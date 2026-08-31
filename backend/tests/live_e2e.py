"""Opt-in live-stack contract smoke test. Run only against an isolated data directory."""

from io import BytesIO
import json
import os
from time import perf_counter

import httpx
from PIL import Image, ImageDraw


API = os.environ.get("LABELGUARD_E2E_API", "http://127.0.0.1:8000").rstrip("/")
FRONTEND = os.environ.get("LABELGUARD_E2E_FRONTEND", "http://localhost:3000").rstrip("/")


def synthetic_label() -> bytes:
    image = Image.new("RGB", (1100, 760), "white")
    draw = ImageDraw.Draw(image)
    lines = [
        "SYNTHETIC E2E FIXTURE - NOT A REAL PRODUCT",
        "COMMON NAME: Roasted grain snack",
        "MANUFACTURED BY: Example Foods Private Limited",
        "ADDRESS: Plot 12, Industrial Estate, Pune, Maharashtra 411001",
        "NET QUANTITY: 250 g",
        "MRP: Rs. 95.00 inclusive of all taxes",
        "MFG: 08/2026",
        "CONSUMER CARE: care@example.test 1800 000 1234",
    ]
    for index, line in enumerate(lines):
        draw.text((45, 45 + index * 78), line, fill="black", font_size=28)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def main() -> None:
    if os.environ.get("LABELGUARD_ALLOW_E2E_WRITES") != "1":
        raise SystemExit(
            "Refusing to create live records. Start the API with LABELGUARD_DATA_DIR pointing "
            "to a temporary directory, then set LABELGUARD_ALLOW_E2E_WRITES=1."
        )
    total_started = perf_counter()
    with httpx.Client(timeout=90) as client:
        frontend = client.get(FRONTEND)
        frontend.raise_for_status()
        assert "LabelGuard" in frontend.text

        health = client.get(f"{API}/system/status").json()
        assert health["database"]["available"] is True
        assert health["rule_engine"]["verdict_source"] == "backend_deterministic_rule_engine"

        preflight = client.options(
            f"{API}/inspect",
            headers={
                "Origin": FRONTEND,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == FRONTEND

        inspect_started = perf_counter()
        created = client.post(
            f"{API}/inspect",
            data={"package_scope": "domestic", "commodity_category": "synthetic test"},
            files={"image": ("synthetic-e2e.png", synthetic_label(), "image/png")},
        )
        assert created.status_code == 201, created.text
        inspect_ms = round((perf_counter() - inspect_started) * 1000, 1)
        result = created.json()
        inspection_id = result["id"]
        assert result["overall_status"] in {
            "compliant", "potential_non_compliance", "manual_review_required"
        }
        assert result["rule_engine_version"].startswith("LMPC-ENGINE-")
        assert result["orientation_degrees"] in {0, 90, 180, 270}

        report_ms = 0.0
        for path, content_type in [
            (f"/inspection/{inspection_id}", "application/json"),
            (f"/inspection/{inspection_id}/image", "image/"),
            (f"/inspection/{inspection_id}/evidence-image", "image/"),
            (f"/report/{inspection_id}", "application/pdf"),
        ]:
            route_started = perf_counter()
            response = client.get(f"{API}{path}")
            response.raise_for_status()
            assert response.headers["content-type"].startswith(content_type)
            if path.startswith("/report/"):
                report_ms = round((perf_counter() - route_started) * 1000, 1)

        review = client.post(
            f"{API}/inspection/{inspection_id}/review",
            json={
                "review_status": "VERIFIED",
                "reviewed_by": "E2E Inspector",
                "review_notes": "Synthetic live-stack verification.",
            },
        )
        review.raise_for_status()

        correction = client.post(
            f"{API}/inspection/{inspection_id}/correct",
            json={
                "field": "date_of_manufacture",
                "corrected_text": "08/2026",
                "reason": "Verified against the synthetic fixture.",
                "actor": "E2E Inspector",
            },
        )
        correction.raise_for_status()
        assert correction.json()["extracted_fields"]["date_of_manufacture"]["source"] == "human_correction"

        audit = client.get(f"{API}/inspection/{inspection_id}/audit").json()
        event_types = [event["event_type"] for event in audit["audit_trail"]]
        assert "REVIEW_UPDATED" in event_types
        assert "RULES_RE_EVALUATED" in event_types
        assert any(item["id"] == inspection_id for item in client.get(f"{API}/history").json())

        print(json.dumps({
            "inspection_id": inspection_id,
            "initial_status": result["overall_status"],
            "orientation_degrees": result["orientation_degrees"],
            "audit_events": len(audit["audit_trail"]),
            "inspect_ms": inspect_ms,
            "report_ms": report_ms,
            "total_e2e_ms": round((perf_counter() - total_started) * 1000, 1),
            "status": "PASS",
        }, indent=2))


if __name__ == "__main__":
    main()

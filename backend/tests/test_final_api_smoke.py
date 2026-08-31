"""One explicit smoke covering every endpoint required by the final extraction gate."""

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
from gemini_fakes import FakeGeminiService, visual_candidate
from gemini_vision import GeminiExtractionResponse


client = TestClient(app_module.app)


def _image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (900, 650), "white").save(output, "PNG")
    return output.getvalue()


def test_final_required_api_smoke(monkeypatch) -> None:
    response = GeminiExtractionResponse(
        image_readability="clear",
        distortion_types=["none"],
        warnings=[],
        fields=[
            visual_candidate("common_name", "Roasted grain snack", "Common name: Roasted grain snack", [40, 30, 100, 560]),
            visual_candidate("manufacturer_name", "Example Foods Pvt. Ltd.", "Manufactured by: Example Foods Pvt. Ltd.", [130, 30, 200, 670]),
            visual_candidate("manufacturer_address", "Plot 12, Industrial Estate, Pune 411001, India", "Manufactured by: Example Foods Pvt. Ltd., Plot 12, Industrial Estate, Pune 411001, India", [200, 30, 280, 780]),
            visual_candidate("net_quantity", "250 g", "Net Quantity: 250 g", [330, 30, 390, 390]),
            visual_candidate("mrp", "Rs. 95.00", "MRP: Rs. 95.00", [430, 30, 490, 390]),
            visual_candidate("manufacture_date", "08/2026", "MFD: 08/2026", [530, 30, 590, 340]),
            visual_candidate("consumer_email", "care@example.test", "Consumer Care: care@example.test", [630, 30, 700, 620]),
        ],
    )
    monkeypatch.setattr(app_module, "GEMINI", FakeGeminiService(response))
    monkeypatch.setattr(
        app_module,
        "analyze_image_quality",
        lambda _: {"status": "good", "is_decodable": True, "width": 900, "height": 650, "warnings": []},
    )

    assert client.get("/health").status_code == 200
    assert client.get("/system/status").json()["rule_engine"]["verdict_source"] == "backend_deterministic_rule_engine"
    assert client.get("/rules").status_code == 200

    created = client.post(
        "/inspect",
        files={"image": ("final-smoke.png", _image(), "image/png")},
        data={"package_scope": "domestic"},
    )
    assert created.status_code == 201, created.text
    inspection_id = created.json()["id"]

    history = client.get("/history")
    assert history.status_code == 200
    assert any(item["id"] == inspection_id for item in history.json())
    assert client.get(f"/inspection/{inspection_id}").status_code == 200
    report = client.get(f"/report/{inspection_id}")
    assert report.status_code == 200
    assert report.content.startswith(b"%PDF")

    review = client.post(
        f"/inspection/{inspection_id}/review",
        json={"review_status": "VERIFIED", "reviewed_by": "Final Smoke", "review_notes": "Endpoint verification"},
    )
    assert review.status_code == 200
    correction = client.post(
        f"/inspection/{inspection_id}/correct",
        json={"field": "date_of_manufacture", "corrected_text": "08/2026", "reason": "Verified fixture", "actor": "Final Smoke"},
    )
    assert correction.status_code == 200
    assert correction.json()["extracted_fields"]["date_of_manufacture"]["source"] == "human_correction"

    audit = client.get(f"/inspection/{inspection_id}/audit")
    assert audit.status_code == 200
    event_types = {event["event_type"] for event in audit.json()["audit_trail"]}
    assert {"REVIEW_UPDATED", "FIELD_CORRECTED", "RULES_RE_EVALUATED"}.issubset(event_types)

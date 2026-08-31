from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
import image_quality
from database import save_inspection
from gemini_fakes import FakeGeminiService
from gemini_vision import GeminiExtractionResponse


client = TestClient(app_module.app)


def _png(width: int = 100, height: int = 100) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def _record(**overrides):
    record = {
        "id": str(uuid4()),
        "original_filename": "fixture.png",
        "stored_filename": "fixture.png",
        "mime_type": "image/png",
        "file_size_bytes": 100,
        "created_at": "2026-08-30T00:00:00+00:00",
        "overall_status": "manual_review_required",
        "quality": {"status": "good"},
        "extracted_fields": {},
        "findings": [],
        "context": {"package_scope": "unknown"},
    }
    record.update(overrides)
    return record


def test_security_headers_are_present() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers.get("x-request-id")


def test_valid_image_with_spoofed_extension_uses_detected_mime(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "GEMINI",
        FakeGeminiService(
            GeminiExtractionResponse(
                image_readability="clear",
                distortion_types=["none"],
                fields=[],
                warnings=[],
            )
        ),
    )
    response = client.post(
        "/inspect",
        files={"image": ("payload.jpg", _png(), "image/jpeg")},
        data={"package_scope": "unknown"},
    )
    assert response.status_code == 201
    detail = client.get(f"/inspection/{response.json()['id']}").json()
    assert detail["mime_type"] == "image/png"


def test_pixel_safety_limit_is_enforced(monkeypatch) -> None:
    monkeypatch.setattr(image_quality, "MAX_PIXEL_AREA", 5_000)
    response = client.post(
        "/inspect",
        files={"image": ("large.png", _png(100, 100), "image/png")},
    )
    assert response.status_code == 422
    assert "pixel safety limit" in response.json()["detail"]


def test_media_path_traversal_and_unknown_correction_field_are_rejected() -> None:
    inspection_id = save_inspection(_record(stored_filename=r"..\outside.png"))
    assert client.get(f"/inspection/{inspection_id}/image").status_code == 404
    correction = client.post(
        f"/inspection/{inspection_id}/correct",
        json={
            "field": "overall_status",
            "corrected_text": "compliant",
            "reason": "attempted direct verdict edit",
            "actor": "Security test",
        },
    )
    assert correction.status_code == 400


def test_csv_export_neutralizes_spreadsheet_formulas() -> None:
    save_inspection(_record(original_filename="=HYPERLINK(\"https://example.test\")"))
    response = client.get("/exports/history.csv")
    assert response.status_code == 200
    assert "'=HYPERLINK" in response.text


def test_upload_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "UPLOAD_RATE_LIMIT", 1)
    app_module._upload_attempts.clear()
    first = client.post("/inspect", files={"image": ("bad.png", b"bad", "image/png")})
    assert first.status_code == 422
    second = client.post("/inspect", files={"image": ("bad.png", b"bad", "image/png")})
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
from gemini_fakes import FakeGeminiService, visual_candidate
from gemini_vision import GeminiExtractionResponse


client = TestClient(app_module.app)


def _valid_png() -> bytes:
    image = Image.new("RGB", (1000, 700), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_api_contract_end_to_end(monkeypatch) -> None:
    response = GeminiExtractionResponse(
        image_readability="clear",
        distortion_types=["none"],
        warnings=[],
        fields=[
            visual_candidate("common_name", "Roasted chickpea snack", "Common name: Roasted chickpea snack", [50, 40, 120, 650]),
            visual_candidate("manufacturer_name", "Example Foods Private Limited", "Manufactured by: Example Foods Private Limited", [150, 40, 230, 760]),
            visual_candidate("manufacturer_address", "12 Industrial Estate, Pune 411001, India", "Manufactured by: Example Foods Private Limited, 12 Industrial Estate, Pune 411001, India", [230, 40, 310, 760]),
            visual_candidate("net_quantity", "500 g", "Net Quantity: 500 g", [350, 40, 420, 360]),
            visual_candidate("mrp", "Rs. 120", "MRP: Rs. 120", [450, 40, 520, 300]),
            visual_candidate("manufacture_date", "08/2026", "MFD: 08/2026", [550, 40, 620, 300]),
            visual_candidate("consumer_email", "care@example.test", "Consumer Care: care@example.test", [650, 40, 720, 800]),
        ],
    )
    monkeypatch.setattr(app_module, "GEMINI", FakeGeminiService(response))
    monkeypatch.setattr(
        app_module,
        "analyze_image_quality",
        lambda _: {"status": "good", "is_decodable": True, "width": 1000, "height": 700, "warnings": []},
    )

    response = client.post(
        "/inspect",
        files={"image": ("synthetic-label.png", _valid_png(), "image/png")},
        data={"package_scope": "domestic", "commodity_category": "snack food"},
    )
    assert response.status_code == 201, response.text
    data = response.json()

    assert isinstance(data["id"], int)
    inspection_id = data["id"]
    assert data["overall_status"] == "compliant"
    assert data["quality"]["is_decodable"] is True
    assert data["orientation_degrees"] == 0
    assert data["ocr_engine"] == "gemini-vision/test-gemini"
    assert data["context"]["package_scope"] == "domestic"
    assert data["image_url"].endswith(f"/inspection/{inspection_id}/image")

    assert isinstance(data["extracted_fields"], dict)
    for field_name, field_value in data["extracted_fields"].items():
        assert isinstance(field_name, str)
        assert isinstance(field_value["text"], str)
        assert 0.0 <= field_value["confidence"] <= 1.0
        assert field_value["source"] in {"gemini", "human_correction"}

    assert len(data["findings"]) == 6
    for finding in data["findings"]:
        assert finding["status"] in {"PASS", "FAIL", "UNCERTAIN"}
        assert finding["severity"] in {"MAJOR", "MINOR"}
        assert len(finding["bounding_box"]) == 4
        assert finding["source_citation"].startswith("Legal Metrology")
        assert finding["rule_version"]

    history_response = client.get("/history", params={"search": str(inspection_id)})
    assert history_response.status_code == 200
    assert history_response.json()[0]["id"] == inspection_id

    detail_response = client.get(f"/inspection/{inspection_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["overall_status"] == data["overall_status"]

    image_response = client.get(f"/inspection/{inspection_id}/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"

    report_response = client.get(f"/report/{inspection_id}")
    assert report_response.status_code == 200
    assert report_response.headers["content-type"] == "application/pdf"
    assert report_response.content.startswith(b"%PDF")

    analytics_response = client.get("/analytics")
    assert analytics_response.status_code == 200
    assert analytics_response.json()["total_inspections"] == 1

    csv_response = client.get("/exports/history.csv")
    assert csv_response.status_code == 200
    assert "synthetic-label.png" in csv_response.text

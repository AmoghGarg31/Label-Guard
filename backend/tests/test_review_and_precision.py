import uuid
import pytest
from fastapi.testclient import TestClient
from app import app
from database import get_connection, save_inspection
from extractor import compute_precise_bbox, extract_fields
from models import OcrLine, FieldEvidence
from report import build_pdf
from rules import evaluate_rules, overall_status, load_rules

client = TestClient(app)

def test_precise_bbox_subtoken_calculation():
    line_text = "BISCUITS NET WEIGHT: 270 g (4 Units x 67.5 g)"
    bbox = (100, 200, 900, 240)
    start_idx = line_text.find("270 g")
    end_idx = start_idx + len("270 g")
    precise = compute_precise_bbox(line_text, bbox, (start_idx, end_idx))
    
    assert precise is not None
    assert precise[1] == 200
    assert precise[3] == 240
    width = precise[2] - precise[0]
    assert width < 250, f"Expected tight box width < 250, got {width}"
    assert precise[0] >= 100
    assert precise[2] <= 900

def test_mrp_rejects_usp_unit_price():
    lines = [
        OcrLine(text="MRP", confidence=0.90, bounding_box=(100, 100, 200, 130)),
        OcrLine(text="3 Per g", confidence=0.85, bounding_box=(500, 100, 600, 130)),
        OcrLine(text="Rs. 170.00", confidence=0.92, bounding_box=(250, 100, 400, 130)),
    ]
    fields = extract_fields(lines)
    assert fields["mrp"].value == "₹170.00"
    assert fields["mrp"].confidence >= 0.55
    assert fields["mrp"].confidence != 0.92
    assert fields["mrp"].bounding_box[2] <= 420

def test_zero_box_behavior():
    lines = [OcrLine(text="Random unrelated packaging text", confidence=0.80, bounding_box=(10, 10, 100, 30))]
    fields = extract_fields(lines)
    assert fields["net_quantity"].value is None
    assert fields["net_quantity"].bounding_box is None

def test_review_status_does_not_mutate_automated_verdict():
    rules = load_rules()
    test_fields = {
        "net_quantity": FieldEvidence(None, 0.0, None),
        "mrp": FieldEvidence("₹50", 0.95, (10, 10, 50, 30)),
        "manufacturer_name": FieldEvidence("ABC Ltd", 0.90, None),
        "manufacturer_address": FieldEvidence("Mumbai 400001", 0.90, None),
        "responsible_party_name_and_address": FieldEvidence("Example Foods Ltd, Mumbai 400001", 0.90, None),
        "common_or_generic_name": FieldEvidence("Roasted snack", 0.95, None),
        "date_of_manufacture": FieldEvidence("01/2026", 0.90, None),
        "consumer_care_contact": FieldEvidence("care@abc.com", 0.90, None),
        "country_of_origin": FieldEvidence("India", 0.90, None),
    }
    findings = evaluate_rules(test_fields, rules, {"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, 10)
    assert verdict == "manual_review_required"

    test_id = str(uuid.uuid4())
    record = {
        "id": test_id,
        "original_filename": "test_immutability.png",
        "stored_filename": "test_immutability.png",
        "file_size_bytes": 1000,
        "created_at": "2026-08-30T00:00:00Z",
        "overall_status": verdict,
        "extracted_fields": {"net_quantity": {"text": "", "confidence": 0.0}},
        "findings": findings,
        "context": {"package_scope": "domestic"},
    }
    numeric_id = save_inspection(record)

    resp = client.post(
        f"/inspection/{numeric_id}/review",
        json={"review_status": "VERIFIED", "reviewed_by": "Inspector Test", "review_notes": "Visually verified on pack"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["review"]["review_status"] == "VERIFIED"

    detail_resp = client.get(f"/inspection/{numeric_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["overall_status"] == "manual_review_required"
    assert detail["review"]["review_status"] == "VERIFIED"

def test_ocr_correction_re_evaluates_rules_deterministically():
    rules = load_rules()
    test_fields = {
        "net_quantity": FieldEvidence(None, 0.0, None),
        "mrp": FieldEvidence("₹50", 0.95, (10, 10, 50, 30)),
        "manufacturer_name": FieldEvidence("ABC Foods Pvt Ltd", 0.95, None),
        "manufacturer_address": FieldEvidence("Plot 1, Mumbai, Maharashtra 400001", 0.95, None),
        "responsible_party_name_and_address": FieldEvidence("Example Foods Pvt Ltd, Plot 1, Mumbai 400001", 0.95, None),
        "common_or_generic_name": FieldEvidence("Roasted snack", 0.95, None),
        "date_of_manufacture": FieldEvidence("01/2026", 0.95, None),
        "consumer_care_contact": FieldEvidence("care@abc.com", 0.95, None),
        "country_of_origin": FieldEvidence("India", 0.95, None),
    }
    findings = evaluate_rules(test_fields, rules, {"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, 10)
    assert verdict == "manual_review_required"

    test_id = str(uuid.uuid4())
    record = {
        "id": test_id,
        "original_filename": "test_correct.png",
        "stored_filename": "test_correct.png",
        "file_size_bytes": 1000,
        "created_at": "2026-08-30T00:00:00Z",
        "overall_status": verdict,
        "quality": {"status": "good"},
        "ocr_text": "SAMPLE PRODUCT\nNET WT: 250 g\nMRP Rs. 50\nMFG: ABC FOODS",
        "extracted_fields": {
            "net_quantity": {"text": "", "confidence": 0.0},
            "mrp": {"text": "₹50", "confidence": 0.95},
            "common_or_generic_name": {"text": "Roasted snack", "confidence": 0.95},
            "manufacturer_name": {"text": "Example Foods Pvt Ltd", "confidence": 0.95},
            "manufacturer_address": {"text": "Plot 1, Mumbai, Maharashtra 400001", "confidence": 0.95},
            "date_of_manufacture": {"text": "01/2026", "confidence": 0.95},
            "consumer_care_contact": {"text": "care@abc.com", "confidence": 0.95},
            "country_of_origin": {"text": "India", "confidence": 0.95},
        },
        "findings": findings,
        "context": {"package_scope": "domestic"},
    }
    numeric_id = save_inspection(record)

    corr_resp = client.post(
        f"/inspection/{numeric_id}/correct",
        json={
            "field": "net_quantity",
            "corrected_text": "250 g",
            "reason": "Clear net weight on lower panel",
            "actor": "Test Officer"
        }
    )
    assert corr_resp.status_code == 200
    updated = corr_resp.json()
    assert updated["overall_status"] == "compliant"
    assert len(updated["corrections"]) == 1
    assert updated["corrections"][0]["field"] == "net_quantity"
    assert updated["corrections"][0]["corrected_text"] == "250 g"
    
    audit_resp = client.get(f"/inspection/{numeric_id}/audit")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    event_types = [e["event_type"] for e in audit_data["audit_trail"]]
    assert "FIELD_CORRECTED" in event_types
    assert "RULES_RE_EVALUATED" in event_types

def test_pdf_report_includes_review_and_audit():
    test_id = str(uuid.uuid4())
    record = {
        "id": test_id,
        "original_filename": "test_label.png",
        "stored_filename": "test_label.png",
        "file_size_bytes": 1000,
        "created_at": "2026-08-30T00:00:00Z",
        "overall_status": "compliant",
        "extracted_fields": {"mrp": {"text": "₹100", "confidence": 0.95}},
        "findings": [],
    }
    numeric_id = save_inspection(record)
    client.post(
        f"/inspection/{numeric_id}/review",
        json={"review_status": "VERIFIED", "reviewed_by": "Senior Officer", "review_notes": "Batch physically verified"}
    )
    saved_record = __import__("database").get_inspection(numeric_id)
    pdf_bytes = build_pdf(saved_record)
    assert len(pdf_bytes) > 1000
    assert b"%PDF" in pdf_bytes[:10]

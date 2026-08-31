import pytest
import cv2
from rules import evaluate_rules, overall_status
from models import FieldEvidence
from image_quality import analyze_image_quality
from extractor import extract_fields
from models import OcrLine
import numpy as np

def test_scenario_a_good_readable_compliant_label():
    fields = {
        'mrp': FieldEvidence('₹ 150.00', 0.95, (10, 10, 50, 100)),
        'net_quantity': FieldEvidence('500 g', 0.92, (60, 10, 100, 100)),
        'responsible_party_name_and_address': FieldEvidence('Example Foods Ltd, Bengaluru, India', 0.90, (110, 10, 150, 200)),
        'common_or_generic_name': FieldEvidence('Whole wheat biscuits', 0.94, (5, 5, 90, 30)),
        'date_of_manufacture': FieldEvidence('08/2026', 0.93, (210, 10, 250, 100)),
        'consumer_care_contact': FieldEvidence('care@example.test, 1800-000-1234', 0.91, (260, 10, 300, 200)),
        'country_of_origin': FieldEvidence('India', 0.95, (310, 10, 350, 100)),
    }
    findings = evaluate_rules(fields, context={"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, ocr_line_count=5)
    assert verdict == 'compliant'
    assert all(f['status'] == 'PASS' for f in findings)
    assert len(findings) == 6

def test_scenario_b_missing_mandatory_declaration():
    # MRP missing -> should be UNCERTAIN (requires manual review)
    fields = {
        'net_quantity': FieldEvidence('500 g', 0.92, (60, 10, 100, 100)),
        'responsible_party_name_and_address': FieldEvidence('Example Foods Ltd, Bengaluru, India', 0.90, (110, 10, 150, 200)),
    }
    findings = evaluate_rules(fields, context={"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, ocr_line_count=5)
    assert verdict == 'manual_review_required'
    mrp_finding = next(f for f in findings if f['rule_id'] == 'LMPC-MRP-001')
    assert mrp_finding['status'] == 'UNCERTAIN'

def test_scenario_c_blurry_low_quality_image():
    # Synthetic flat/blurry black image
    flat_img = np.zeros((100, 100, 3), dtype=np.uint8)
    import cv2
    _, encoded = cv2.imencode('.png', flat_img)
    quality = analyze_image_quality(encoded.tobytes())
    assert quality['status'] == 'review'
    assert len(quality['warnings']) > 0


def test_bright_readable_label_is_not_misclassified_as_glare() -> None:
    image = np.full((700, 1000, 3), 255, dtype=np.uint8)
    for y in range(80, 620, 70):
        cv2.putText(image, "DECLARATION PANEL 250 g Rs. 95", (40, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (5, 5, 5), 3)
    ok, encoded = cv2.imencode('.png', image)
    assert ok
    quality = analyze_image_quality(encoded.tobytes())
    assert quality['glare_ok'] is True
    assert quality['status'] == 'good'


def test_washed_out_frame_is_flagged_for_review() -> None:
    image = np.full((700, 1000, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode('.png', image)
    assert ok
    quality = analyze_image_quality(encoded.tobytes())
    assert quality['glare_ok'] is False
    assert quality['status'] == 'review'

def test_scenario_d_mrp_malformed_text():
    # MRP present but not a valid rupee format -> FAIL -> potential_non_compliance
    fields = {
        'mrp': FieldEvidence('FREE SAMPLE NOT FOR SALE', 0.95, (10, 10, 50, 100)),
        'net_quantity': FieldEvidence('500 g', 0.92, (60, 10, 100, 100)),
        'responsible_party_name_and_address': FieldEvidence('Example Foods Ltd, Bengaluru', 0.90, (110, 10, 150, 200)),
    }
    findings = evaluate_rules(fields, context={"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, ocr_line_count=5)
    assert verdict == 'potential_non_compliance'
    mrp_finding = next(f for f in findings if f['rule_id'] == 'LMPC-MRP-001')
    assert mrp_finding['status'] == 'FAIL'


def test_scenario_d_anchored_malformed_ocr_reaches_rule_engine():
    lines = [
        OcrLine('MRP: ask retailer', 0.94, (10, 10, 220, 40)),
        OcrLine('Net Quantity: 500 g', 0.94, (10, 50, 220, 80)),
    ]
    fields = extract_fields(lines)
    findings = evaluate_rules(fields, context={"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, ocr_line_count=len(lines))
    mrp_finding = next(f for f in findings if f['rule_id'] == 'LMPC-MRP-001')
    assert fields['mrp'].value == 'ask retailer'
    assert mrp_finding['status'] == 'FAIL'
    assert verdict == 'potential_non_compliance'

def test_scenario_e_net_quantity_malformed():
    # Net quantity present but non-metric unit -> FAIL -> potential_non_compliance
    fields = {
        'mrp': FieldEvidence('₹ 150', 0.95, (10, 10, 50, 100)),
        'net_quantity': FieldEvidence('10 pieces', 0.92, (60, 10, 100, 100)),
        'responsible_party_name_and_address': FieldEvidence('Example Foods Ltd, Bengaluru', 0.90, (110, 10, 150, 200)),
    }
    findings = evaluate_rules(fields, context={"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, ocr_line_count=5)
    assert verdict == 'potential_non_compliance'
    net_finding = next(f for f in findings if f['rule_id'] == 'LMPC-NET-001')
    assert net_finding['status'] == 'FAIL'

def test_scenario_f_manufacturer_partial():
    # Field missing / None -> UNCERTAIN
    fields = {
        'mrp': FieldEvidence('₹ 150', 0.95, (10, 10, 50, 100)),
        'net_quantity': FieldEvidence('500 g', 0.92, (60, 10, 100, 100)),
    }
    findings = evaluate_rules(fields, context={"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, ocr_line_count=5)
    assert verdict == 'manual_review_required'
    mfr_finding = next(f for f in findings if f['rule_id'] == 'LMPC-MFR-001')
    assert mfr_finding['status'] == 'UNCERTAIN'

def test_scenario_g_low_ocr_confidence():
    # Valid pattern but OCR confidence below threshold (0.55) -> UNCERTAIN -> manual_review_required
    fields = {
        'mrp': FieldEvidence('₹ 150', 0.40, (10, 10, 50, 100)),
        'net_quantity': FieldEvidence('500 g', 0.92, (60, 10, 100, 100)),
        'responsible_party_name_and_address': FieldEvidence('Example Foods Ltd, Bengaluru', 0.90, (110, 10, 150, 200)),
    }
    findings = evaluate_rules(fields, context={"package_scope": "domestic"})
    verdict = overall_status(findings, {"status": "good"}, ocr_line_count=5)
    assert verdict == 'manual_review_required'
    mrp_finding = next(f for f in findings if f['rule_id'] == 'LMPC-MRP-001')
    assert mrp_finding['status'] == 'UNCERTAIN'

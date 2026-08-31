from pathlib import Path
import pytest
from models import FieldEvidence
from rules import evaluate_rules, load_rules, overall_status, RULE_ENGINE_VERSION
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def evidence(value: str | None, confidence: float = 0.95) -> FieldEvidence:
    return FieldEvidence(value, confidence, (1, 2, 30, 40) if value else None)


def test_all_active_rules_load_successfully() -> None:
    rules = load_rules()
    assert len(rules) >= 6
    rule_ids = [r["rule_id"] for r in rules]
    assert "LMPC-MRP-001" in rule_ids
    assert "LMPC-NET-001" in rule_ids
    assert "LMPC-MFR-001" in rule_ids
    assert "LMPC-DOM-001" in rule_ids
    assert "LMPC-CARE-001" in rule_ids
    assert "LMPC-COO-001" in rule_ids
    assert "LMPC-NAME-001" in rule_ids


def test_duplicate_rule_id_fails_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import rules

    fake_rules_dir = tmp_path / "rules"
    fake_rules_dir.mkdir()

    r1 = {
        "rule_id": "DUP-001",
        "rule_version": "1.0",
        "active": True,
        "field": "mrp",
        "source_citation": "Test source",
        "description": "Rule 1",
        "check_type": "presence_and_pattern",
        "pattern": r"^\d+$",
        "severity_if_fail": "high",
        "confidence_floor": 0.5,
        "on_field_missing": "UNCERTAIN",
    }
    r2 = {
        "rule_id": "DUP-001",
        "rule_version": "1.0",
        "active": True,
        "field": "net_quantity",
        "source_citation": "Test source",
        "description": "Rule 2 (duplicate)",
        "check_type": "presence_and_pattern",
        "pattern": r"^\d+$",
        "severity_if_fail": "high",
        "confidence_floor": 0.5,
        "on_field_missing": "UNCERTAIN",
    }

    (fake_rules_dir / "a.json").write_text(json.dumps(r1))
    (fake_rules_dir / "b.json").write_text(json.dumps(r2))

    monkeypatch.setattr(rules, "RULES_DIR", fake_rules_dir)
    with pytest.raises(ValueError, match="Duplicate rule_id 'DUP-001'"):
        rules.load_rules()


def test_missing_required_metadata_fails_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import rules

    fake_rules_dir = tmp_path / "rules"
    fake_rules_dir.mkdir()

    invalid_rule = {
        "rule_id": "INVALID-001",
        # missing "field", "description", "check_type"
    }

    (fake_rules_dir / "invalid.json").write_text(json.dumps(invalid_rule))
    monkeypatch.setattr(rules, "RULES_DIR", fake_rules_dir)
    with pytest.raises(ValueError, match="missing required fields"):
        rules.load_rules()


def test_missing_field_is_uncertain_not_fail() -> None:
    result = evaluate_rules({"net_quantity": evidence(None)}, [
        {
            "rule_id": "test-missing",
            "field": "net_quantity",
            "check_type": "presence_and_pattern",
            "pattern": r"^\d+\s*g$",
            "confidence_floor": 0.5,
            "severity_if_fail": "high",
            "on_field_missing": "UNCERTAIN",
        }
    ])
    assert result[0]["status"] == "UNCERTAIN"


def test_net_quantity_with_unit_passes() -> None:
    result = evaluate_rules({"net_quantity": evidence("500 g")}, [
        {
            "rule_id": "test-net",
            "field": "net_quantity",
            "check_type": "presence_and_pattern",
            "pattern": r"^\d+\s*(?:kg|g|mg)$",
            "confidence_floor": 0.5,
            "severity_if_fail": "high",
            "on_field_missing": "UNCERTAIN",
        }
    ])
    assert result[0]["status"] == "PASS"


def test_malformed_present_value_fails() -> None:
    result = evaluate_rules({"net_quantity": evidence("500")}, [
        {
            "rule_id": "test-net",
            "field": "net_quantity",
            "check_type": "presence_and_pattern",
            "pattern": r"^\d+\s*g$",
            "confidence_floor": 0.5,
            "severity_if_fail": "high",
            "on_field_missing": "UNCERTAIN",
        }
    ])
    assert result[0]["status"] == "FAIL"


def test_low_confidence_routes_to_uncertain() -> None:
    result = evaluate_rules({"mrp": evidence("₹100", 0.2)}, [
        {
            "rule_id": "test-mrp",
            "field": "mrp",
            "check_type": "presence_and_pattern",
            "pattern": r"^(?:₹|Rs\.?)\s*\d+$",
            "confidence_floor": 0.5,
            "severity_if_fail": "high",
            "on_field_missing": "UNCERTAIN",
        }
    ])
    assert result[0]["status"] == "UNCERTAIN"


def test_date_of_manufacture_rule() -> None:
    active_rules = load_rules()
    dom_rule = [r for r in active_rules if r["rule_id"] == "LMPC-DOM-001"]
    assert len(dom_rule) == 1

    # Valid date format
    res_pass = evaluate_rules({"date_of_manufacture": evidence("08/2026")}, dom_rule)
    assert res_pass[0]["status"] == "PASS"

    # Malformed date format
    res_fail = evaluate_rules({"date_of_manufacture": evidence("not-a-date")}, dom_rule)
    assert res_fail[0]["status"] == "FAIL"

    # Missing date
    res_missing = evaluate_rules({"date_of_manufacture": evidence(None)}, dom_rule)
    assert res_missing[0]["status"] == "UNCERTAIN"


def test_consumer_care_rule() -> None:
    active_rules = load_rules()
    care_rule = [r for r in active_rules if r["rule_id"] == "LMPC-CARE-001"]
    assert len(care_rule) == 1

    # Valid email/contact
    res_pass = evaluate_rules({"consumer_care_contact": evidence("care@example.test, 1800-123-4567")}, care_rule)
    assert res_pass[0]["status"] == "PASS"

    # Missing contact
    res_missing = evaluate_rules({"consumer_care_contact": evidence(None)}, care_rule)
    assert res_missing[0]["status"] == "UNCERTAIN"


def test_country_of_origin_rule() -> None:
    active_rules = load_rules()
    coo_rule = [r for r in active_rules if r["rule_id"] == "LMPC-COO-001"]
    assert len(coo_rule) == 1

    # Valid country
    res_pass = evaluate_rules({"country_of_origin": evidence("India")}, coo_rule)
    assert res_pass[0]["status"] == "PASS"

    # Missing country
    res_missing = evaluate_rules({"country_of_origin": evidence(None)}, coo_rule)
    assert res_missing[0]["status"] == "UNCERTAIN"

    # The declaration is not applicable to a package explicitly identified as domestic.
    res_domestic = evaluate_rules(
        {"country_of_origin": evidence(None)}, coo_rule, {"package_scope": "domestic"}
    )
    assert res_domestic == []

    # Unknown scope remains cautious instead of silently assuming a domestic package.
    res_unknown = evaluate_rules(
        {"country_of_origin": evidence(None)}, coo_rule, {"package_scope": "unknown"}
    )
    assert res_unknown[0]["status"] == "UNCERTAIN"
    assert res_unknown[0]["applicability"] == "unknown"


def test_overall_status_deterministic_logic() -> None:
    # 1 FAIL -> potential_non_compliance
    findings_fail = [{"status": "FAIL"}, {"status": "PASS"}]
    assert overall_status(findings_fail, {"status": "good"}, 5) == "potential_non_compliance"

    # 1 UNCERTAIN -> manual_review_required
    findings_unc = [{"status": "UNCERTAIN"}, {"status": "PASS"}]
    assert overall_status(findings_unc, {"status": "good"}, 5) == "manual_review_required"

    # All PASS + good quality -> compliant
    findings_pass = [{"status": "PASS"}, {"status": "PASS"}]
    assert overall_status(findings_pass, {"status": "good"}, 5) == "compliant"

    # Quality retake -> manual_review_required even if all PASS
    assert overall_status(findings_pass, {"status": "retake"}, 5) == "manual_review_required"


def test_rules_api_endpoint() -> None:
    resp = client.get("/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 6

    for r in data:
        assert "rule_id" in r
        assert "field" in r
        assert "source_citation" in r
        assert "description" in r
        assert "severity" in r
        assert "confidence_floor" in r
        assert "check_type" in r
        # Verify no filesystem paths or secret keys are exposed
        for val in r.values():
            assert not str(val).startswith("c:\\")
            assert not str(val).startswith("/")
            assert "token" not in str(val).lower()
            assert "secret" not in str(val).lower()

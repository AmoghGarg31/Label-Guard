"""Versioned, deterministic compliance rules."""

import json
import re
from pathlib import Path
from typing import Any

from models import BBox, FieldEvidence


RULES_DIR = Path(__file__).resolve().parent / "rules"
RULE_ENGINE_VERSION = "LMPC-ENGINE-2.0"

REQUIRED_RULE_KEYS = {
    "rule_id",
    "rule_version",
    "active",
    "field",
    "source_citation",
    "description",
    "check_type",
    "severity_if_fail",
    "confidence_floor",
    "on_field_missing",
}
VALID_FINDING_STATUSES = {"PASS", "FAIL", "UNCERTAIN"}


def load_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in sorted(RULES_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as rule_file:
            rule = json.load(rule_file)
            missing = REQUIRED_RULE_KEYS - set(rule.keys())
            if missing:
                raise ValueError(f"Rule in {path.name} is missing required fields: {missing}")
            rule_id = rule["rule_id"]
            if rule_id in seen_ids:
                raise ValueError(f"Duplicate rule_id '{rule_id}' detected in {path.name}")
            seen_ids.add(rule_id)
            if rule.get("on_field_missing") != "UNCERTAIN":
                raise ValueError(
                    f"Rule '{rule_id}' must use on_field_missing='UNCERTAIN'; "
                    "a missing OCR field is not proof of a violation."
                )
            confidence_floor = float(rule.get("confidence_floor", -1))
            if not 0 <= confidence_floor <= 1:
                raise ValueError(f"Rule '{rule_id}' has an invalid confidence_floor.")
            if rule.get("check_type") == "presence_and_pattern" and not rule.get("pattern"):
                raise ValueError(f"Rule '{rule_id}' has check_type 'presence_and_pattern' but missing 'pattern'")
            if rule.get("active") is True:
                rules.append(rule)
    return rules


SEVERITY_MAP = {
    "critical": "MAJOR",
    "high": "MAJOR",
    "medium": "MINOR",
    "low": "MINOR",
    "info": "MINOR",
}


def _box_as_list(box: BBox | None) -> list[int]:
    if box is not None and len(box) == 4 and box[2] > box[0] and box[3] > box[1]:
        return [int(box[0]), int(box[1]), int(box[2]), int(box[3])]
    return [0, 0, 0, 0]


def _normalize_severity(rule: dict[str, Any]) -> str:
    raw = rule.get("severity_if_fail") or rule.get("severity")
    if raw is None:
        raise ValueError(f"Rule '{rule.get('rule_id')}' is missing 'severity_if_fail' or 'severity'.")
    raw_str = str(raw).lower()
    if raw_str not in SEVERITY_MAP:
        raise ValueError(
            f"Rule '{rule.get('rule_id')}' has unrecognized severity '{raw}'. "
            f"Expected one of {list(SEVERITY_MAP.keys())}."
        )
    return SEVERITY_MAP[raw_str]


def _finding(
    rule: dict[str, Any],
    status: str,
    confidence: float,
    box: BBox | None,
    *,
    description: str | None = None,
    applicability: str = "applicable",
) -> dict[str, Any]:
    if status not in VALID_FINDING_STATUSES:
        raise ValueError(f"Rule '{rule.get('rule_id')}' produced invalid status '{status}'.")
    return {
        "rule_id": rule["rule_id"],
        "field": rule["field"],
        "status": status,
        "severity": _normalize_severity(rule),
        "confidence": round(max(0.0, min(confidence, 1.0)), 3),
        "bounding_box": _box_as_list(box),
        "description": description or rule.get("description", ""),
        "source_citation": rule.get("source_citation", ""),
        "rule_version": str(rule.get("rule_version", "1.0")),
        "applicability": applicability,
    }


def evaluate_rules(
    extracted_fields: dict[str, FieldEvidence],
    rules: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate rules without side effects, OCR calls, or generative models."""

    active_rules = rules if rules is not None else load_rules()
    findings: list[dict[str, Any]] = []
    package_scope = str((context or {}).get("package_scope", "unknown")).lower()
    if package_scope not in {"unknown", "domestic", "imported"}:
        package_scope = "unknown"
    for rule in active_rules:
        evidence = extracted_fields.get(rule["field"], FieldEvidence(None, 0.0, None))
        missing = evidence.value is None or not str(evidence.value).strip()

        if rule.get("applicability") == "imported_goods_only":
            if package_scope == "domestic":
                continue
            if package_scope == "unknown" and missing:
                findings.append(
                    _finding(
                        rule,
                        "UNCERTAIN",
                        evidence.confidence,
                        evidence.bounding_box,
                        description=(
                            "Country-of-origin applicability cannot be determined until the "
                            "package is identified as domestic or imported."
                        ),
                        applicability="unknown",
                    )
                )
                continue

        if missing:
            findings.append(_finding(rule, rule.get("on_field_missing", "UNCERTAIN"), evidence.confidence, evidence.bounding_box))
            continue

        if evidence.confidence < float(rule.get("confidence_floor", 0)):
            findings.append(_finding(rule, "UNCERTAIN", evidence.confidence, evidence.bounding_box))
            continue

        check_type = rule.get("check_type")
        if check_type == "presence_and_pattern":
            passed = bool(re.search(rule["pattern"], evidence.value or "", re.IGNORECASE))
        elif check_type == "all_present":
            passed = bool(evidence.value and str(evidence.value).strip())
        else:
            raise ValueError(f"Unsupported check_type: {check_type}")
        findings.append(_finding(rule, "PASS" if passed else "FAIL", evidence.confidence, evidence.bounding_box))
    return findings


def overall_status(
    findings: list[dict[str, Any]],
    quality: dict[str, Any],
    ocr_line_count: int,
) -> str:
    if any(finding["status"] == "FAIL" for finding in findings):
        return "potential_non_compliance"
    if (
        any(finding["status"] == "UNCERTAIN" for finding in findings)
        or quality.get("status") != "good"
        or ocr_line_count == 0
    ):
        return "manual_review_required"
    return "compliant"

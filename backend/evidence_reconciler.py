"""Deterministic validation and mapping of visual-reader evidence.

The active inspection path uses Gemini as its only image reader. This module
is the trust boundary: model candidates are parsed by LabelGuard's
field-specific deterministic extractors before they can reach ``rules.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from extractor import extract_fields
from gemini_vision import GeminiExtractionResponse, GeminiFieldCandidate
from models import BBox, FIELD_NAMES, FieldEvidence, OcrLine, OcrToken


VerificationState = Literal[
    "GEMINI_VALIDATED",
    "CONFLICT",
    "UNREADABLE",
    "MISSING",
]

GEMINI_TO_ACTIVE_FIELD: dict[str, str | None] = {
    "common_name": "common_or_generic_name",
    "manufacturer_name": "manufacturer_name",
    "manufacturer_address": "manufacturer_address",
    "packer_name": "packer_name",
    "packer_address": "packer_address",
    "marketer_name": "marketer_name",
    "marketer_address": "marketer_address",
    "importer_name": "importer_name",
    "importer_address": "importer_address",
    "net_quantity": "net_quantity",
    "mrp": "mrp",
    "manufacture_date": "date_of_manufacture",
    "packing_date": "date_of_manufacture",
    "best_before": None,
    "use_by": None,
    "expiry_date": None,
    "consumer_phone": "consumer_care_contact",
    "consumer_email": "consumer_care_contact",
    "consumer_website": "consumer_care_contact",
    "consumer_address": "consumer_care_contact",
    "country_of_origin": "country_of_origin",
}


@dataclass(frozen=True)
class ValidatedGeminiCandidate:
    field: str
    source_field: str
    value: str
    model_score: float
    bbox_2d: list[int] | None
    raw_text: str | None
    evidence_text: str


@dataclass
class EvidenceValidationResult:
    fields: dict[str, FieldEvidence]
    provenance: dict[str, dict[str, Any]]
    review_required: bool


def normalized_bbox_to_pixels(
    bbox_2d: list[int] | None, image_width: int, image_height: int
) -> BBox | None:
    """Convert [ymin,xmin,ymax,xmax] in 0..1000 to original-image pixels."""

    if (
        not bbox_2d
        or len(bbox_2d) != 4
        or image_width <= 0
        or image_height <= 0
    ):
        return None
    ymin, xmin, ymax, xmax = bbox_2d
    if not all(isinstance(value, int) and 0 <= value <= 1000 for value in bbox_2d):
        return None
    if ymax <= ymin or xmax <= xmin:
        return None
    left = max(0, min(image_width, round(xmin * image_width / 1000)))
    top = max(0, min(image_height, round(ymin * image_height / 1000)))
    right = max(0, min(image_width, round(xmax * image_width / 1000)))
    bottom = max(0, min(image_height, round(ymax * image_height / 1000)))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _clean_compare_text(value: str) -> str:
    return re.sub(r"[^a-z0-9@.+]", "", value.casefold())


def _decimal(value: str) -> Decimal | None:
    match = re.search(r"[0-9][0-9,]*(?:\.[0-9]+)?", value)
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def canonical_value(field: str, value: str | None) -> str | None:
    if not value:
        return None
    if field == "mrp":
        number = _decimal(value)
        return f"{number:.2f}" if number is not None else None
    if field == "net_quantity":
        match = re.search(
            r"([0-9]+(?:[.,][0-9]+)?)\s*(kg|gms?|gm|mg|g|ml|cl|l|units?|pcs?|pieces?)\b",
            value,
            re.I,
        )
        if not match:
            return None
        try:
            number = Decimal(match.group(1).replace(",", ".")).normalize()
        except InvalidOperation:
            return None
        unit_map = {
            "gm": "g",
            "gms": "g",
            "unit": "unit",
            "units": "unit",
            "pc": "piece",
            "pcs": "piece",
            "piece": "piece",
            "pieces": "piece",
        }
        unit = unit_map.get(match.group(2).lower(), match.group(2).lower())
        return f"{number} {unit}"
    if field == "consumer_care_contact":
        values = sorted(
            _clean_compare_text(part)
            for part in re.split(r"\s*[,;]\s*", value)
            if _clean_compare_text(part)
        )
        return "|".join(values) or None
    if field == "date_of_manufacture":
        clean = re.sub(r"\s+", " ", value.strip()).upper()
        normalized_separators = re.sub(r"[./]", "-", clean)
        for date_format in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d-%m-%y",
            "%d %b %Y",
            "%d %B %Y",
        ):
            try:
                return datetime.strptime(normalized_separators, date_format).strftime(
                    "%Y-%m-%d"
                )
            except ValueError:
                continue
        for date_format in ("%m-%Y", "%b %Y", "%B %Y"):
            try:
                return datetime.strptime(normalized_separators, date_format).strftime(
                    "%Y-%m"
                )
            except ValueError:
                continue
        return None
    return _clean_compare_text(value) or None


def values_equivalent(field: str, left: str | None, right: str | None) -> bool:
    return canonical_value(field, left) == canonical_value(field, right)


def validate_gemini_candidate(
    candidate: GeminiFieldCandidate,
) -> ValidatedGeminiCandidate | None:
    """Route visual text through LabelGuard's existing deterministic validators.

    The candidate's normalized value is deliberately not injected into the
    evidence line. Only the purported visible evidence is parsed, which keeps
    anchors, role separation, nutrition rejection, unit-price rejection,
    expiry separation and explicit COO requirements intact.
    """

    active_field = GEMINI_TO_ACTIVE_FIELD.get(candidate.field)
    if active_field is None or not candidate.readable:
        return None
    evidence_text = re.sub(
        r"\s+", " ", (candidate.evidence_text or candidate.raw_text or "")
    ).strip()
    if not evidence_text:
        return None
    if active_field.endswith("_address"):
        role = active_field.removesuffix("_address")
        anchors = {
            "manufacturer": r"\b(?:manufactured\s+by|manufacturer)\b",
            "packer": r"\b(?:packed\s+by|packer)\b",
            "marketer": r"\b(?:marketed\s+by|marketer)\b",
            "importer": r"\b(?:imported\s+by|importer)\b",
        }
        claimed_address = re.sub(
            r"\s+", " ", candidate.normalized_value or candidate.raw_text or ""
        ).strip(" ,;:-")
        address_key = _clean_compare_text(claimed_address)
        evidence_key = _clean_compare_text(evidence_text)
        looks_address_like = bool(
            re.search(r"\d", claimed_address)
            and re.search(
                r"(?i)\b(?:plot|road|street|lane|estate|area|sector|phase|floor|building|village|district|city|state|india|pin|pincode)\b",
                claimed_address,
            )
        )
        if (
            not claimed_address
            or not re.search(anchors[role], evidence_text, re.I)
            or not address_key
            or address_key not in evidence_key
            or not looks_address_like
        ):
            return None
        return ValidatedGeminiCandidate(
            active_field,
            candidate.field,
            claimed_address,
            candidate.model_score,
            candidate.bbox_2d,
            candidate.raw_text,
            evidence_text,
        )
    box: BBox = (0, 0, 1000, 100)
    token = OcrToken(
        evidence_text,
        candidate.model_score,
        box,
        block_id="gemini-validation",
        line_id="gemini-validation",
        source_pass="gemini-validation",
    )
    line = OcrLine(
        evidence_text,
        candidate.model_score,
        box,
        tokens=(token,),
        block_id="gemini-validation",
        line_id="gemini-validation",
        source_pass="gemini-validation",
    )
    validated = extract_fields([line]).get(active_field)
    if not validated or not validated.value:
        return None
    claimed = candidate.normalized_value or candidate.raw_text
    if claimed and not values_equivalent(active_field, validated.value, claimed):
        return None
    return ValidatedGeminiCandidate(
        active_field,
        candidate.field,
        validated.value,
        candidate.model_score,
        candidate.bbox_2d,
        candidate.raw_text,
        evidence_text,
    )


def _union_boxes(boxes: list[BBox | None]) -> BBox | None:
    valid = [box for box in boxes if box is not None]
    if not valid:
        return None
    return (
        min(box[0] for box in valid),
        min(box[1] for box in valid),
        max(box[2] for box in valid),
        max(box[3] for box in valid),
    )


def _all_valid_candidates(
    response: GeminiExtractionResponse | None,
) -> tuple[dict[str, list[ValidatedGeminiCandidate]], dict[str, list[dict[str, Any]]]]:
    valid: dict[str, list[ValidatedGeminiCandidate]] = {}
    rejected: dict[str, list[dict[str, Any]]] = {}
    if response is None:
        return valid, rejected
    for candidate in response.fields:
        active_field = GEMINI_TO_ACTIVE_FIELD.get(candidate.field)
        if active_field is None:
            continue
        checked = validate_gemini_candidate(candidate)
        if checked:
            valid.setdefault(active_field, []).append(checked)
        else:
            rejected.setdefault(active_field, []).append(
                {
                    "field": candidate.field,
                    "raw_text": candidate.raw_text,
                    "reason": "rejected_by_deterministic_field_validator",
                }
            )
    return valid, rejected


def accept_gemini_evidence(
    response: GeminiExtractionResponse,
    image_width: int,
    image_height: int,
) -> EvidenceValidationResult:
    """Accept one Gemini scan only after deterministic field validation.

    Gemini supplies visible text candidates and approximate geometry.  It does
    not decide which candidate is a statutory declaration.  Missing geometry,
    semantic-validator failures, and conflicting values fail closed.  Valid
    phone/email/web/address channels may be combined because they are all
    evidence for the single consumer-care rule.
    """

    grouped, rejected = _all_valid_candidates(response)
    final: dict[str, FieldEvidence] = {}
    provenance: dict[str, dict[str, Any]] = {}
    review_required = False
    unreadable = response.image_readability == "unreadable"

    for field in FIELD_NAMES:
        candidates = list(grouped.get(field, []))
        # A visible manufacture date is more specific than a packing date for
        # the API's legacy date_of_manufacture field.  Packing date remains a
        # valid fallback when no manufacture-date candidate is present.
        if field == "date_of_manufacture":
            manufacturing = [item for item in candidates if item.source_field == "manufacture_date"]
            if manufacturing:
                candidates = manufacturing

        located: list[tuple[ValidatedGeminiCandidate, BBox]] = []
        for item in candidates:
            box = normalized_bbox_to_pixels(item.bbox_2d, image_width, image_height)
            if box is None:
                rejected.setdefault(field, []).append(
                    {
                        "field": item.source_field,
                        "raw_text": item.raw_text,
                        "reason": "missing_or_invalid_evidence_bbox",
                    }
                )
                continue
            located.append((item, box))

        accepted: FieldEvidence
        state: VerificationState
        accepted_source: str | None = None
        field_review = bool(rejected.get(field))
        model_values = [item.value for item, _ in located]

        if field == "consumer_care_contact" and located:
            unique: dict[str, tuple[ValidatedGeminiCandidate, BBox]] = {}
            for item, box in located:
                key = canonical_value(field, item.value) or _clean_compare_text(item.value)
                current = unique.get(key)
                if current is None or item.model_score > current[0].model_score:
                    unique[key] = (item, box)
            selected = list(unique.values())
            accepted = FieldEvidence(
                ", ".join(item.value for item, _ in selected),
                round(min(0.95, min(item.model_score for item, _ in selected)), 3),
                _union_boxes([box for _, box in selected]),
            )
            state = "GEMINI_VALIDATED"
            accepted_source = "GEMINI_DETERMINISTICALLY_VALIDATED"
        elif located:
            by_value: dict[str, list[tuple[ValidatedGeminiCandidate, BBox]]] = {}
            for item, box in located:
                key = canonical_value(field, item.value) or _clean_compare_text(item.value)
                by_value.setdefault(key, []).append((item, box))
            if len(by_value) > 1:
                accepted = FieldEvidence(None, 0.0, _union_boxes([box for _, box in located]))
                state = "CONFLICT"
                field_review = True
            else:
                selected = max(located, key=lambda pair: pair[0].model_score)
                item, box = selected
                accepted = FieldEvidence(
                    item.value,
                    round(min(0.95, item.model_score), 3),
                    box,
                )
                state = "GEMINI_VALIDATED"
                accepted_source = "GEMINI_DETERMINISTICALLY_VALIDATED"
        else:
            accepted = FieldEvidence(None, 0.0, None)
            state = "UNREADABLE" if unreadable else "MISSING"

        final[field] = accepted
        review_required = review_required or field_review
        provenance[field] = {
            "gemini_value": accepted.value if accepted_source else (model_values[0] if len(model_values) == 1 else None),
            "gemini_values": model_values,
            "gemini_model_score": accepted.confidence if accepted_source else None,
            "verification_state": state,
            "verification_source": accepted_source or state,
            "accepted_source": accepted_source,
            "review_required": field_review,
            "rejected_candidates": rejected.get(field, []),
        }

    return EvidenceValidationResult(final, provenance, review_required)

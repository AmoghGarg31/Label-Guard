"""LabelGuard FastAPI service."""

import logging
import os
import csv
import hashlib
import io
import json
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv


# Load only the backend-local environment file. Existing process/hosting
# variables win, and frontend environment files are never consulted.
load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

from database import (
    REPORT_DIR,
    UPLOAD_DIR,
    database_health,
    get_audit_events,
    get_field_corrections,
    get_gemini_cache,
    get_inspection,
    get_latest_review,
    initialize_database,
    list_inspections,
    save_audit_event,
    save_field_correction,
    save_gemini_cache,
    save_inspection,
    save_review,
    update_inspection_findings,
)
from evidence import draw_evidence
from evidence_reconciler import accept_gemini_evidence
from extractor import (
    format_extracted_fields,
    values_only,
)
from gemini_vision import (
    GEMINI_SCHEMA_VERSION,
    GeminiCallResult,
    GeminiExtractionResponse,
    GeminiVisionService,
)
from image_quality import (
    ImageValidationError,
    analyze_image_quality,
    validate_image_payload,
)
from models import BBox, FieldEvidence
from report import build_pdf
from rules import RULE_ENGINE_VERSION, evaluate_rules, load_rules, overall_status


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("labelguard")

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

EXTRACTED_FIELD_NAMES = (
    "common_or_generic_name",
    "manufacturer_name",
    "manufacturer_address",
    "packer_name",
    "packer_address",
    "importer_name",
    "importer_address",
    "marketer_name",
    "marketer_address",
    "net_quantity",
    "mrp",
    "date_of_manufacture",
    "consumer_care_contact",
    "country_of_origin",
)
GEMINI = GeminiVisionService()
RULES = load_rules()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    port = os.environ.get("PORT", "8000")
    logger.info("LabelGuard API listening on 0.0.0.0:%s", port)
    yield

app = FastAPI(
    title="LabelGuard API",
    version="1.0.0",
    description=(
        "A cautious packaged-commodity label screening prototype. "
        "Automated results are not legal certification."
    ),
    lifespan=lifespan,
)

_upload_attempts: dict[str, deque[float]] = defaultdict(deque)
UPLOAD_RATE_LIMIT = max(1, int(os.getenv("UPLOAD_RATE_LIMIT_PER_MINUTE", "30")))

def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins if origins else ["http://localhost:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.middleware("http")
async def security_and_abuse_controls(request: Request, call_next):
    request_id = str(uuid4())
    if request.method == "POST" and request.url.path in {"/inspect", "/api/inspect"}:
        client_key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        attempts = _upload_attempts[client_key]
        while attempts and now - attempts[0] > 60:
            attempts.popleft()
        if len(attempts) >= UPLOAD_RATE_LIMIT:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many inspection uploads. Try again in one minute."},
            )
            response.headers["Retry-After"] = "60"
        else:
            attempts.append(now)
            response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith(("/inspection", "/api/inspection", "/report", "/api/report")):
        response.headers["Cache-Control"] = "no-store"
    return response


class ExtractedField(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: list[int] | None = None
    source: Literal["ocr", "gemini", "human_correction"] = "gemini"


class Finding(BaseModel):
    rule_id: str
    field: str
    status: Literal["PASS", "FAIL", "UNCERTAIN"]
    severity: Literal["MAJOR", "MINOR"]
    confidence: float = Field(ge=0, le=1)
    bounding_box: list[int]
    description: str
    source_citation: str = ""
    rule_version: str = "1.0"
    applicability: Literal["applicable", "unknown"] = "applicable"


class InspectionResponse(BaseModel):
    id: int
    overall_status: Literal[
        "compliant", "potential_non_compliance", "manual_review_required"
    ]
    extracted_fields: dict[str, ExtractedField]
    findings: list[Finding]
    rule_engine_version: str = RULE_ENGINE_VERSION
    quality: dict[str, Any]
    ocr_engine: str
    orientation_degrees: Literal[0, 90, 180, 270] = 0
    image_url: str
    context: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    gemini_status: dict[str, Any] = Field(default_factory=dict)
    ai_summary: str = ""
    recommendation: list[str] = Field(default_factory=list)
    performance: dict[str, Any] = Field(default_factory=dict)


class RuleInfo(BaseModel):
    rule_id: str
    field: str
    source_citation: str
    description: str
    severity: Literal["MAJOR", "MINOR"]
    confidence_floor: float
    check_type: str
    rule_version: str
    applicability: str = "all_packages"
    legal_verification_required: bool = True


class HistoryItem(BaseModel):
    id: int
    original_filename: str
    created_at: str
    overall_status: str
    quality_status: str
    ocr_engine: str
    review_status: str = "NOT_REVIEWED"
    package_scope: str = "unknown"


class ReviewRequest(BaseModel):
    review_status: Literal[
        "NOT_REVIEWED",
        "VERIFIED",
        "CORRECTION_REQUIRED",
        "VIOLATION_CONFIRMED",
        "REINSPECTION_REQUIRED",
    ]
    reviewed_by: str = Field(default="Inspector", min_length=1, max_length=120)
    review_notes: str | None = Field(default=None, max_length=2000)


class FieldCorrectionRequest(BaseModel):
    field: str = Field(min_length=1, max_length=80)
    corrected_text: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)
    actor: str = Field(default="Inspector", min_length=1, max_length=120)


class ReviewInfo(BaseModel):
    review_status: str = "NOT_REVIEWED"
    reviewed_by: str | None = None
    review_notes: str | None = None
    reviewed_at: str | None = None


class FieldCorrectionInfo(BaseModel):
    id: int
    field: str
    original_text: str
    corrected_text: str
    reason: str
    actor: str
    created_at: str


class AuditEventInfo(BaseModel):
    id: int
    event_type: str
    description: str
    actor: str
    created_at: str


class InspectionDetail(InspectionResponse):
    original_filename: str
    mime_type: str | None
    file_size_bytes: int
    created_at: str
    ocr_text: str
    evidence_filename: str | None
    report_url: str
    review: ReviewInfo = Field(default_factory=ReviewInfo)
    corrections: list[FieldCorrectionInfo] = Field(default_factory=list)
    audit_trail: list[AuditEventInfo] = Field(default_factory=list)
    original_overall_status: str | None = None


def _union_boxes(*boxes: BBox | None) -> BBox | None:
    valid = [box for box in boxes if box is not None]
    if not valid:
        return None
    return (
        min(box[0] for box in valid),
        min(box[1] for box in valid),
        max(box[2] for box in valid),
        max(box[3] for box in valid),
    )


def _combined_manufacturer_evidence(
    fields: dict[str, FieldEvidence],
) -> FieldEvidence:
    name = fields.get("manufacturer_name", FieldEvidence(None, 0, None))
    address = fields.get("manufacturer_address", FieldEvidence(None, 0, None))
    if not name.value or not address.value:
        return FieldEvidence(
            None,
            min(name.confidence, address.confidence),
            _union_boxes(name.bounding_box, address.bounding_box),
        )
    return FieldEvidence(
        f"{name.value}, {address.value}",
        min(name.confidence, address.confidence),
        _union_boxes(name.bounding_box, address.bounding_box),
    )


def _combined_responsible_party_evidence(
    fields: dict[str, FieldEvidence],
) -> FieldEvidence:
    candidates: list[FieldEvidence] = []
    for role in ("manufacturer", "packer", "importer", "marketer"):
        name = fields.get(f"{role}_name", FieldEvidence(None, 0, None))
        address = fields.get(f"{role}_address", FieldEvidence(None, 0, None))
        if name.value and address.value:
            candidates.append(
                FieldEvidence(
                    f"{name.value}, {address.value}",
                    min(name.confidence, address.confidence),
                    _union_boxes(name.bounding_box, address.bounding_box),
                )
            )
    if candidates:
        return max(candidates, key=lambda evidence: evidence.confidence)
    return _combined_manufacturer_evidence(fields)


def _inspection_response(record: dict[str, Any]) -> InspectionResponse:
    raw_extracted = record.get("extracted_fields", {})
    extracted: dict[str, ExtractedField] = {}
    for k, v in raw_extracted.items():
        if isinstance(v, dict):
            extracted[k] = ExtractedField(
                text=str(v.get("text") or ""),
                confidence=round(float(v.get("confidence", 0.0)), 3),
                bounding_box=(
                    [int(value) for value in v.get("bounding_box")]
                    if _is_valid_box(v.get("bounding_box"))
                    else None
                ),
                source=(
                    "human_correction"
                    if v.get("source") == "human_correction"
                    else ("gemini" if v.get("source") == "gemini" else "ocr")
                ),
            )
        elif isinstance(v, str):
            extracted[k] = ExtractedField(text=v, confidence=0.8)
        else:
            extracted[k] = ExtractedField(text="", confidence=0.0)

    raw_findings = record.get("findings", [])
    findings: list[Finding] = []
    for f in raw_findings:
        raw_sev = f.get("severity")
        if str(raw_sev).upper() in ("MAJOR", "HIGH", "CRITICAL") or raw_sev is None:
            sev = "MAJOR"
        else:
            sev = "MINOR"
        raw_bbox = f.get("bounding_box")
        if not raw_bbox or len(raw_bbox) != 4:
            bbox = [0, 0, 0, 0]
        else:
            bbox = [int(raw_bbox[0]), int(raw_bbox[1]), int(raw_bbox[2]), int(raw_bbox[3])]
        findings.append(
            Finding(
                rule_id=str(f.get("rule_id", "")),
                field=str(f.get("field", "")),
                status=f.get("status", "UNCERTAIN"),
                severity=sev,
                confidence=round(float(f.get("confidence", 0.0)), 3),
                bounding_box=bbox,
                description=str(f.get("description", "")),
                source_citation=str(f.get("source_citation", "")),
                rule_version=str(f.get("rule_version", "1.0")),
                applicability=("unknown" if f.get("applicability") == "unknown" else "applicable"),
            )
        )

    return InspectionResponse(
        id=int(record["id"]),
        overall_status=record["overall_status"],
        extracted_fields=extracted,
        findings=findings,
        rule_engine_version=str(record.get("rule_engine_version") or RULE_ENGINE_VERSION),
        quality=record.get("quality", {}),
        ocr_engine=str(record.get("ocr_engine", "unknown")),
        orientation_degrees=int(record.get("orientation_degrees", 0)),
        image_url=f"/api/inspection/{record['id']}/image",
        context=record.get("context", {}),
        verification=record.get("verification", {}),
        gemini_status=record.get("gemini_status", {}),
        ai_summary=str(record.get("ai_summary") or ""),
        recommendation=[str(item) for item in record.get("recommendation", [])],
        performance=record.get("performance", {}),
    )


def _detail_response(record: dict[str, Any]) -> InspectionDetail:
    response = _inspection_response(record)
    insp_id = str(record["id"])
    review = get_latest_review(insp_id)
    corrections = get_field_corrections(insp_id)
    audit_trail = get_audit_events(insp_id)

    review_info = ReviewInfo(**review) if review else ReviewInfo(review_status="NOT_REVIEWED")
    corrections_info = [
        FieldCorrectionInfo(
            id=c["id"],
            field=c["field"],
            original_text=c.get("original_text") or "",
            corrected_text=c["corrected_text"],
            reason=c.get("reason") or "",
            actor=c.get("actor") or "Inspector",
            created_at=c["created_at"],
        )
        for c in corrections
    ]
    audit_info = [
        AuditEventInfo(
            id=a["id"],
            event_type=a["event_type"],
            description=a["description"],
            actor=a["actor"],
            created_at=a["created_at"],
        )
        for a in audit_trail
    ]

    return InspectionDetail(
        **response.model_dump(),
        original_filename=record["original_filename"],
        mime_type=record.get("mime_type"),
        file_size_bytes=record["file_size_bytes"],
        created_at=record["created_at"],
        ocr_text=record.get("ocr_text", ""),
        evidence_filename=record.get("evidence_filename"),
        report_url=f"/api/report/{record['id']}",
        review=review_info,
        corrections=corrections_info,
        audit_trail=audit_info,
        original_overall_status=record.get("original_overall_status") or record["overall_status"],
    )


def _is_valid_box(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > value[0]
        and value[3] > value[1]
    )


def _stored_suffix(filename: str | None, mime_type: str | None) -> str:
    mime_suffix = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(mime_type or "")
    if mime_suffix:
        return mime_suffix
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        return suffix
    return ".bin"


def _safe_original_filename(filename: str | None) -> str:
    clean = re.sub(r"[\x00-\x1f\x7f]+", "", Path(filename or "unnamed-image").name).strip()
    return (clean or "unnamed-image")[:180]


def _safe_media_path(filename: str | None) -> Path | None:
    if not filename or Path(filename).name != filename:
        return None
    candidate = (UPLOAD_DIR / filename).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if candidate.parent != upload_root or not candidate.is_file():
        return None
    return candidate


def _deterministic_explanation(
    status: str, findings: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    failed = [finding for finding in findings if finding.get("status") == "FAIL"]
    uncertain = [finding for finding in findings if finding.get("status") == "UNCERTAIN"]
    if status == "potential_non_compliance":
        fields = ", ".join(dict.fromkeys(str(item.get("field", "declaration")) for item in failed))
        explanation = (
            f"The deterministic LabelGuard rules identified {len(failed)} potential "
            f"non-compliance finding(s), affecting {fields or 'the checked declarations'}. "
            "This is an automated screening result, not legal certification; the cited "
            "evidence should be verified by an inspector."
        )
        recommendation = [
            "Review every failed declaration against the highlighted source region.",
            "Correct extracted text only after checking it directly on the package image.",
            "Record the inspector decision and supporting notes in the review section.",
        ]
    elif status == "manual_review_required":
        fields = ", ".join(
            dict.fromkeys(str(item.get("field", "declaration")) for item in uncertain)
        )
        explanation = (
            f"The deterministic screening requires manual review because {len(uncertain)} "
            f"finding(s) remain uncertain, including {fields or 'one or more declarations'}. "
            "An uncertain item is not a confirmed violation and should be checked against "
            "the original package image."
        )
        recommendation = [
            "Review each uncertain declaration and its highlighted evidence region.",
            "Capture a closer, straighter image if the declaration remains unreadable.",
            "Confirm or correct the field before relying on the screening result.",
        ]
    else:
        explanation = (
            "The configured deterministic rules found no failed or uncertain applicable "
            "declaration in the accepted evidence. This is a screening outcome only and "
            "does not constitute government approval or legal certification."
        )
        recommendation = [
            "Retain the image and evidence report with the inspection record.",
            "Verify any category-specific requirements outside the configured rule set.",
            "Record an inspector review before using the result for formal action.",
        ]
    return explanation, recommendation


def _explanation_is_consistent(explanation: str, status: str) -> bool:
    text = re.sub(r"\s+", " ", explanation).casefold()
    if status == "compliant":
        return not any(
            phrase in text
            for phrase in ("is non-compliant", "is not compliant", "failed compliance")
        )
    if status == "potential_non_compliance":
        return not any(
            phrase in text
            for phrase in ("is fully compliant", "all requirements passed", "no issue was found")
        )
    return not any(
        phrase in text
        for phrase in ("is fully compliant", "confirmed non-compliant", "confirmed violation")
    )


def _gemini_visual_result(
    image_bytes: bytes,
    mime_type: str,
    quality: dict[str, Any],
    routing_hint: Literal["standard", "difficult"],
) -> tuple[GeminiCallResult, str]:
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    if GEMINI.config.enabled and GEMINI.config.api_key:
        route = (
            GEMINI.route_models(routing_hint)
            if hasattr(GEMINI, "route_models")
            else [GEMINI.config.model]
        )
        for model in route:
            try:
                cached = get_gemini_cache(image_hash, model, GEMINI_SCHEMA_VERSION)
                if cached and cached.get("status") == "success" and cached.get("result"):
                    response = GeminiExtractionResponse.model_validate(cached["result"])
                    return (
                        GeminiCallResult(
                            "success",
                            model,
                            GEMINI_SCHEMA_VERSION,
                            str(cached.get("created_at") or datetime.now(timezone.utc).isoformat()),
                            response=response,
                            duration_ms=float(cached.get("duration_ms") or 0),
                            attempts=0,
                            cache_hit=True,
                            route_reason=(
                                "difficult_image" if routing_hint == "difficult" else "standard_image"
                            ),
                            routed_models=route,
                        ),
                        image_hash,
                    )
            except Exception as exc:
                logger.info("Gemini cache lookup ignored safely: %s", exc)

    try:
        # Exactly one visual reader receives the original package image.  No
        # local OCR scan or OCR corroboration is performed by the upload path.
        result = GEMINI.extract(
            image_bytes,
            mime_type,
            routing_hint=routing_hint,
        )
    except Exception as exc:
        logger.info("Gemini visual verification failed safely: %s", exc)
        result = GeminiCallResult(
            "unavailable",
            GEMINI.config.model,
            GEMINI_SCHEMA_VERSION,
            datetime.now(timezone.utc).isoformat(),
            error=f"{type(exc).__name__}: visual verification unavailable"[:240],
        )
    if result.successful:
        try:
            save_gemini_cache(
                image_hash,
                result.model,
                result.schema_version,
                result.created_at,
                result.status,
                result.response.model_dump(mode="json") if result.response else None,
                result.error,
                result.duration_ms,
            )
        except Exception as exc:
            logger.info("Gemini cache write ignored safely: %s", exc)
    return result, image_hash


def _run_gemini_only_pipeline(
    image_bytes: bytes, context: dict[str, Any], mime_type: str
) -> dict[str, Any]:
    started = time.perf_counter()
    quality = analyze_image_quality(image_bytes)
    if not quality.get("is_decodable"):
        raise HTTPException(status_code=422, detail="The image could not be decoded.")
    quality_ms = (time.perf_counter() - started) * 1000
    routing_hint: Literal["standard", "difficult"] = (
        "difficult"
        if quality.get("status") != "good"
        or not quality.get("contrast_ok", True)
        or not quality.get("blur_ok", True)
        or not quality.get("glare_ok", True)
        else "standard"
    )

    gemini_result, image_hash = _gemini_visual_result(
        image_bytes, mime_type, quality, routing_hint
    )
    if not gemini_result.successful:
        if gemini_result.status == "rate_limited":
            raise HTTPException(
                status_code=429,
                detail="Gemini extraction rate limit reached. Retry after the indicated interval.",
                headers={"Retry-After": str(max(1, gemini_result.retry_after_seconds))},
            )
        if gemini_result.status in {"disabled", "not_configured"}:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Gemini-only extraction is not configured. Set GEMINI_ENABLED=true "
                    "and configure GEMINI_API_KEY in backend/.env."
                ),
            )
        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini could not produce a schema-valid extraction. "
                "No OCR fallback was used; retry or review the backend Gemini configuration."
            ),
        )

    width = int(quality.get("width") or 0)
    height = int(quality.get("height") or 0)
    validation_started = time.perf_counter()
    accepted = accept_gemini_evidence(gemini_result.response, width, height)
    validation_ms = (time.perf_counter() - validation_started) * 1000

    fields_for_rules = dict(accepted.fields)
    fields_for_rules["responsible_party_name_and_address"] = (
        _combined_responsible_party_evidence(accepted.fields)
    )
    transcript_lines = list(
        dict.fromkeys(
            re.sub(r"\s+", " ", candidate.evidence_text or candidate.raw_text or "").strip()
            for candidate in gemini_result.response.fields
            if (candidate.evidence_text or candidate.raw_text or "").strip()
        )
    )
    rules_started = time.perf_counter()
    findings = evaluate_rules(fields_for_rules, RULES, context)
    status = overall_status(findings, quality, len(transcript_lines))
    rules_ms = (time.perf_counter() - rules_started) * 1000

    fallback_summary, fallback_recommendation = _deterministic_explanation(
        status, findings
    )
    ai_summary = fallback_summary
    recommendation = fallback_recommendation
    explanation_status = "deterministic_fallback"
    explanation_duration_ms = 0.0
    explanation_error: str | None = None
    if gemini_result.successful:
        authoritative_facts = {
            "overall_status": status,
            "findings": [
                {
                    "rule_id": item.get("rule_id"),
                    "field": item.get("field"),
                    "status": item.get("status"),
                    "description": item.get("description"),
                    "source_citation": item.get("source_citation"),
                }
                for item in findings
            ],
            "accepted_extracted_declarations": values_only(accepted.fields),
            "review_required": accepted.review_required,
        }
        explanation = GEMINI.explain(authoritative_facts)
        explanation_duration_ms = explanation.duration_ms
        explanation_error = explanation.error
        if (
            explanation.status == "success"
            and explanation.explanation
            and _explanation_is_consistent(explanation.explanation, status)
        ):
            ai_summary = explanation.explanation
            recommendation = explanation.recommendation
            explanation_status = "gemini_generated"
        elif explanation.status == "success":
            explanation_status = "deterministic_fallback_inconsistent_ai_output"
        else:
            explanation_status = f"deterministic_fallback_{explanation.status}"

    gemini_status = {
        **GEMINI.status(),
        **gemini_result.metadata(),
        "image_sha256": image_hash,
        "image_readability": (
            gemini_result.response.image_readability
            if gemini_result.response
            else None
        ),
        "distortion_types": (
            gemini_result.response.distortion_types if gemini_result.response else []
        ),
        "candidate_count": (
            len(gemini_result.response.fields) if gemini_result.response else 0
        ),
        "extraction_mode": "gemini_only",
        "deterministic_validation": True,
        "explanation_status": explanation_status,
        "explanation_error": explanation_error,
    }
    performance = {
        "image_quality_ms": round(quality_ms, 1),
        "gemini_visual_ms": round(gemini_result.duration_ms, 1),
        "deterministic_evidence_validation_ms": round(validation_ms, 1),
        "deterministic_rules_ms": round(rules_ms, 1),
        "gemini_explanation_ms": round(explanation_duration_ms, 1),
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    return {
        "quality": quality,
        "findings": findings,
        "status": status,
        "engine": f"gemini-vision/{gemini_result.model}",
        # Kept under the legacy database/API key for backward compatibility.
        # It contains Gemini's visible evidence transcript, not OCR output.
        "ocr_text": "\n".join(transcript_lines),
        "orientation": 0,
        "fields": accepted.fields,
        "verification": {
            "status": "deterministically_validated",
            "reader": "gemini_vision",
            "review_required": accepted.review_required,
            "fields": accepted.provenance,
        },
        "gemini_status": gemini_status,
        "ai_summary": ai_summary,
        "recommendation": recommendation,
        "performance": performance,
    }


@app.post("/inspect", response_model=InspectionResponse, status_code=201, tags=["inspections"])
@app.post("/api/inspect", response_model=InspectionResponse, status_code=201, include_in_schema=False)
async def inspect_image(
    image: Annotated[UploadFile, File(description="Packaged-commodity label image")],
    package_scope: Annotated[Literal["unknown", "domestic", "imported"], Form()] = "unknown",
    commodity_category: Annotated[str | None, Form(max_length=120)] = None,
) -> InspectionResponse:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload an image file.")
    contents = await image.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded image is empty.")
    if len(contents) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Uploaded file exceeds the maximum allowed size of 10 MB.",
        )
    try:
        validated = validate_image_payload(contents)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    context = {
        "package_scope": package_scope,
        "commodity_category": (commodity_category or "").strip()[:120] or None,
    }
    pipeline = _run_gemini_only_pipeline(contents, context, validated["mime_type"])
    quality = pipeline["quality"]
    findings = pipeline["findings"]
    status = pipeline["status"]
    engine = pipeline["engine"]
    ocr_text = pipeline["ocr_text"]
    orientation = pipeline["orientation"]
    fields = pipeline["fields"]
    inspection_uuid = str(uuid4())
    safe_original_filename = _safe_original_filename(image.filename)
    suffix = _stored_suffix(image.filename, validated["mime_type"])
    stored_filename = f"{inspection_uuid}{suffix}"
    evidence_filename = f"{inspection_uuid}-evidence.png"
    stored_path = UPLOAD_DIR / stored_filename
    evidence_path = UPLOAD_DIR / evidence_filename
    stored_path.write_bytes(contents)
    evidence_bytes = draw_evidence(contents, findings)
    if evidence_bytes:
        evidence_path.write_bytes(evidence_bytes)
    else:
        evidence_filename = None

    record = {
        "uuid": inspection_uuid,
        "id": inspection_uuid,
        "original_filename": safe_original_filename,
        "stored_filename": stored_filename,
        "mime_type": validated["mime_type"],
        "file_size_bytes": len(contents),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": status,
        "extracted_fields": format_extracted_fields(fields, source="gemini"),
        "findings": findings,
        "quality": quality,
        "ocr_engine": engine,
        "ocr_text": ocr_text,
        "evidence_filename": evidence_filename,
        "processing_error": None,
        "rule_engine_version": RULE_ENGINE_VERSION,
        "context": context,
        "orientation_degrees": orientation,
        "verification": pipeline["verification"],
        "gemini_status": pipeline["gemini_status"],
        "ai_summary": pipeline["ai_summary"],
        "recommendation": pipeline["recommendation"],
        "performance": pipeline["performance"],
    }
    try:
        numeric_id = save_inspection(record)
        record["id"] = numeric_id
        save_audit_event(
            str(numeric_id),
            "INSPECTION_CREATED",
            f"Uploaded file '{safe_original_filename}' ({len(contents)} bytes)",
            "SYSTEM_PIPELINE",
            record["created_at"],
        )
        save_audit_event(
            str(numeric_id),
            "IMAGE_QUALITY_COMPLETED",
            f"Deterministic image-quality analysis completed with status '{quality.get('status', 'unknown')}'.",
            "SYSTEM_PIPELINE",
            record["created_at"],
        )
        save_audit_event(
            str(numeric_id),
            (
                "GEMINI_EXTRACTION_COMPLETED"
                if pipeline["gemini_status"].get("status") == "success"
                else "GEMINI_EXTRACTION_UNAVAILABLE"
            ),
            (
                f"Gemini-only visual extraction completed with model '{pipeline['gemini_status'].get('model', 'unknown')}' and returned {len(ocr_text.splitlines())} evidence lines."
                if pipeline["gemini_status"].get("status") == "success"
                else f"Required Gemini extraction status: {pipeline['gemini_status'].get('status', 'unavailable')}. No OCR fallback was used."
            ),
            "SYSTEM_PIPELINE",
            record["created_at"],
        )
        save_audit_event(
            str(numeric_id),
            "EVIDENCE_VALIDATED",
            f"Deterministic field validators checked Gemini evidence; manual review flag is {pipeline['verification'].get('review_required', False)}.",
            "SYSTEM_PIPELINE",
            record["created_at"],
        )
        save_audit_event(
            str(numeric_id),
            "RULES_EVALUATED",
            f"Deterministic rule engine evaluated {len(findings)} statutory findings. Initial verdict: {status}",
            "SYSTEM_PIPELINE",
            record["created_at"],
        )
        save_audit_event(
            str(numeric_id),
            "AI_EXPLANATION_GENERATED",
            f"Explanation status: {pipeline['gemini_status'].get('explanation_status', 'deterministic_fallback')}. The deterministic verdict was already complete.",
            "SYSTEM_PIPELINE",
            record["created_at"],
        )
    except Exception:
        stored_path.unlink(missing_ok=True)
        evidence_path.unlink(missing_ok=True)
        logger.exception("Could not save inspection %s", inspection_uuid)
        raise HTTPException(status_code=500, detail="Could not save inspection.")

    logger.info(
        "Inspection %s (numeric id=%d) completed with status=%s using %s",
        inspection_uuid,
        numeric_id,
        status,
        engine,
    )
    return _inspection_response(record)


@app.post("/inspection/{inspection_id}/review", response_model=dict[str, Any], tags=["inspections"])
@app.post("/api/inspection/{inspection_id}/review", response_model=dict[str, Any], include_in_schema=False)
def review_inspection(inspection_id: int, payload: ReviewRequest) -> dict[str, Any]:
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    now_iso = datetime.now(timezone.utc).isoformat()
    rev = save_review(
        str(inspection_id),
        payload.review_status,
        payload.reviewed_by or "Inspector",
        payload.review_notes,
        now_iso,
    )
    save_audit_event(
        str(inspection_id),
        "REVIEW_UPDATED",
        f"Inspector review status updated to '{payload.review_status}' by {payload.reviewed_by or 'Inspector'}. Notes: {payload.review_notes or 'None'}",
        payload.reviewed_by or "Inspector",
        now_iso,
    )
    return {
        "status": "ok",
        "review": rev,
        "audit_trail": get_audit_events(str(inspection_id)),
    }


@app.post("/inspection/{inspection_id}/correct", response_model=InspectionDetail, tags=["inspections"])
@app.post("/api/inspection/{inspection_id}/correct", response_model=InspectionDetail, include_in_schema=False)
def correct_field(inspection_id: int, payload: FieldCorrectionRequest) -> InspectionDetail:
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    field = payload.field.strip()
    corrected_text = payload.corrected_text.strip()
    reason = payload.reason.strip()
    actor = (payload.actor or "Inspector").strip()
    if field not in EXTRACTED_FIELD_NAMES:
        raise HTTPException(status_code=400, detail="The requested field is not correctable.")
    if not corrected_text:
        raise HTTPException(status_code=400, detail="Corrected text cannot be empty.")

    now_iso = datetime.now(timezone.utc).isoformat()
    old_fields = record.get("extracted_fields", {})
    original_field_obj = old_fields.get(field, {})
    original_text = original_field_obj.get("text", "") if isinstance(original_field_obj, dict) else str(original_field_obj)

    # 1. Save field correction
    save_field_correction(
        str(inspection_id),
        field,
        original_text,
        corrected_text,
        reason,
        actor,
        now_iso,
    )

    # 2. Build updated extracted fields
    updated_extracted = dict(old_fields)
    original_box = original_field_obj.get("bounding_box") if isinstance(original_field_obj, dict) else None
    updated_extracted[field] = {
        "text": corrected_text,
        "confidence": 1.0,
        "bounding_box": original_box if _is_valid_box(original_box) else None,
        "source": "human_correction",
    }

    # 3. Construct FieldEvidence dictionary for rules evaluation
    fields_for_rules: dict[str, FieldEvidence] = {}
    for f_name in EXTRACTED_FIELD_NAMES:
        f_obj = updated_extracted.get(f_name, {})
        val = f_obj.get("text") if isinstance(f_obj, dict) else str(f_obj or "")
        conf = float(f_obj.get("confidence", 0.0)) if isinstance(f_obj, dict) else 0.0
        raw_box = f_obj.get("bounding_box") if isinstance(f_obj, dict) else None
        fields_for_rules[f_name] = FieldEvidence(
            value=val if val else None,
            confidence=conf,
            bounding_box=tuple(int(value) for value in raw_box) if _is_valid_box(raw_box) else None,
        )

    fields_for_rules["responsible_party_name_and_address"] = _combined_responsible_party_evidence(fields_for_rules)

    # 4. Call deterministic rule engine!
    new_findings = evaluate_rules(fields_for_rules, RULES, record.get("context", {}))
    quality = record.get("quality", {})
    evidence_line_count = len((record.get("ocr_text") or "").splitlines())
    new_status = overall_status(new_findings, quality, evidence_line_count)

    # 5. Persist updated findings and status
    updated_verification = dict(record.get("verification", {}))
    verification_fields = dict(updated_verification.get("fields", {}))
    field_provenance = dict(verification_fields.get(field, {}))
    field_provenance.update(
        {
            "verification_state": "MANUALLY_CORRECTED",
            "verification_source": "MANUALLY_CORRECTED",
            "accepted_source": "HUMAN_CORRECTION",
            "review_required": False,
        }
    )
    verification_fields[field] = field_provenance
    updated_verification["fields"] = verification_fields
    new_summary, new_recommendation = _deterministic_explanation(
        new_status, new_findings
    )
    updated_gemini_status = dict(record.get("gemini_status", {}))
    updated_gemini_status["explanation_status"] = (
        "deterministic_fallback_after_human_correction"
    )
    updated_gemini_status["explanation_error"] = None
    update_inspection_findings(
        str(inspection_id),
        updated_extracted,
        new_findings,
        new_status,
        updated_verification,
        new_summary,
        new_recommendation,
        updated_gemini_status,
    )

    original_image_path = _safe_media_path(record.get("stored_filename"))
    evidence_path = _safe_media_path(record.get("evidence_filename"))
    if original_image_path and evidence_path:
        evidence_bytes = draw_evidence(original_image_path.read_bytes(), new_findings)
        if evidence_bytes:
            evidence_path.write_bytes(evidence_bytes)

    # 6. Save audit events
    save_audit_event(
        str(inspection_id),
        "FIELD_CORRECTED",
        f"Field '{field}' corrected from '{original_text}' to '{corrected_text}'. Reason: {reason}",
        actor,
        now_iso,
    )
    save_audit_event(
        str(inspection_id),
        "RULES_RE_EVALUATED",
        f"Deterministic rule engine re-evaluated compliance after correction: status changed from '{record['overall_status']}' to '{new_status}'",
        "SYSTEM_PIPELINE",
        now_iso,
    )

    updated_record = get_inspection(inspection_id)
    return _detail_response(updated_record)


@app.get("/inspection/{inspection_id}/audit", tags=["inspections"])
@app.get("/api/inspection/{inspection_id}/audit", include_in_schema=False)
def get_audit(inspection_id: int) -> dict[str, Any]:
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return {
        "inspection_id": inspection_id,
        "review": get_latest_review(str(inspection_id)) or {"review_status": "NOT_REVIEWED"},
        "corrections": get_field_corrections(str(inspection_id)),
        "audit_trail": get_audit_events(str(inspection_id)),
    }


@app.get("/rules", response_model=list[RuleInfo], tags=["rules"])
@app.get("/api/rules", response_model=list[RuleInfo], include_in_schema=False)
def list_rules() -> list[RuleInfo]:
    active = load_rules()
    result: list[RuleInfo] = []
    for r in active:
        raw_sev = r.get("severity_if_fail") or r.get("severity")
        sev = "MAJOR" if str(raw_sev).lower() in ("critical", "high", "major") else "MINOR"
        result.append(
            RuleInfo(
                rule_id=str(r.get("rule_id", "")),
                field=str(r.get("field", "")),
                source_citation=str(r.get("source_citation", "Legal Metrology (Packaged Commodities) Rules, 2011, Rule 6")),
                description=str(r.get("description", "")),
                severity=sev,
                confidence_floor=float(r.get("confidence_floor", 0.55)),
                check_type=str(r.get("check_type", "presence_and_pattern")),
                rule_version=str(r.get("rule_version", "1.0")),
                applicability=str(r.get("applicability", "all_packages")),
                legal_verification_required=True,
            )
        )
    return result


@app.get("/history", response_model=list[HistoryItem], tags=["inspections"])
@app.get("/api/history", response_model=list[HistoryItem], include_in_schema=False)
def history(
    limit: int = 100,
    status: str | None = None,
    review_status: str | None = None,
    search: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
) -> list[HistoryItem]:
    records = list_inspections(min(max(limit, 1), 500))
    normalized_search = (search or "").strip().lower()
    items: list[HistoryItem] = []
    for record in records:
        latest_review = get_latest_review(str(record["id"])) or {"review_status": "NOT_REVIEWED"}
        record_review_status = str(latest_review.get("review_status", "NOT_REVIEWED"))
        if status and record["overall_status"] != status:
            continue
        if review_status and record_review_status != review_status:
            continue
        if created_from and record["created_at"] < created_from:
            continue
        if created_to and record["created_at"] > created_to:
            continue
        searchable = " ".join(
            [
                str(record["id"]),
                str(record.get("original_filename", "")),
                *[
                    str(value.get("text", ""))
                    for value in record.get("extracted_fields", {}).values()
                    if isinstance(value, dict)
                ],
            ]
        ).lower()
        if normalized_search and normalized_search not in searchable:
            continue
        items.append(
        HistoryItem(
            id=int(record["id"]),
            original_filename=record["original_filename"],
            created_at=record["created_at"],
            overall_status=record["overall_status"],
            quality_status=record.get("quality", {}).get("status", "unknown"),
            ocr_engine=record.get("ocr_engine", "unknown"),
            review_status=record_review_status,
            package_scope=record.get("context", {}).get("package_scope", "unknown"),
        )
        )
    return items


@app.get("/inspection/{inspection_id}", response_model=InspectionDetail, tags=["inspections"])
@app.get("/api/inspection/{inspection_id}", response_model=InspectionDetail, include_in_schema=False)
def inspection_detail(inspection_id: int) -> InspectionDetail:
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return _detail_response(record)


@app.get("/inspection/{inspection_id}/image", tags=["inspections"])
@app.get("/api/inspection/{inspection_id}/image", include_in_schema=False)
def inspection_image(inspection_id: int) -> FileResponse:
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    path = _safe_media_path(record.get("stored_filename"))
    if path is None:
        raise HTTPException(status_code=404, detail="Inspection image is unavailable.")
    return FileResponse(path, media_type=record.get("mime_type") or "application/octet-stream")


@app.get("/inspection/{inspection_id}/evidence-image", tags=["inspections"])
@app.get("/api/inspection/{inspection_id}/evidence-image", include_in_schema=False)
def inspection_evidence_image(inspection_id: int) -> FileResponse:
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    path = _safe_media_path(record.get("evidence_filename"))
    if path is None:
        raise HTTPException(status_code=404, detail="Evidence image is unavailable.")
    return FileResponse(path, media_type="image/png")


@app.get("/analytics", tags=["inspections"])
@app.get("/api/analytics", include_in_schema=False)
def analytics() -> dict[str, Any]:
    records = list_inspections(500)
    status_counts = {key: 0 for key in ("compliant", "potential_non_compliance", "manual_review_required")}
    quality_counts: dict[str, int] = defaultdict(int)
    review_counts: dict[str, int] = defaultdict(int)
    daily_counts: dict[str, int] = defaultdict(int)
    for record in records:
        status_counts[record["overall_status"]] = status_counts.get(record["overall_status"], 0) + 1
        quality_counts[str(record.get("quality", {}).get("status", "unknown"))] += 1
        review = get_latest_review(str(record["id"])) or {"review_status": "NOT_REVIEWED"}
        review_counts[str(review.get("review_status", "NOT_REVIEWED"))] += 1
        daily_counts[str(record.get("created_at", ""))[:10]] += 1
    return {
        "total_inspections": len(records),
        "status_counts": status_counts,
        "quality_counts": dict(quality_counts),
        "review_counts": dict(review_counts),
        "daily_counts": [
            {"date": date, "count": count} for date, count in sorted(daily_counts.items())[-14:]
        ],
        "sample_limit": 500,
        "is_complete_history": len(records) < 500,
    }


@app.get("/review-queue", response_model=list[HistoryItem], tags=["inspections"])
@app.get("/api/review-queue", response_model=list[HistoryItem], include_in_schema=False)
def review_queue(limit: int = 100) -> list[HistoryItem]:
    queue = history(limit=500)
    return [
        item
        for item in queue
        if item.overall_status == "manual_review_required"
        or item.review_status in {"NOT_REVIEWED", "CORRECTION_REQUIRED", "REINSPECTION_REQUIRED"}
    ][: min(max(limit, 1), 500)]


def _safe_csv_cell(value: Any) -> str:
    text_value = str(value or "")
    return f"'{text_value}" if text_value.startswith(("=", "+", "-", "@")) else text_value


@app.get("/exports/history.csv", tags=["exports"])
@app.get("/api/exports/history.csv", include_in_schema=False)
def export_history_csv() -> StreamingResponse:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["inspection_id", "created_at", "filename", "overall_status", "quality_status", "review_status", "package_scope"])
    for item in history(limit=500):
        writer.writerow([
            item.id,
            item.created_at,
            _safe_csv_cell(item.original_filename),
            item.overall_status,
            item.quality_status,
            item.review_status,
            item.package_scope,
        ])
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="labelguard-history.csv"'},
    )


@app.get("/exports/history.json", tags=["exports"])
@app.get("/api/exports/history.json", include_in_schema=False)
def export_history_json() -> Response:
    payload = [item.model_dump() for item in history(limit=500)]
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="labelguard-history.json"'},
    )


@app.get("/report/{inspection_id}", tags=["reports"])
@app.get("/api/report/{inspection_id}", include_in_schema=False)
def inspection_report(inspection_id: int) -> Response:
    record = get_inspection(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    evidence_path = (
        _safe_media_path(record["evidence_filename"])
        if record.get("evidence_filename")
        else None
    )
    pdf = build_pdf(record, evidence_path)
    report_path = REPORT_DIR / f"{inspection_id}.pdf"
    report_path.write_bytes(pdf)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="labelguard-report-{inspection_id}.pdf"'
        },
    )


@app.get("/health", tags=["system"])
@app.get("/system/status", tags=["system"])
@app.get("/api/health", include_in_schema=False)
@app.get("/api/healthz", include_in_schema=False)
@app.get("/api/system/status", include_in_schema=False)
def health() -> dict[str, Any]:
    database = database_health()
    gemini = GEMINI.status()
    status = (
        "ok"
        if database.get("available") and RULES and gemini.get("available")
        else "degraded"
    )
    return {
        "status": status,
        "service": "labelguard-api",
        "database": database,
        "extraction": {
            "mode": "gemini_only",
            "reader": "gemini_vision",
            "available": bool(gemini.get("available")),
            "local_ocr_in_inspection_path": False,
            "deterministic_field_validation": True,
        },
        "gemini": gemini,
        "rule_engine": {
            "available": bool(RULES),
            "version": RULE_ENGINE_VERSION,
            "active_rule_count": len(RULES),
            "verdict_source": "backend_deterministic_rule_engine",
        },
    }

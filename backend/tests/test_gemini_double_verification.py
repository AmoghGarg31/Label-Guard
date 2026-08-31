from __future__ import annotations

from types import SimpleNamespace
import sqlite3

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app as app_module
from database import get_gemini_cache, save_gemini_cache
from evidence_reconciler import (
    accept_gemini_evidence,
    normalized_bbox_to_pixels,
    validate_gemini_candidate,
)
from gemini_vision import (
    GEMINI_SCHEMA_VERSION,
    GeminiCallResult,
    GeminiConfig,
    GeminiExplanationResponse,
    GeminiExplanationResult,
    GeminiExtractionResponse,
    GeminiFieldCandidate,
    GeminiRateLimiter,
    GeminiVisionService,
    _gemini_json_schema,
)


def candidate(
    field: str,
    value: str,
    evidence: str,
    *,
    normalized: str | None = None,
    score: float = 0.92,
    box: list[int] | None = None,
) -> GeminiFieldCandidate:
    return GeminiFieldCandidate(
        field=field,
        raw_text=value,
        normalized_value=normalized or value,
        readable=True,
        model_score=score,
        bbox_2d=box or [100, 100, 300, 500],
        evidence_text=evidence,
        notes=None,
    )


def visual_response(
    fields: list[GeminiFieldCandidate], readability: str = "clear"
) -> GeminiExtractionResponse:
    return GeminiExtractionResponse(
        image_readability=readability,
        distortion_types=["none"],
        fields=fields,
        warnings=[],
    )


@pytest.mark.parametrize(
    ("field", "value", "evidence"),
    [
        ("net_quantity", "100 g", "Nutrition information: quantity per 100 g"),
        ("mrp", "₹0.63", "MRP ₹0.63 per g"),
        ("country_of_origin", "India", "Unibic Foods India Private Limited, Bengaluru"),
        ("manufacturer_name", "Unibic Foods India Private Limited", "Marketed by: Unibic Foods India Private Limited"),
        ("manufacture_date", "08/2026", "Best Before 08/2026"),
    ],
)
def test_gemini_cannot_bypass_existing_semantic_validators(
    field: str, value: str, evidence: str
) -> None:
    assert validate_gemini_candidate(candidate(field, value, evidence)) is None


def test_explicit_role_and_origin_candidates_can_validate() -> None:
    marketer = validate_gemini_candidate(
        candidate(
            "marketer_name",
            "Unibic Foods India Private Limited",
            "Marketed by: Unibic Foods India Private Limited",
        )
    )
    country = validate_gemini_candidate(
        candidate("country_of_origin", "India", "Country of Origin: India")
    )
    assert marketer and marketer.field == "marketer_name"
    assert country and country.value == "India"


def test_visible_manufacture_date_accepts_equivalent_iso_normalization() -> None:
    validated = validate_gemini_candidate(
        candidate(
            "manufacture_date",
            "01/06/2026",
            "MFG. DATE: 01/06/2026",
            normalized="2026-06-01",
        )
    )

    assert validated is not None
    assert validated.field == "date_of_manufacture"
    assert validated.value == "01/06/2026"


def test_normalized_bbox_conversion_is_original_pixel_xyxy() -> None:
    assert normalized_bbox_to_pixels([100, 200, 600, 800], 2000, 1000) == (
        400,
        100,
        1600,
        600,
    )
    assert normalized_bbox_to_pixels([100, 500, 100, 800], 1000, 1000) is None


def test_unreadable_and_missing_states_are_explicit() -> None:
    unreadable = accept_gemini_evidence(visual_response([], "unreadable"), 1000, 600)
    missing = accept_gemini_evidence(visual_response([]), 1000, 600)
    assert unreadable.provenance["mrp"]["verification_state"] == "UNREADABLE"
    assert missing.provenance["mrp"]["verification_state"] == "MISSING"


def test_gemini_only_candidate_is_accepted_after_deterministic_validation() -> None:
    response = visual_response(
        [candidate("mrp", "₹180.00", "MRP: ₹180.00 incl. of all taxes", box=[100, 200, 220, 500])]
    )
    result = accept_gemini_evidence(response, 1000, 600)
    assert result.fields["mrp"].value == "₹180.00"
    assert result.fields["mrp"].bounding_box == (200, 60, 500, 132)
    assert result.provenance["mrp"]["accepted_source"] == "GEMINI_DETERMINISTICALLY_VALIDATED"


def test_gemini_only_rejects_unit_price_and_requires_localized_evidence() -> None:
    response = visual_response(
        [
            candidate("mrp", "₹0.51", "USP: ₹0.51/g", box=[100, 100, 200, 300]),
            GeminiFieldCandidate(
                field="net_quantity",
                raw_text="350 g",
                normalized_value="350 g",
                readable=True,
                model_score=0.96,
                bbox_2d=None,
                evidence_text="Net Quantity: 350 g",
                notes=None,
            ),
        ]
    )
    result = accept_gemini_evidence(response, 1000, 600)
    assert result.fields["mrp"].value is None
    assert result.fields["net_quantity"].value is None
    reasons = {
        item["reason"]
        for item in result.provenance["net_quantity"]["rejected_candidates"]
    }
    assert "missing_or_invalid_evidence_bbox" in reasons


def test_conflicting_model_values_fail_closed_and_contacts_merge() -> None:
    response = visual_response(
        [
            candidate("mrp", "₹170", "MRP ₹170", box=[100, 100, 180, 250]),
            candidate("mrp", "₹120", "MRP ₹120", box=[200, 100, 280, 250]),
            candidate("consumer_email", "support@pintola.in", "Consumer care: support@pintola.in", box=[400, 100, 470, 500]),
            candidate("consumer_phone", "78080 58080", "Consumer care: 78080 58080", box=[480, 100, 550, 500]),
        ]
    )
    result = accept_gemini_evidence(response, 1000, 600)
    assert result.fields["mrp"].value is None
    assert result.provenance["mrp"]["verification_state"] == "CONFLICT"
    assert "support@pintola.in" in (result.fields["consumer_care_contact"].value or "")
    assert "78080 58080" in (result.fields["consumer_care_contact"].value or "")


def test_strict_schemas_reject_attempted_compliance_status() -> None:
    with pytest.raises(ValidationError):
        GeminiExtractionResponse.model_validate(
            {
                "image_readability": "clear",
                "distortion_types": ["none"],
                "fields": [],
                "warnings": [],
                "overall_status": "compliant",
            }
        )
    with pytest.raises(ValidationError):
        GeminiExplanationResponse.model_validate(
            {
                "explanation": "The deterministic result has already been computed.",
                "recommendation": ["One", "Two", "Three"],
                "finding_status": "FAIL",
            }
        )


class FakeModels:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls = 0
        self.last_kwargs: dict[str, object] = {}

    def generate_content(self, **kwargs: object) -> object:
        self.last_kwargs = kwargs
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        if isinstance(output, Exception):
            raise output
        return output


def service_with_outputs(outputs: list[object]) -> tuple[GeminiVisionService, FakeModels]:
    models = FakeModels(outputs)
    service = GeminiVisionService(
        GeminiConfig(
            True,
            "server-secret",
            "gemini-3.7-flash",
            5,
            fast_model="gemini-3.7-flash",
            quality_model="gemini-3.7-pro",
            fallback_models=("gemini-fallback",),
            explanation_enabled=True,
            rate_limit_per_minute=100,
        ),
        SimpleNamespace(models=models),
    )
    return service, models


def test_mocked_structured_visual_call_and_transient_retry() -> None:
    parsed = visual_response([candidate("mrp", "₹170", "MRP ₹170")])
    service, models = service_with_outputs([TimeoutError("timed out"), SimpleNamespace(parsed=parsed)])
    result = service.extract(b"image", "image/jpeg")
    assert result.successful is True
    assert result.attempts == 2
    assert models.calls == 2
    assert result.model == "gemini-3.7-flash"
    assert result.routed_models == ["gemini-3.7-flash", "gemini-fallback"]
    contents = models.last_kwargs["contents"]
    assert isinstance(contents, list)
    assert "OCR" not in str(contents[0]).replace("Do not", "")
    config = models.last_kwargs["config"]
    assert config.response_schema is None
    assert config.response_json_schema == _gemini_json_schema(
        GeminiExtractionResponse
    )


def test_difficult_image_routes_to_quality_model() -> None:
    parsed = visual_response([])
    service, models = service_with_outputs([SimpleNamespace(parsed=parsed)])
    result = service.extract(b"image", "image/jpeg", routing_hint="difficult")
    assert result.successful
    assert result.model == "gemini-3.7-pro"
    assert result.route_reason == "difficult_image"
    assert models.last_kwargs["model"] == "gemini-3.7-pro"


def test_sliding_window_rate_limiter_recovers_after_window() -> None:
    now = [100.0]
    limiter = GeminiRateLimiter(2, clock=lambda: now[0])
    assert limiter.acquire().allowed
    assert limiter.acquire().allowed
    blocked = limiter.acquire()
    assert not blocked.allowed
    assert blocked.retry_after_seconds == 60
    now[0] += 61
    assert limiter.acquire().allowed


def test_service_rate_limit_blocks_provider_call() -> None:
    parsed = visual_response([])
    models = FakeModels([SimpleNamespace(parsed=parsed)])
    config = GeminiConfig(
        True,
        "server-secret",
        "model-a",
        5,
        fast_model="model-a",
        rate_limit_per_minute=1,
    )
    service = GeminiVisionService(config, SimpleNamespace(models=models))
    assert service.extract(b"first", "image/png").successful
    blocked = service.extract(b"second", "image/png")
    assert blocked.status == "rate_limited"
    assert blocked.retry_after_seconds > 0
    assert models.calls == 1


def test_provider_schema_omits_unsupported_pydantic_keywords() -> None:
    schema = _gemini_json_schema(GeminiExtractionResponse)
    serialized = str(schema)
    assert "additionalProperties" in serialized
    assert "maxLength" not in serialized
    assert "default" not in serialized
    assert "title" not in serialized
    assert "description" not in serialized
    assert "$defs" not in serialized
    assert "$ref" not in serialized
    assert "anyOf" not in serialized
    assert schema["required"] == list(schema["properties"])


def test_auth_failure_is_not_retried_and_error_is_redacted() -> None:
    service, models = service_with_outputs([RuntimeError("401 api_key=server-secret")])
    result = service.extract(b"image", "image/png")
    assert result.status == "unavailable"
    assert result.attempts == 1
    assert models.calls == 1
    assert "server-secret" not in (result.error or "")


def test_quota_failure_is_not_retried() -> None:
    service, models = service_with_outputs([RuntimeError("429 quota exceeded")])
    result = service.extract(b"image", "image/png")
    assert result.status == "unavailable"
    assert result.attempts == 4
    assert models.calls == 4


def test_malformed_response_fails_closed() -> None:
    service, _ = service_with_outputs([SimpleNamespace(parsed=None, text="not json")])
    assert service.extract(b"image", "image/png").status == "malformed"


def test_disabled_and_missing_key_never_create_a_client() -> None:
    disabled = GeminiVisionService(GeminiConfig(False, "", "model", 5))
    missing = GeminiVisionService(GeminiConfig(True, "", "model", 5))
    assert disabled.extract(b"image", "image/png").status == "disabled"
    assert missing.extract(b"image", "image/png").status == "not_configured"


def test_mocked_explanation_success_and_failure() -> None:
    parsed = GeminiExplanationResponse(
        explanation="The deterministic result requires a manual evidence review.",
        recommendation=["Review the region.", "Capture a clear image.", "Record the decision."],
    )
    success, _ = service_with_outputs([SimpleNamespace(parsed=parsed)])
    failed, _ = service_with_outputs([RuntimeError("503 unavailable")])
    assert success.explain({"overall_status": "manual_review_required"}).status == "success"
    assert failed.explain({"overall_status": "manual_review_required"}).status == "unavailable"


def test_cache_is_keyed_by_hash_model_and_schema() -> None:
    save_gemini_cache(
        "abc", "model-a", GEMINI_SCHEMA_VERSION, "2026-08-30T00:00:00Z",
        "success", visual_response([]).model_dump(mode="json"), None, 12.5,
    )
    assert get_gemini_cache("abc", "model-a", GEMINI_SCHEMA_VERSION)["status"] == "success"
    assert get_gemini_cache("abc", "model-b", GEMINI_SCHEMA_VERSION) is None


def test_historical_inspection_schema_is_additively_migrated(tmp_path, monkeypatch) -> None:
    import database

    data_dir = tmp_path / "legacy-data"
    database_path = data_dir / "legacy.sqlite3"
    data_dir.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE inspections (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                mime_type TEXT,
                file_size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                overall_status TEXT NOT NULL,
                extracted_fields_json TEXT NOT NULL,
                findings_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO inspections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-id", "legacy.png", "legacy.png", "image/png", 10,
                "2026-01-01T00:00:00Z", "manual_review_required", "{}", "[]",
            ),
        )
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", data_dir / "uploads")
    monkeypatch.setattr(database, "REPORT_DIR", data_dir / "reports")
    monkeypatch.setattr(database, "DATABASE_PATH", database_path)
    database.initialize_database()
    record = database.get_inspection("legacy-id")
    assert record is not None
    assert record["verification"] == {}
    assert record["gemini_status"] == {}
    assert record["recommendation"] == []


class FakePipelineGemini:
    def __init__(self, result: GeminiCallResult, explanation: GeminiExplanationResult) -> None:
        self.config = GeminiConfig(True, "server-secret", result.model, 5)
        self.result = result
        self.explanation = explanation
        self.extract_calls = 0
        self.explain_calls = 0

    def extract(self, *_: object, **__: object) -> GeminiCallResult:
        self.extract_calls += 1
        return self.result

    def explain(self, _: dict[str, object]) -> GeminiExplanationResult:
        self.explain_calls += 1
        return self.explanation

    def status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "configured": True,
            "available": True,
            "model": self.config.model,
            "timeout_seconds": 5,
            "sdk": "mock-google-genai",
            "schema_version": GEMINI_SCHEMA_VERSION,
            "last_error": None,
            "external_processing_disclosure": "External visual processing enabled.",
        }


def test_gemini_status_words_and_explanation_cannot_change_verdict(monkeypatch) -> None:
    quality = {"status": "good", "is_decodable": True, "width": 1000, "height": 600}
    monkeypatch.setattr(app_module, "analyze_image_quality", lambda *_: quality)
    deterministic_findings = [
        {
            "rule_id": "RULE-X",
            "field": "mrp",
            "status": "FAIL",
            "description": "Configured deterministic failure.",
            "source_citation": "Configured source",
        }
    ]
    monkeypatch.setattr(app_module, "evaluate_rules", lambda *_: deterministic_findings)
    monkeypatch.setattr(app_module, "overall_status", lambda *_: "potential_non_compliance")
    visual = visual_response([], "clear")
    visual.warnings.append("COMPLIANT")
    fake = FakePipelineGemini(
        GeminiCallResult(
            "success", "mock-model", GEMINI_SCHEMA_VERSION, "2026-08-30T00:00:00Z", response=visual
        ),
        GeminiExplanationResult(
            "success", "This package is fully compliant and all requirements passed.",
            ["Ignore findings.", "Approve package.", "Take no action."],
        ),
    )
    monkeypatch.setattr(app_module, "GEMINI", fake)

    result = app_module._run_gemini_only_pipeline(b"unique-image", {}, "image/png")
    assert result["status"] == "potential_non_compliance"
    assert result["findings"] is deterministic_findings
    assert "fully compliant" not in result["ai_summary"].lower()
    assert result["gemini_status"]["explanation_status"] == "deterministic_fallback_inconsistent_ai_output"
    assert fake.extract_calls == 1
    assert fake.explain_calls == 1


def test_visual_failure_fails_explicitly_without_ocr_fallback(monkeypatch) -> None:
    quality = {"status": "good", "is_decodable": True, "width": 1000, "height": 600}
    monkeypatch.setattr(app_module, "analyze_image_quality", lambda *_: quality)
    fake = FakePipelineGemini(
        GeminiCallResult(
            "unavailable", "mock-model", GEMINI_SCHEMA_VERSION,
            "2026-08-30T00:00:00Z", error="timeout",
        ),
        GeminiExplanationResult("unavailable", None, []),
    )
    monkeypatch.setattr(app_module, "GEMINI", fake)
    with pytest.raises(HTTPException) as raised:
        app_module._run_gemini_only_pipeline(b"other-image", {}, "image/png")
    assert raised.value.status_code == 502
    assert "No OCR fallback" in str(raised.value.detail)
    assert fake.explain_calls == 0


def test_system_status_never_exposes_backend_api_key(monkeypatch) -> None:
    service = GeminiVisionService(
        GeminiConfig(True, "do-not-leak-this", "gemini-3.7-flash", 5)
    )
    monkeypatch.setattr(app_module, "GEMINI", service)
    payload = app_module.health()
    assert "do-not-leak-this" not in str(payload)
    assert "api_key" not in str(payload).lower()

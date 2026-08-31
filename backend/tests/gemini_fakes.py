"""Deterministic Gemini fixtures shared by API tests."""

from datetime import datetime, timezone

from gemini_vision import (
    GEMINI_SCHEMA_VERSION,
    GeminiCallResult,
    GeminiConfig,
    GeminiExplanationResult,
    GeminiExtractionResponse,
    GeminiFieldCandidate,
)


def visual_candidate(
    field: str,
    value: str,
    evidence: str,
    box: list[int],
    score: float = 0.94,
) -> GeminiFieldCandidate:
    return GeminiFieldCandidate(
        field=field,
        raw_text=value,
        normalized_value=value,
        readable=True,
        model_score=score,
        bbox_2d=box,
        evidence_text=evidence,
        notes=None,
    )


class FakeGeminiService:
    def __init__(self, response: GeminiExtractionResponse, model: str = "test-gemini") -> None:
        self.response = response
        self.config = GeminiConfig(
            True,
            "test-only-key",
            model,
            5,
            fast_model=model,
            quality_model=model,
            explanation_enabled=False,
            rate_limit_per_minute=100,
        )
        self.extract_calls = 0

    def route_models(self, _routing_hint: str = "standard") -> list[str]:
        return [self.config.model]

    def extract(self, *_args: object, **_kwargs: object) -> GeminiCallResult:
        self.extract_calls += 1
        return GeminiCallResult(
            "success",
            self.config.model,
            GEMINI_SCHEMA_VERSION,
            datetime.now(timezone.utc).isoformat(),
            response=self.response,
            attempts=1,
            route_reason="standard_image",
            routed_models=[self.config.model],
        )

    def explain(self, _facts: dict[str, object]) -> GeminiExplanationResult:
        return GeminiExplanationResult("disabled", None, [])

    def status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "configured": True,
            "available": True,
            "mode": "gemini_only_extraction",
            "model": self.config.model,
            "fast_model": self.config.model,
            "quality_model": self.config.model,
            "fallback_models": [],
            "explanation_model": self.config.model,
            "explanation_enabled": False,
            "timeout_seconds": 5,
            "rate_limit": {
                "limit_per_minute": 100,
                "used_in_current_window": self.extract_calls,
                "remaining_in_current_window": 100 - self.extract_calls,
                "max_concurrent_requests": 2,
            },
            "last_route": None,
            "sdk": "fake-google-genai",
            "schema_version": GEMINI_SCHEMA_VERSION,
            "last_error": None,
            "external_processing_disclosure": "Test-only external visual processing fixture.",
        }

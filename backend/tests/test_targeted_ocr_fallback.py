"""Architecture regression: the HTTP inspection route has no OCR fallback."""

import inspect

import app as app_module


def test_active_pipeline_uses_one_gemini_reader_and_no_local_ocr() -> None:
    source = inspect.getsource(app_module._run_gemini_only_pipeline)
    assert "accept_gemini_evidence" in source
    assert "GEMINI" in source
    assert "OCR." not in source
    assert "OCRService" not in source
    assert not hasattr(app_module, "OCR")


def test_inspect_route_calls_gemini_only_pipeline() -> None:
    source = inspect.getsource(app_module.inspect_image)
    assert "_run_gemini_only_pipeline" in source
    assert "OCR." not in source
    assert "OCRService" not in source

"""Make the API artifact modules importable from any pytest working directory."""

import os
import sys
from pathlib import Path

import pytest


API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# Automated tests must never inherit a developer's live Gemini setting from
# backend/.env. Individual Gemini tests inject deterministic mock services.
os.environ.setdefault("GEMINI_ENABLED", "false")


@pytest.fixture(autouse=True)
def isolated_runtime_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep every automated test away from the user's inspection database and media."""

    import app as app_module
    import database

    data_dir = tmp_path / "runtime-data"
    upload_dir = data_dir / "uploads"
    report_dir = data_dir / "reports"
    database_path = data_dir / "labelguard-test.sqlite3"

    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(database, "REPORT_DIR", report_dir)
    monkeypatch.setattr(database, "DATABASE_PATH", database_path)
    monkeypatch.setattr(app_module, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(app_module, "REPORT_DIR", report_dir)
    app_module._upload_attempts.clear()
    database.initialize_database()
    yield

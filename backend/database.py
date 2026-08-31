"""SQLite persistence for LabelGuard inspections."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


DATA_DIR = Path(os.environ.get("LABELGUARD_DATA_DIR", Path(__file__).resolve().parent / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
DATABASE_PATH = DATA_DIR / "labelguard.sqlite3"

JSON_COLUMNS = {
    "quality_json",
    "extracted_fields_json",
    "findings_json",
    "context_json",
    "verification_json",
    "gemini_status_json",
    "recommendation_json",
    "performance_json",
}


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inspections (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                mime_type TEXT,
                file_size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                overall_status TEXT NOT NULL,
                extracted_fields_json TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                quality_json TEXT NOT NULL DEFAULT '{}',
                ocr_engine TEXT NOT NULL DEFAULT 'unknown',
                ocr_text TEXT NOT NULL DEFAULT '',
                evidence_filename TEXT,
                processing_error TEXT
                ,context_json TEXT NOT NULL DEFAULT '{}'
                ,orientation_degrees INTEGER NOT NULL DEFAULT 0
                ,verification_json TEXT NOT NULL DEFAULT '{}'
                ,gemini_status_json TEXT NOT NULL DEFAULT '{}'
                ,ai_summary TEXT
                ,recommendation_json TEXT NOT NULL DEFAULT '[]'
                ,performance_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inspection_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'NOT_REVIEWED',
                reviewed_by TEXT,
                review_notes TEXT,
                reviewed_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inspection_field_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id TEXT NOT NULL,
                field TEXT NOT NULL,
                original_text TEXT,
                corrected_text TEXT NOT NULL,
                reason TEXT,
                actor TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inspection_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gemini_visual_cache (
                image_sha256 TEXT NOT NULL,
                model TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                safe_error TEXT,
                duration_ms REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (image_sha256, model, schema_version)
            )
            """
        )

        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(inspections)").fetchall()
        }
        migrations = {
            "quality_json": "ALTER TABLE inspections ADD COLUMN quality_json TEXT NOT NULL DEFAULT '{}'",
            "ocr_engine": "ALTER TABLE inspections ADD COLUMN ocr_engine TEXT NOT NULL DEFAULT 'unknown'",
            "ocr_text": "ALTER TABLE inspections ADD COLUMN ocr_text TEXT NOT NULL DEFAULT ''",
            "evidence_filename": "ALTER TABLE inspections ADD COLUMN evidence_filename TEXT",
            "processing_error": "ALTER TABLE inspections ADD COLUMN processing_error TEXT",
            "rule_engine_version": "ALTER TABLE inspections ADD COLUMN rule_engine_version TEXT NOT NULL DEFAULT 'LMPC-ENGINE-1.1'",
            "original_extracted_fields_json": "ALTER TABLE inspections ADD COLUMN original_extracted_fields_json TEXT",
            "original_overall_status": "ALTER TABLE inspections ADD COLUMN original_overall_status TEXT",
            "context_json": "ALTER TABLE inspections ADD COLUMN context_json TEXT NOT NULL DEFAULT '{}'",
            "orientation_degrees": "ALTER TABLE inspections ADD COLUMN orientation_degrees INTEGER NOT NULL DEFAULT 0",
            "verification_json": "ALTER TABLE inspections ADD COLUMN verification_json TEXT NOT NULL DEFAULT '{}'",
            "gemini_status_json": "ALTER TABLE inspections ADD COLUMN gemini_status_json TEXT NOT NULL DEFAULT '{}'",
            "ai_summary": "ALTER TABLE inspections ADD COLUMN ai_summary TEXT",
            "recommendation_json": "ALTER TABLE inspections ADD COLUMN recommendation_json TEXT NOT NULL DEFAULT '[]'",
            "performance_json": "ALTER TABLE inspections ADD COLUMN performance_json TEXT NOT NULL DEFAULT '{}'",
        }
        for column, statement in migrations.items():
            if column not in existing_columns:
                connection.execute(statement)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inspections_created_at ON inspections(created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(overall_status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_inspection_id ON inspection_reviews(inspection_id, id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_corrections_inspection_id ON inspection_field_corrections(inspection_id, id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_inspection_id ON inspection_audit_events(inspection_id, id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_gemini_cache_created_at ON gemini_visual_cache(created_at)"
        )


def save_inspection(record: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO inspections (
                id, original_filename, stored_filename, mime_type,
                file_size_bytes, created_at, overall_status,
                extracted_fields_json, findings_json, quality_json,
                ocr_engine, ocr_text, evidence_filename, processing_error,
                rule_engine_version, context_json, orientation_degrees,
                verification_json, gemini_status_json, ai_summary,
                recommendation_json, performance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record.get("uuid") or record.get("id")),
                record["original_filename"],
                record["stored_filename"],
                record.get("mime_type"),
                record["file_size_bytes"],
                record["created_at"],
                record["overall_status"],
                json.dumps(record["extracted_fields"], ensure_ascii=False),
                json.dumps(record["findings"], ensure_ascii=False),
                json.dumps(record.get("quality", {}), ensure_ascii=False),
                record.get("ocr_engine", "unknown"),
                record.get("ocr_text", ""),
                record.get("evidence_filename"),
                record.get("processing_error"),
                record.get("rule_engine_version", "LMPC-ENGINE-1.1"),
                json.dumps(record.get("context", {}), ensure_ascii=False),
                int(record.get("orientation_degrees", 0)),
                json.dumps(record.get("verification", {}), ensure_ascii=False),
                json.dumps(record.get("gemini_status", {}), ensure_ascii=False),
                record.get("ai_summary"),
                json.dumps(record.get("recommendation", []), ensure_ascii=False),
                json.dumps(record.get("performance", {}), ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def _decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    record = dict(row)
    record["rule_engine_version"] = record.get("rule_engine_version") or "LMPC-ENGINE-1.1"
    if "numeric_id" in row.keys():
        record["id"] = int(row["numeric_id"])
        del record["numeric_id"]
    elif "rowid" in row.keys():
        record["id"] = int(row["rowid"])

    for column in JSON_COLUMNS:
        raw_value = record.get(column)
        fallback: Any = [] if column == "recommendation_json" else {}
        try:
            decoded = json.loads(raw_value or ("[]" if isinstance(fallback, list) else "{}"))
            record[column.removesuffix("_json")] = decoded
        except (TypeError, json.JSONDecodeError):
            record[column.removesuffix("_json")] = fallback
        record.pop(column, None)

    extracted = record.get("extracted_fields", {})
    normalized_extracted: dict[str, dict[str, Any]] = {}
    for k, v in extracted.items():
        if isinstance(v, dict):
            normalized_extracted[k] = {
                "text": str(v.get("text") or ""),
                "confidence": round(float(v.get("confidence", 0.0)), 3),
                "bounding_box": v.get("bounding_box") if _valid_bbox(v.get("bounding_box")) else None,
                "source": (
                    "human_correction"
                    if v.get("source") == "human_correction"
                    else ("gemini" if v.get("source") == "gemini" else "ocr")
                ),
            }
        elif isinstance(v, str):
            normalized_extracted[k] = {
                "text": v,
                "confidence": 0.8,
                "bounding_box": None,
                "source": "ocr",
            }
        else:
            normalized_extracted[k] = {
                "text": "",
                "confidence": 0.0,
                "bounding_box": None,
                "source": "ocr",
            }
    record["extracted_fields"] = normalized_extracted

    findings = record.get("findings", [])
    normalized_findings: list[dict[str, Any]] = []
    for f in findings:
        severity = f.get("severity")
        if str(severity).upper() in ("MAJOR", "HIGH", "CRITICAL") or severity is None:
            sev = "MAJOR"
        else:
            sev = "MINOR"
        bbox = f.get("bounding_box")
        if not bbox or len(bbox) != 4:
            bbox = [0, 0, 0, 0]
        else:
            bbox = [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
        normalized_findings.append({
            "rule_id": str(f.get("rule_id", "")),
            "field": str(f.get("field", "")),
            "status": str(f.get("status", "UNCERTAIN")),
            "severity": sev,
            "confidence": round(float(f.get("confidence", 0.0)), 3),
            "bounding_box": bbox,
            "description": str(f.get("description", "")),
            "source_citation": str(f.get("source_citation", "")),
            "rule_version": str(f.get("rule_version", "1.0")),
            "applicability": str(f.get("applicability", "applicable")),
        })
    record["findings"] = normalized_findings
    raw_original = record.get("original_extracted_fields_json")
    try:
        record["original_extracted_fields"] = json.loads(raw_original) if raw_original else None
    except (TypeError, json.JSONDecodeError):
        record["original_extracted_fields"] = None
    return record


def get_inspection(inspection_id: int | str) -> dict[str, Any] | None:
    with get_connection() as connection:
        if isinstance(inspection_id, int) or (isinstance(inspection_id, str) and inspection_id.isdigit()):
            row = connection.execute(
                "SELECT rowid as numeric_id, * FROM inspections WHERE rowid = ? OR id = ?",
                (int(inspection_id), str(inspection_id)),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT rowid as numeric_id, * FROM inspections WHERE id = ?",
                (str(inspection_id),),
            ).fetchone()
    return _decode_row(row)


def list_inspections(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = min(max(limit, 1), 500)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT rowid as numeric_id, * FROM inspections
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [record for row in rows if (record := _decode_row(row)) is not None]


def save_review(
    inspection_id: str,
    review_status: str,
    reviewed_by: str,
    review_notes: str | None,
    reviewed_at: str,
) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO inspection_reviews (
                inspection_id, review_status, reviewed_by, review_notes, reviewed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (inspection_id, review_status, reviewed_by, review_notes or "", reviewed_at),
        )
        return {
            "id": cursor.lastrowid,
            "inspection_id": inspection_id,
            "review_status": review_status,
            "reviewed_by": reviewed_by,
            "review_notes": review_notes or "",
            "reviewed_at": reviewed_at,
        }


def get_latest_review(inspection_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM inspection_reviews
            WHERE inspection_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (str(inspection_id),),
        ).fetchone()
        if row:
            return dict(row)
        return None


def save_field_correction(
    inspection_id: str,
    field: str,
    original_text: str | None,
    corrected_text: str,
    reason: str,
    actor: str | None,
    created_at: str,
) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO inspection_field_corrections (
                inspection_id, field, original_text, corrected_text, reason, actor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inspection_id,
                field,
                original_text or "",
                corrected_text,
                reason,
                actor or "inspector",
                created_at,
            ),
        )
        return {
            "id": cursor.lastrowid,
            "inspection_id": inspection_id,
            "field": field,
            "original_text": original_text or "",
            "corrected_text": corrected_text,
            "reason": reason,
            "actor": actor or "inspector",
            "created_at": created_at,
        }


def get_field_corrections(inspection_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM inspection_field_corrections
            WHERE inspection_id = ?
            ORDER BY id ASC
            """,
            (str(inspection_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def save_audit_event(
    inspection_id: str,
    event_type: str,
    description: str,
    actor: str,
    created_at: str,
) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO inspection_audit_events (
                inspection_id, event_type, description, actor, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (inspection_id, event_type, description, actor, created_at),
        )
        return {
            "id": cursor.lastrowid,
            "inspection_id": inspection_id,
            "event_type": event_type,
            "description": description,
            "actor": actor,
            "created_at": created_at,
        }


def get_audit_events(inspection_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM inspection_audit_events
            WHERE inspection_id = ?
            ORDER BY id ASC
            """,
            (str(inspection_id),),
        ).fetchall()
        return [dict(r) for r in rows]


def update_inspection_findings(
    inspection_id: str,
    extracted_fields: dict[str, Any],
    findings: list[dict[str, Any]],
    overall_status: str,
    verification: dict[str, Any] | None = None,
    ai_summary: str | None = None,
    recommendation: list[str] | None = None,
    gemini_status: dict[str, Any] | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE inspections
            SET original_extracted_fields_json = COALESCE(original_extracted_fields_json, extracted_fields_json),
                original_overall_status = COALESCE(original_overall_status, overall_status),
                extracted_fields_json = ?,
                findings_json = ?,
                overall_status = ?,
                verification_json = CASE WHEN ? IS NULL THEN verification_json ELSE ? END,
                ai_summary = CASE WHEN ? IS NULL THEN ai_summary ELSE ? END,
                recommendation_json = CASE WHEN ? IS NULL THEN recommendation_json ELSE ? END,
                gemini_status_json = CASE WHEN ? IS NULL THEN gemini_status_json ELSE ? END
            WHERE id = ? OR rowid = ?
            """,
            (
                json.dumps(extracted_fields, ensure_ascii=False),
                json.dumps(findings, ensure_ascii=False),
                overall_status,
                1 if verification is not None else None,
                json.dumps(verification, ensure_ascii=False) if verification is not None else None,
                ai_summary,
                ai_summary,
                1 if recommendation is not None else None,
                json.dumps(recommendation, ensure_ascii=False) if recommendation is not None else None,
                1 if gemini_status is not None else None,
                json.dumps(gemini_status, ensure_ascii=False) if gemini_status is not None else None,
                str(inspection_id),
                int(inspection_id) if str(inspection_id).isdigit() else -1,
            ),
        )


def get_gemini_cache(
    image_sha256: str, model: str, schema_version: str
) -> dict[str, Any] | None:
    """Read a schema/model-specific visual result without retaining image bytes."""

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM gemini_visual_cache
            WHERE image_sha256 = ? AND model = ? AND schema_version = ?
            """,
            (image_sha256, model, schema_version),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    try:
        result["result"] = json.loads(result.pop("result_json") or "null")
    except (TypeError, json.JSONDecodeError):
        result["result"] = None
        result.pop("result_json", None)
    return result


def save_gemini_cache(
    image_sha256: str,
    model: str,
    schema_version: str,
    created_at: str,
    status: str,
    result: dict[str, Any] | None,
    safe_error: str | None,
    duration_ms: float,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO gemini_visual_cache (
                image_sha256, model, schema_version, created_at, status,
                result_json, safe_error, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_sha256, model, schema_version) DO UPDATE SET
                created_at = excluded.created_at,
                status = excluded.status,
                result_json = excluded.result_json,
                safe_error = excluded.safe_error,
                duration_ms = excluded.duration_ms
            """,
            (
                image_sha256,
                model,
                schema_version,
                created_at,
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                safe_error,
                float(duration_ms),
            ),
        )


def database_health() -> dict[str, Any]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
            count = int(connection.execute("SELECT COUNT(*) FROM inspections").fetchone()[0])
        return {"available": True, "inspection_count": count}
    except sqlite3.Error as exc:
        return {"available": False, "error": str(exc)}


def _valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > value[0]
        and value[3] > value[1]
    )

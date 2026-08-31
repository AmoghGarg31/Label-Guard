# LabelGuard baseline audit

Recorded before recovery changes on 2026-08-30. This file is evidence of the starting state, not current instructions.

## Preservation

- Active SQLite database: `backend/data/labelguard.sqlite3`, 59 inspections.
- Non-destructive backup created at `backend/data/backups/labelguard.sqlite3.pre-recovery-20260830.bak`.
- Code-only baseline archive created at `tmp/baseline/labelguard-code-pre-recovery-20260830.zip`.
- Existing uploads, generated reports, and the older `backend/data/inspections.db` were preserved.
- Workspace root had no usable Git metadata; status/diff reporting was therefore unavailable. Snapshot comparison was used instead.

## Initial gates

| Gate | Baseline result |
|---|---|
| Backend pure rule/extractor tests | 29 passed. |
| Frontend TypeScript | Passed. |
| Frontend production build | Failed while fetching Google Inter during build. |
| `npm audit` | 5 high findings: vulnerable Next.js 13 chain, PostCSS, and minimatch / TypeScript-ESLint chain. |
| Python audit | Not initially configured. Subsequent isolated-environment audit found no known vulnerability in the declared set. |
| Full-stack behavior | Frontend silently fell back to mocks when API requests failed; this could make a broken stack look functional. |

## Baseline structural problems

- Two competing backend identities: the actual FastAPI service and an unused TypeScript/Express scaffold with workspace-only dependencies.
- Frontend API logic synthesized inspector/location/product values and reconstructed broken media paths.
- Automatic mock fallback returned plausible records and even synthetic inspection results after network failure.
- A multi-screen “processing” wizard implied separate OCR/rule phases even though the backend exposed one synchronous `/inspect` operation.
- Camera control was visual only.
- Rule Explorer and declaration matrix contained hardcoded, incomplete, and in places incorrect citations/IDs.
- Dashboard counts came from five displayed rows instead of the database.
- Detail screen included hardcoded reviewer/location presentation and did not provide a complete evidence/review experience.
- OCR grouping merged spatial lines; orientation was not generalized across all right angles.
- Extraction conflated responsible-party roles and contained brand/demo-coupled behavior.
- Missing declarations, imported-only applicability, correction provenance, and evidence-box trust needed stronger doctrine.
- Upload content/dimension hardening, rate limits, security headers, export safety, and test isolation were incomplete.
- Checked-in generated UI primitives added unused dependency surface and stale React assumptions.

## Handbook baseline

The 127-page handbook was fully text-extracted (127 non-empty pages) before implementation decisions. Its core scope was upload/camera, quality, OCR, declaration extraction, deterministic rules, localized evidence, cautious status, human review, history, and report generation. Authentication, LLM verdicts, blockchain, and unnecessary distributed architecture were out of scope for the hackathon prototype.

## Baseline conclusion

The starting repository demonstrated useful OCR/rule concepts but was not judge-safe: a disconnected backend could look healthy, legal/evidence presentation was inconsistent, the primary database could be polluted by tests, dependency findings were high severity, and important UI controls were incomplete.

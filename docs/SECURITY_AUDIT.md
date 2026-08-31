# Security Audit

Audit date: 2026-08-30. Scope: LabelGuard frontend, API, upload/OCR pipeline, SQLite persistence, dependencies, reports, and repository hygiene. This is a prototype security review, not a penetration test or production certification.

## Executive result

The recovered application is suitable for a trusted local demonstration. The upload boundary is materially hardened, CORS is allowlisted, SQL is parameterized, reports escape user-controlled content, security headers are present, dependency audits are clean, and runtime data/secrets are excluded from source control. Public or multi-user deployment is not approved because authentication, authorization, durable distributed rate limiting, centralized logging, encrypted object storage, and a production database are not implemented.

## Threat model

The primary untrusted inputs are image uploads, multipart metadata, search/filter query parameters, field corrections, review notes, OCR output, and persisted filenames. Primary assets are inspection evidence, uploaded labels, audit records, availability of the OCR service, and integrity of deterministic verdicts. Likely abuse includes oversized/decompression-bomb images, spoofed MIME types, path traversal, SQL injection, stored markup in PDFs/UI, cross-origin requests, rapid expensive OCR submissions, spreadsheet formula injection, and accidental publication of local data.

## Findings and controls

| Area | Before | Final control | Verification | Residual risk |
|---|---|---|---|---|
| Upload size | Extension-led acceptance and incomplete content checks | 10 MB request limit; strict extension/declared MIME/decoded-format agreement; Pillow verification before OpenCV; 40 MP decoded-pixel cap; generated storage names | API security tests cover invalid type, oversized body, corrupt bytes, mismatch, and valid formats | OCR remains CPU-intensive; local in-process throttling is not distributed |
| Path traversal | Media paths required review | IDs and server-generated filenames only; media responses resolve persisted server-owned paths; no client path is joined | Endpoint and code-path review | Local operator retains filesystem access |
| CORS | Broad prototype configuration | Exact origins from `CORS_ORIGINS`, defaulting only to `http://localhost:3000`; credentials disabled | CORS preflight tests and live browser call | Configuration must be set correctly when origin changes |
| Request abuse | No explicit OCR throttle | Upload rate limit per client, bounded body/image size, request IDs | Rate-limit and size tests | In-memory state resets with process and is unsuitable for multiple instances |
| SQL injection | Mixed legacy query construction risk | Parameterized SQLite queries; filter values never interpolated into SQL text | Search/filter tests and source review | SQLite is not an internet-scale multi-tenant datastore |
| Database integrity | Legacy schema and two database files were ambiguous | One configured database; additive migrations; WAL, busy timeout, foreign keys, indexes; original result/provenance retained; pre-recovery backup | Existing 59 records load; isolated migration/tests; backup exists | No encryption at rest or automated off-host backups |
| Stored markup | OCR/review values could enter generated reports | PDF text is HTML-escaped; React renders strings without raw HTML; CSV cells are formula-neutralized | Report/API tests and rendered PDF inspection | PDF libraries and viewers remain third-party parsers |
| Verdict integrity | Frontend and stale code could diverge | Only backend `rules.py` produces per-rule and overall status; rule metadata is validated; corrections rerun the same engine | Rule tests, live correction, source scans | Legal applicability and rule corpus require qualified review |
| Frontend headers | Framework defaults | CSP, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, nosniff, no-referrer, restrictive permissions, no powered-by header | production configuration review and browser response inspection | Next.js requires inline scripts/styles; nonce-based CSP is future hardening |
| Secrets | Environment/recovery artifacts could be committed | `.env*`, SQLite/database files, uploads, reports, backups, temporary renders, venvs, and build outputs ignored; no embedded credentials found | repository secret-pattern scan | Root has no Git metadata, so staging state cannot be inspected |
| Dependencies | npm audit reported five high findings | Next.js upgraded to 15.5.24; PostCSS fixed at 8.5.26; unused dependency surface removed; exact Python versions pinned | final `npm audit`: zero; `pip-audit`: no known vulnerabilities | ESLint 9 is development-only and its upstream support lifecycle should be monitored |
| Information disclosure | Diagnostics could reveal implementation details | API errors are normalized; database path is not exposed by the UI; reports use cautious product wording | error-state and system-page browser review | System capability data is visible to any local user because auth is absent |
| Auditability | Review and corrections were conflated | Append-only audit events identify automated evaluation, corrections, rule reruns, and independent human review | API tests and live browser flow | Local administrators can alter SQLite directly |

## Header policy

Production responses use a CSP restricted to the application and configured API origin. `unsafe-eval` is enabled only during development; it is absent from production builds. `unsafe-inline` remains for Next.js runtime styles/scripts. Object embedding and framing are denied, form actions and base URIs are same-origin, camera access is limited to self, and microphone/geolocation are disabled.

## Dependency evidence

- Baseline npm audit: 5 high-severity advisories across the legacy Next.js/PostCSS/minimatch development tree.
- Final npm audit: 0 vulnerabilities.
- Final Python audit: no known vulnerabilities in pinned runtime/test requirements.
- Package installation and audits were performed against the lockfile/requirements in this repository.

## Deliberate deployment boundary

Do not expose this build directly to the internet. Before any public or operational pilot, add identity, role-based authorization, CSRF/session strategy as appropriate, tenant/data-access controls, an external rate limiter and job queue, production database/object storage, encryption and retention policy, malware scanning where required, centralized redacted telemetry, backup/restore drills, dependency monitoring, and a qualified Legal Metrology rule review.

Final classification: **LOCAL DEMO READY ONLY**.

# Handbook feature matrix

> Historical handbook mapping. References to the former OCR inspection path are superseded by the Gemini-only architecture in `GEMINI_ONLY_IMPLEMENTATION_REPORT.md`.

The complete 127-page `LabelGuard_SIH26034_Handbook.pdf` was read before this classification. The handbook is product guidance, not legal authority. Citations below are traceability metadata and require legal verification.

Status vocabulary: **Implemented**, **Partial**, **Excluded**, or **Deferred**. Priority vocabulary follows the handbook: **MUST**, **SHOULD**, **OPTIONAL**, **DO NOT BUILD**.

## Product and workflow

| Requirement | Priority | Status | Evidence / decision |
|---|---|---|---|
| Clear problem/decision-support positioning | MUST | Implemented | README, app shell, dashboard, report, and result panels consistently say screening—not certification. |
| Image upload | MUST | Implemented | Real multipart upload with preview, validation, size/type/content constraints, and error recovery. |
| Device camera capture | SHOULD | Implemented | `getUserMedia`, environment-facing preference, capture/cancel, permission fallback to upload. File upload remains the judge-safe path. |
| Package context before evaluation | MUST | Implemented | Unknown/domestic/imported scope plus optional category persisted with inspection. |
| Truthful processing state | MUST | Implemented | UI says one synchronous request and does not invent percentage/substage completion. |
| Strong headline result | MUST | Implemented | Backend result shown with cautious labels: no issue flagged, potential non-compliance, manual review required. |
| Retake/image guidance | MUST | Implemented | Resolution, blur, glare/readability, local contrast, warnings and guidance are stored and surfaced. |
| Responsive/mobile workflow | MUST | Implemented | Mobile header/nav, stacked forms/metrics/cards, horizontally contained tables. Browser checked 390×844 and 1440×900. |
| Loading, empty, error, and not-found states | MUST | Implemented | Shared states used across data routes; unavailable backend is explicit. |
| Judge-safe demo fixtures | SHOULD | Implemented | Five watermarked generated fixtures: readable, missing MRP, rotated, blurred, malformed MRP. |

## OCR, extraction, and evidence

| Requirement | Priority | Status | Evidence / decision |
|---|---|---|---|
| OCR text extraction | MUST | Implemented | Paddle preference with deterministic Tesseract fallback. OCR engine stored per inspection. |
| Generalized right-angle orientation | MUST | Implemented | 0/90/180/270 candidates scored from declaration anchors/text/confidence; selected angle stored. |
| Bounding boxes and evidence image | MUST | Implemented | Field/rule boxes mapped back to original coordinates; generated evidence PNG and interactive overlays. |
| Do not fabricate evidence locations | MUST | Implemented | Invalid/zero boxes are omitted and explicitly presented as not localized. |
| Common/generic name | MUST | Implemented | Anchored generalized extraction and LMPC-NAME-001. |
| Responsible party name/address | MUST | Implemented | Manufacturer, packer, importer, and marketer parsed separately; best complete role pair evaluated. |
| Net quantity | MUST | Implemented | Anchored normalized metric extraction; malformed anchored values retained for format rule. |
| MRP | MUST | Implemented | Anchored INR/Rs/₹ numeric extraction, unit-price rejection, malformed anchored values retained. |
| Manufacture/pre-pack month/year | MUST | Implemented | MFD/MFG/manufactured/packed variants, numeric and month-name formats. |
| Consumer care contact | MUST | Implemented | Email/phone/web detection around care/feedback/helpline anchors. |
| Country of origin | MUST (imported goods) | Implemented | Scope-aware imported-only rule; no domestic false failure. |
| Layout variation | MUST | Implemented | Inline, same-row, and below-anchor spatial matching; paragraph-aware OCR line grouping. |
| Low-confidence handling | MUST | Implemented | Below rule confidence floor becomes UNCERTAIN rather than FAIL. |
| Multilingual OCR | SHOULD | Partial | Requested languages configurable (`eng+hin`); verified runtime has English only. No claim of Hindi accuracy without installed trained data and evaluation set. |
| Curved/complex packaging and perspective correction | SHOULD | Partial | Quality gate/manual review works; no generalized geometric dewarping model was added. |
| Targeted OCR re-crops | OPTIONAL | Implemented | Unresolved strong OCR anchors and Gemini region hints trigger bounded local Tesseract PSM 6/11 retries; accepted evidence still requires deterministic validation. |

## Deterministic compliance doctrine

| Requirement | Priority | Status | Evidence / decision |
|---|---|---|---|
| Backend-only verdict ownership | MUST | Implemented | `rules.py` is sole status owner; frontend renders returned values. |
| Versioned external rule definitions | MUST | Implemented | Seven validated JSON rules, active flags, rule versions, engine version `LMPC-ENGINE-2.0`. |
| Required rule metadata | MUST | Implemented | ID/version/active/field/source/description/type/severity/confidence/missing policy validated at load. |
| Missing declaration doctrine | MUST | Implemented | Missing evidence → UNCERTAIN, matching handbook caution. |
| Present malformed declaration doctrine | MUST | Implemented | Retained anchored raw text → deterministic pattern FAIL. |
| Overall result policy | MUST | Implemented | Any FAIL → potential issue; otherwise uncertainty/quality/no OCR → manual review; otherwise no issue flagged. |
| Rule source/version/applicability shown | MUST | Implemented | Finding matrix, Rule Explorer, API, and PDF. |
| Legal verification warning | MUST | Implemented | Every rule flags legal verification required; UI/report/docs repeat limitation. |
| LLM legal verdicts | DO NOT BUILD | Excluded | Optional Gemini reading/explanation exists, but repository integrity tests and architecture prevent any model from setting finding or overall status. |
| Frontend status inference | DO NOT BUILD | Excluded | No frontend compliance calculation exists. |
| Automatic category/exemption inference | DO NOT BUILD for prototype | Excluded | Category is recorded but exception applicability requires officer review. |

## Human review, persistence, and outputs

| Requirement | Priority | Status | Evidence / decision |
|---|---|---|---|
| Persist inspections/history | MUST | Implemented | Additively migrated SQLite; pre-existing records remain loadable and historical-schema migration is covered by regression tests. |
| Manual review states and notes | MUST | Implemented | Five review dispositions, actor, timestamp, notes, separate from automated result. |
| Correct OCR text | MUST | Implemented | Whitelisted fields, non-empty/reason constraints, original value, actor, source, box preservation. |
| Rerun deterministic rules after correction | MUST | Implemented | Same rule engine, regenerated findings/status/evidence; original status retained. |
| Chronological audit trail | MUST | Implemented | Creation, OCR, initial evaluation, corrections, re-evaluation, reviews. |
| Review queue | SHOULD | Implemented | Manual-review results and incomplete/correction/reinspection review states. |
| Search/filter history | SHOULD | Implemented | ID/filename/detected text, automated/review status, date filters. |
| PDF report | MUST | Implemented | Metadata, cautious automated result, quality, fields, findings/source, review, corrections, audit, OCR, evidence, notice. |
| CSV/JSON export | SHOULD | Implemented | History exports; CSV formula prefixes neutralized. |
| Dashboard analytics | SHOULD | Implemented | DB-backed status/quality/review/daily counts, explicitly descriptive. |
| Offline/demo mode | OPTIONAL | Excluded | Silent fallback was unsafe. Synthetic image fixtures use the real backend instead. |

## Security, quality, and operations

| Requirement | Priority | Status | Evidence / decision |
|---|---|---|---|
| Upload size/type/content validation | MUST | Implemented | 10 MB bounded read, supported decoded encoding, 40M-pixel cap, safe filenames. |
| Safe media/report paths | MUST | Implemented | Resolved path must be a direct file under configured upload directory; reports are ID-addressed. |
| Restricted CORS | MUST | Implemented | Exact configurable origins, GET/POST/OPTIONS, limited request headers, no credentials. |
| Security headers | SHOULD | Implemented | API and Next responses: nosniff, frame denial, referrer policy; frontend CSP and camera-limited permissions policy. |
| Rate limiting | SHOULD | Implemented (prototype) | In-process per-client upload window. Production needs shared storage/gateway controls. |
| Test isolation | MUST | Implemented | Autouse temp DB/media; live test refuses writes without explicit opt-in. |
| Unit/contract/security/orientation tests | MUST | Implemented | Final suite covers rules, extraction, scenarios, API, correction/review/report, CORS, upload and security. |
| Full-stack browser verification | MUST | Implemented | Real upload, good/missing/malformed/rotated/blurred cases, correction, review, audit, all routes, desktop/mobile. |
| Dependency audit | MUST | Implemented | `npm audit` zero; `pip-audit` zero known vulnerabilities for pinned requirements. |
| Authentication and RBAC | OPTIONAL / beyond handbook demo scope | Deferred | Absence documented; prevents public/production deployment. |
| Cloud deployment | OPTIONAL | Partial | Render/Vercel configuration and deployment guidance are present; no public deployment is performed automatically. Authentication remains a production blocker. |
| Blockchain provenance | DO NOT BUILD | Excluded | Adds no handbook value to evidence accuracy. |
| Microservices/event bus | DO NOT BUILD | Excluded | Monolith is clearer and safer for this prototype scale. |
| Chatbot/LLM explanation | DO NOT BUILD for verdict path | Implemented outside verdict path | Optional Gemini plain-language explanation runs only after deterministic findings; a deterministic fallback always remains available and neither path can change the verdict. |

## Legal source traceability used for the implemented baseline

- Rule 6(1)(a): manufacturer/packer/importer name and address responsibilities.
- Rule 6(1)(aa): country of origin for imported products.
- Rule 6(1)(b): common/generic name.
- Rule 6(1)(c): net quantity.
- Rule 6(1)(d): month/year declaration, with category-specific exceptions requiring review.
- Rule 6(1)(e): retail sale price.
- Rule 6(2): consumer complaint contact details.

These mappings were checked against Department of Consumer Affairs consolidated Rules/FAQ material during recovery, but a qualified officer must verify current applicability and amendments before operational use.

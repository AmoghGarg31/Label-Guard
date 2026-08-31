# LabelGuard codebase audit

> Historical snapshot. Active inspections now use one Gemini visual scan followed by deterministic field validation and `rules.py`; see `GEMINI_ONLY_IMPLEMENTATION_REPORT.md`.

## Inventory reviewed

- 30 first-party backend files after cleanup: API, persistence, OCR, extraction, quality, evidence, report, seven rule files, two scripts, and eleven test/support files.
- 30 first-party frontend files after cleanup: nine routes plus error/not-found handling, eight shared components, typed client/contracts, and build/style/security configuration.
- 60 first-party application files in total; generated lockfiles, build output, caches, data, and local environment files are excluded from this count.
- Root README, five synthetic fixtures plus their generator, the handbook PDF, and all required recovery documents.
- Every canonical backend endpoint and every frontend route was exercised or inspected. Generated dependencies, build output, bytecode, SQLite contents, uploads, and generated reports are not counted as first-party source.

## Final architecture

```text
Browser (Next.js)
  ├─ upload/camera + package context
  ├─ evidence/review/correction UI
  └─ history/rules/analytics/system UI
          │ exact CORS + typed JSON/multipart
          ▼
FastAPI
  ├─ encoded-image validation + quality gate
  ├─ Paddle preference / Tesseract fallback
  ├─ 0/90/180/270 orientation + bbox remapping
  ├─ deterministic field extraction
  ├─ validated JSON rule engine (sole verdict owner)
  ├─ evidence image + PDF report
  └─ review/correction/audit/export APIs
          │
          ▼
SQLite + local uploads/reports
```

## Canonical contract

`POST /inspect` returns a persisted numeric `id`, backend-owned `overall_status`, extracted fields with text/confidence/bounding box/source, versioned findings with citation/applicability, quality metrics, OCR engine, chosen orientation, relative image route, package context, and rule-engine version. Detail adds original metadata, OCR text, report URL, review, corrections, audit events, and original automated status.

Canonical resource groups:

- Inspection: `/inspect`, `/inspection/{id}`, image, evidence image, correction, review, audit.
- Operations: `/history`, `/review-queue`, `/analytics`, CSV/JSON exports.
- Explainability: `/rules`, `/report/{id}`.
- Readiness: `/system/status` and `/health`.
- Backward-compatible `/api/...` aliases remain but are excluded from OpenAPI duplication.

## Significant defects and resolutions

| Problem/root cause | Resolution and verification |
|---|---|
| Silent mocks masked network and contract failures. | Removed mock store and all automatic fallback branches. Browser now renders an actionable API error. Full-stack browser checks used isolated live data. |
| Frontend recomposed incomplete inspection objects and broken upload URLs. | Added one typed contract and canonical media/report helpers. Browser verified original/evidence images and report link. |
| Rule/citation data existed in UI. | UI only renders findings/rules returned by FastAPI. Source/version/applicability are backend metadata. Source search confirms no frontend status calculation. |
| Country of origin was treated as universal. | Added package context and imported-only applicability. Domestic skips the rule; unknown scope can be uncertain. Rule tests cover all three cases. |
| Missing and malformed declarations collapsed together. | Missing remains `UNCERTAIN`; visibly anchored malformed MRP/net/date text is retained for deterministic `FAIL`. Browser verified malformed MRP → potential non-compliance. |
| OCR lines were merged by block/line only. | Grouping now includes paragraph identity. Synthetic live OCR separates declaration rows. |
| Orientation was not end-to-end generalized. | Deterministic candidate scoring for all right angles, with box remapping to original image. Real Tesseract tests cover 0/90/180/270; browser verified a 90° input. |
| White label stock was treated as glare. | Bright pixels only degrade status when sharp declaration-like dark content is absent. Tests cover readable white panels and washed-out frames. |
| Role extraction conflated manufacturer/packer/importer/marketer. | Separate role fields and responsible-party combination for Rule 6(1)(a); coverage UI reconstructs the combined evidence transparently. |
| Evidence boxes could render at `(0,0)`. | Invalid/zero boxes are omitted; UI explicitly says “not localized.” Tests cover zero-box behavior. |
| Corrections overwrote provenance/status context. | Preserve original extracted fields/status once, mark corrected source, keep box when valid, rerun rules, regenerate evidence, append correction and rule events. Browser and tests verified. |
| Dashboard and analytics were sample-derived. | Added real DB aggregation, review queue, filterable history, and safe exports. Browser showed counts from eight isolated live records. |
| Upload and media trust boundaries were weak. | Actual encoded-format verification, 40M-pixel cap, 10MB read cap, filename sanitation, safe resolved media paths, MIME detection, and upload rate control. Security tests cover them. |
| PDF layout broke long labels and dark headers. | Paragraph-based wrapping, widened metadata label column, white paragraph header style, cautious status language, INR-safe text, and grouped evidence heading/image. Rendered all pages for visual QA. |
| Tests could use the working database. | Autouse temporary DB/media fixture; live test requires explicit write opt-in and documented temporary data directory. |
| Next 13 and unused UI dependencies created audit findings. | Upgraded deliberately to maintenance-LTS Next 15.5.24/React 19, forced patched PostCSS 8.5.26, removed 48 unused UI/hook scaffold files and stale packages. `npm audit` is clean. |
| Remote Google font made offline build fail. | Replaced it with a system font stack. Production build now completes offline. |
| Competing Express scaffold confused ownership. | Removed unused `backend/src`, TypeScript config, package manifest, and build script after reference audit. FastAPI is the single backend. |

## Frontend route audit: before → after

| Route | Before | After |
|---|---|---|
| `/` | Five-row mock-derived metrics and narrow demo layout. | Real analytics/history/readiness, operational metrics, workflow, responsive rail/mobile nav. |
| `/inspections/new` | Fake staged API flow, automatic mock success, camera icon only. | Real file/camera input, context, truthful single-request processing, quality/OCR/orientation/result/evidence summary. |
| `/inspections/[id]` | Reconstructed fields, hardcoded actor/location, limited evidence. | Backend detail, why-result panel, zoom/rotate evidence, declaration matrix, OCR corrections, review, audit, PDF. |
| `/history` | Basic unfiltered list. | Search/status/review/date filters, real quality/OCR/scope, CSV/JSON exports, empty/error/loading states. |
| `/rules` | Hardcoded metadata with incorrect citations/IDs. | Live validated rules, version/applicability/confidence/source, legal-verification warning. |
| `/review` | Absent. | Real review queue linked to evidence workspaces. |
| `/analytics` | Absent. | Descriptive status, review, and 14-recorded-day activity views. |
| `/system` | Absent. | DB/OCR/language/orientation/rule readiness and explicit integrity boundary. |
| error/404 | Inconsistent. | Shared actionable error and styled not-found states. |

## Deliberate exclusions and limitations

- No authentication/role enforcement: handbook scope and local prototype deployment only. This blocks public production use.
- No LLM analysis/verdict, chatbot, blockchain, microservices, or cloud deployment.
- No automatic legal category/exemption inference.
- PaddleOCR remains optional; verified runtime used Tesseract English with `osd` available and Hindi requested only when installed.
- SQLite/local media/in-process rate limit are appropriate for local demo, not horizontally scaled production.

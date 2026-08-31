# LabelGuard Gemini-only implementation report

Verification date: 2026-08-31 (Asia/Calcutta)

## Final architecture

`POST /inspect` performs deterministic image decoding/quality analysis, sends the single original package image to one routed Gemini visual reader, validates every returned candidate with deterministic field-specific validators and evidence geometry, and passes only accepted fields to `backend/rules.py`. Only `evaluate_rules()` and `overall_status()` assign finding statuses or the final compliance result. Local OCR is not imported or invoked by the inspection path and there is no OCR fallback.

The normal inspection makes one visual extraction request. A transient provider failure may retry the same reader/model and then route to configured fallback models. These are availability attempts, not independent extraction layers. Optional Gemini explanation is disabled by default and, if enabled, runs only after the deterministic verdict.

## Root causes corrected

1. The repository root had no `package.json`, so `npm run dev` failed with `ENOENT`.
2. The active backend combined local OCR and Gemini reconciliation, contrary to the requested single-reader design.
3. Gemini provider/model failures had no configurable image-quality route, ordered fallback route, or application-side request controls.
4. Equivalent visible and normalized manufacture dates such as `01/06/2026` and `2026-06-01` compared as unequal.
5. Windows backend auto-reload could leave stale listeners during supervised root development runs.

## Routing and rate controls

- Standard image: `GEMINI_FAST_MODEL`, then primary and ordered fallbacks.
- Difficult image: `GEMINI_QUALITY_MODEL`, then primary and ordered fallbacks.
- Verified local route: `gemini-3.7-flash`; quality `gemini-3.1-pro-preview`; fallbacks `gemini-3.6-flash`, `gemini-2.5-flash`.
- Sliding process-local provider-attempt limit: 10/minute by default.
- Concurrency limit: 2 by default.
- Transient attempts: 2/model by default; every actual provider attempt consumes the sliding-window allowance.
- Internal limit exhaustion returns HTTP 429 with `Retry-After`. Required-reader failure returns an explicit error and never starts local OCR.

## Real Pintola regression

Source image: `backend/data/uploads/c0b88bf7-b4d9-4410-93d1-31921f656c3c.jpg`.

The live provider returned 503 twice for `gemini-3.7-flash`; routing then succeeded with `gemini-3.6-flash`. A subsequent validation run used the cached successful visual response. Deterministically accepted values were:

- MRP: `₹180.00` at original-image box `[292,705,420,743]`.
- Net quantity: `350 g` at `[295,976,381,1023]`.
- Manufacture date: `01/06/2026` at `[258,871,404,917]`.
- Consumer care: `78080 58080, support@pintola.in` at the union box `[110,565,381,658]`.
- Manufacturer: `Das Superfoods Private Limited`.
- Marketer: `Das Foodtech Private Limited`.

`₹0.51/g` was not accepted as MRP. The deterministic regression test also injects `USP: ₹0.51/g` as an MRP candidate and confirms rejection. Common/generic name, role addresses lacking anchor-bearing candidate evidence, and country of origin remain unset. The deterministic final status is therefore `manual_review_required`.

## Verification gates

- Backend: 194 passed; one third-party Starlette/httpx deprecation warning.
- Gemini routing/rate-limit/authority focused tests: passed.
- Frontend TypeScript: passed.
- Frontend ESLint: passed with zero warnings.
- Next.js production build: passed; all ten routes generated.
- `npm audit`: zero known vulnerabilities in root and frontend checks.
- `pip-audit`: no known vulnerabilities.
- Root `npm run dev`: backend on 8000 and frontend on 3000 became ready; health reported `gemini_only`, no local OCR, configured routing/limits, and deterministic verdict authority. Shutdown left no listeners.

## Remaining limitations

The limiter is process-local; multi-instance deployment needs a shared Redis/API-gateway limiter. Model availability, quota, latency, and structured-output behavior remain external dependencies. The prototype intentionally leaves unclear or unanchored fields unset and requires manual review. Authentication/RBAC and production regulatory/legal validation remain outside the current prototype scope.

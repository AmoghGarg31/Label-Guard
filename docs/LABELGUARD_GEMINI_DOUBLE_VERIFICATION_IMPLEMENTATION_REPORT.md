# LABELGUARD GEMINI DOUBLE-VERIFICATION IMPLEMENTATION REPORT

> Superseded. LabelGuard no longer performs local OCR plus Gemini double verification. The active design uses one Gemini visual reader and deterministic backend validation; see `GEMINI_ONLY_IMPLEMENTATION_REPORT.md`.

Report date: 31 August 2026

Scope: implementation and re-audit of the Gemini Vision double-verification architecture requested in frontend/final prompt.md.

## 1. Architecture before

LabelGuard previously processed an uploaded package image through deterministic image-quality checks and OpenCV preprocessing, Tesseract OCR, generic field extraction, deterministic rules.py evaluation, overall-status calculation, persistence, UI display, and PDF reporting. OCR was the only visual reader. The rule engine already owned PASS, FAIL, UNCERTAIN, and the overall status.

## 2. Architecture after

The implemented flow is:

IMAGE → deterministic quality analysis/enhancement → independent local OCR + independent Gemini visual extraction → deterministic evidence reconciliation and targeted local OCR → existing rules.py → PASS/FAIL/UNCERTAIN and overall_status → optional downstream Gemini explanation → deterministic recommendation/report.

Gemini is an evidence candidate source only. It cannot write a finding status or overall status. If it is disabled or unavailable, the original OCR and deterministic rule path continues.

## 3. Files changed

Backend:

- backend/gemini_vision.py: new isolated visual reader, strict schemas, timeout/retry handling, redaction, and downstream explanation service.
- backend/evidence_reconciler.py: new deterministic OCR/Gemini reconciliation and provenance logic.
- backend/app.py: orchestration, cache use, targeted OCR, additive API metadata, explanation/recommendation fallback, and audit events.
- backend/image_quality.py: one conservative enhanced full-frame variant when quality analysis indicates benefit.
- backend/ocr_engine.py: original/upright coordinate mapping and safe engine availability status.
- backend/database.py: additive verification, Gemini status, explanation, recommendation, performance columns, cache table, and migration.
- backend/report.py: result authority label, verification provenance, AI status, explanation, recommendations, audit data, and advisory disclaimer.
- backend/requirements.txt: google-genai 2.20.0.
- backend/.env.example: disabled-by-default Gemini configuration with an empty key.
- backend/tests/test_gemini_double_verification.py: deterministic mock and integrity suite.

Frontend:

- frontend/lib/types.ts: additive verification, AI summary, recommendation, performance, and system-status types.
- frontend/app/inspections/new/page.tsx: six processing stages, disclosure, AI state, provenance, explanation, and recommendations.
- frontend/app/inspections/[id]/page.tsx: verification state, conflict/provenance display, explanation, and recommendations.
- frontend/app/system/page.tsx: independent Tesseract, PaddleOCR, Gemini, database, and rule-engine status.
- frontend/app/page.tsx: AI mode in system readiness.
- frontend/.env.local: removed a misplaced Gemini key and retained only NEXT_PUBLIC_API_BASE_URL.

Operations and documentation:

- render.yaml: server-side Gemini variables; GEMINI_API_KEY is an external secret.
- README.md and docs/DEPLOYMENT.md: configuration, privacy, architecture, deployment, and key-handling guidance.
- This report.

The Gemini pass did not modify backend/rules/net_quantity.json or backend/rules/consumer_care.json. Those files were changed during the earlier generic extraction pass, as recorded in docs/LABELGUARD_FINAL_LAYOUT_INDEPENDENT_EXTRACTION_REPORT.md. Their exact semantic changes were:

| Rule | Before | After | Unchanged behavior |
|---|---|---|---|
| Net quantity | Recognized numeric mass/volume units: kg, g, mg, l, ml, cl. | Also recognizes count units unit, units, pc, and pcs. Current pattern: ^[0-9]+(?:[.,][0-9]+)?\s*(?:kg\|g\|mg\|l\|ml\|cl\|units?\|pcs?)$ | Same deterministic presence/pattern check, 0.55 confidence floor, high severity, and UNCERTAIN when missing. Nutrition/unit-price rejection remains in extraction validation. |
| Consumer care | Recognized direct phone, email, website, or consumer-care keyword channels. | Also accepts a postal contact only when address semantics such as plot/road/street/sector/district/PIN/India are associated with a six-digit PIN. | Same deterministic presence/pattern check, 0.55 confidence floor, high severity, and UNCERTAIN when missing. |

There is no .git directory at the supplied project root, so a byte-for-byte historical diff cannot be independently reconstructed. The semantic before/after above is supported by the prior extraction report and the current version 3.0 rule definitions.

## 4. Gemini SDK/model/configuration

The backend uses Google's current google-genai SDK, pinned to 2.20.0. The default model is configurable as gemini-3.7-flash. Server-only variables are GEMINI_ENABLED, GEMINI_API_KEY, GEMINI_MODEL, and GEMINI_TIMEOUT_SECONDS. Default is disabled; enabled without a key reports not configured and does not crash. The service uses inline image bytes and structured Pydantic output. References: https://googleapis.github.io/python-genai/, https://ai.google.dev/gemini-api/docs/structured-output, and https://pypi.org/project/google-genai/.

## 5. Image preprocessing

The original image remains the primary evidence. Existing deterministic orientation, quality, enhancement, and OCR processing is preserved. At most one extra full-frame enhanced variant is produced when useful: conservative upscaling, CLAHE, and mild sharpening. It does not reconstruct missing pixels, alter aspect ratio, or create synthetic evidence.

## 6. Gemini structured schema

GeminiFieldCandidate and GeminiExtractionResponse are strict extra-forbid Pydantic schemas. Supported declarations include common name; separate manufacturer, packer, marketer, and importer names/addresses; net quantity; MRP; manufacture/packing/expiry-related dates; consumer phone/email/website/address; and explicit country of origin. Candidate fields include raw text, normalized value, readability, model score, normalized bbox_2d, evidence text, and notes. Overall/finding status fields are not allowed by the schema.

## 7. Independent OCR flow

The local Tesseract path receives the original deterministic variants, returns token geometry and candidates, and builds the existing extracted_fields structure. Its initial run does not receive Gemini output. The pre-existing OCR-only pipeline and public field shape remain available and tested.

## 8. Independent Gemini flow

The first Gemini visual call receives image bytes and a strict visual-reading prompt, not OCR values. The prompt forbids inference, nutrition-as-net-quantity, unit-price-as-MRP, expiry-as-manufacture-date, role merging, COO inference from an address, and any compliance verdict. One original image and at most one enhanced image are sent in one request.

## 9. Evidence reconciler

backend/evidence_reconciler.py compares independently produced candidates using AGREED, OCR_ONLY, GEMINI_ONLY, CONFLICT, UNREADABLE, and MISSING states. Gemini evidence_text is passed back through the existing generic extractor/validators; Gemini normalized_value is never injected directly. Only reconciled accepted fields reach evaluate_rules.

## 10. Agreement behavior

Canonical equality handles equivalent forms such as ₹170 and ₹170.00 or compatible net-quantity formatting. An agreement retains OCR evidence geometry, records OCR_GEMINI_AGREED provenance, and does not force confidence to 100%.

## 11. OCR-only behavior

A valid OCR candidate is preserved when Gemini misses it, is disabled, or fails. Provenance is OCR_ONLY. Gemini is not a mandatory voter and cannot erase good deterministic OCR evidence.

## 12. Gemini-only behavior

A Gemini-only value is not accepted as statutory evidence. Its normalized bbox is treated as a region hint, targeted local OCR runs on that region, and the candidate must match a deterministically validated OCR result. Otherwise the field remains unverified/uncertain and requires review.

## 13. Conflict behavior

Conflicting OCR and Gemini values trigger targeted local OCR. If a validated targeted result resolves the conflict, that value is accepted with traceable provenance. If not, the accepted field is cleared, both readings are retained in verification metadata, confidence is lowered, and manual review is required. No arbitrary winner is selected.

## 14. Targeted OCR verification

Normalized Gemini coordinates are clamped, mapped to original pixels, mapped into the upright OCR coordinate system, and used only to crop original/enhanced pixels. Local Tesseract PSM 6 and PSM 11 variants are compared. A result must pass the normal extractor/field validator and canonical equality check.

## 15. Field validator integrity

Tests prove that nutrition “100 g” cannot become net quantity, “₹0.63 per g” cannot become MRP, an Indian address cannot become COO, marketer cannot silently become manufacturer, and expiry/best-before text cannot become manufacture date. Explicit role and origin evidence remains acceptable. Gemini cannot bypass these checks.

## 16. Evidence/bbox integrity

Gemini bbox_2d is normalized [ymin, xmin, ymax, xmax] in 0–1000 space and remains a hint. Final public evidence uses [xmin, ymin, xmax, ymax] absolute original-image pixels from OCR/targeted OCR whenever a field is accepted. No fake precise Gemini rectangle is displayed as authoritative evidence.

## 17. Rule-engine isolation proof

gemini_vision.py does not import rules.py. Repository search found no assignment from Gemini output to overall_status or finding.status and no conditional that treats a Gemini “compliant” or “fail” statement as a verdict. app.py reconciles evidence first and then calls the existing evaluate_rules and overall_status functions. Integrity tests inject contradictory Gemini words and explanations; the deterministic backend status remains unchanged.

## 18. Plain-language explanation

Only after deterministic findings and overall status are complete may a separate Gemini call explain the supplied authoritative facts. Its prompt forbids changing the verdict, inventing violations or requirements, and claiming government certification. Contradictory or invalid output is rejected.

## 19. Recommendation generation

Every inspection receives three or four concise operational next-step lines derived from deterministic findings and review state. Recommendations avoid penalties, prosecution, enforcement orders, and unsupported legal conclusions.

## 20. Deterministic explanation fallback

A template-based explanation and recommendation are always available. Missing key, disabled Gemini, timeout, network error, auth/quota error, malformed response, or contradictory explanation cannot remove or fail the result screen.

## 21. UI changes

The existing design is retained. The inspection flow shows Image Quality, Local OCR, AI Visual Verification, Evidence Reconciliation, Deterministic Rule Evaluation, and Report Preparation without fake percentages. Inspection pages show concise AI availability, OCR/AI provenance, conflicts/manual review, explanation, and recommendations. The UI discloses external Gemini image processing only when enabled/configured. No frontend code computes compliance.

## 22. PDF changes

Reports now identify the Automated Deterministic Screening Result, retain evidence/findings, show AI visual-verification status and per-field provenance, include the plain-language explanation, recommended next step, inspector review and audit trail, and carry this exact disclaimer:

“The compliance screening result is generated by LabelGuard's configured deterministic rule engine. AI-assisted visual verification and explanations are advisory and do not independently determine legal compliance.”

## 23. Audit trail

The pipeline records IMAGE_QUALITY_COMPLETED, OCR_COMPLETED, GEMINI_VERIFICATION_COMPLETED or GEMINI_VERIFICATION_UNAVAILABLE, EVIDENCE_RECONCILED, RULES_EVALUATED, and AI_EXPLANATION_GENERATED. Full request/image payloads and API keys are not logged. Manual corrections use MANUALLY_CORRECTED provenance and rerun deterministic evaluation/explanation.

## 24. Security/API-key audit

A real GEMINI_API_KEY was discovered misplaced in frontend/.env.local during this pass. It was not printed, copied, or reused. The file was rewritten to retain only NEXT_PUBLIC_API_BASE_URL. Final scans report no Gemini key identifiers in frontend source/config, no key-shaped material in the reviewed repository files, zero key markers in both local SQLite databases, and no key in /system/status tests. The old key should be rotated before enabling the service because it was stored in a frontend directory, even though it was not NEXT_PUBLIC-prefixed.

No .git metadata exists at this project root, so Git history could not be audited. Before the first GitHub push, initialize a repository only after confirming .gitignore excludes .env files, databases, uploads, reports, caches, and build output. Configure a newly rotated key only in the backend environment or Render secret store.

## 25. Failure/fallback behavior

Gemini is disabled by default and is never a single point of failure. Missing configuration, network failure, timeout, 5xx, model failure, malformed/schema-invalid output, quota, and auth errors return a safe unavailable status while OCR/rules/reporting continue. There is at most one retry for timeout/5xx/transient failures; quota/auth errors are not retried. Errors are redacted and the configured key is never exposed.

## 26. Distorted-image benchmark

Locally available deterministic sample measurements:

| Fixture | OCR-only time | Quality/orientation | Reconciled safe result |
|---|---:|---|---|
| samples/01-readable-domestic.png | 2,223.8 ms | Good, 0° | Six PASS, compliant |
| samples/03-rotated-90.png | 6,066.4 ms | Good, corrected to 90° | Same accepted values; six PASS, compliant |
| samples/04-low-quality-blur.png | 6,489.5 ms | Review; blur/glare | No invented fields; six UNCERTAIN, manual review |

The repository did not contain separate real fixtures for every requested perspective, curvature, crumple, low-resolution, shadow, and occlusion condition. Distortion enum/schema behavior, orientation, blur/glare quality handling, bbox conversion, and reconciliation are covered in tests. No live Gemini key was available, so a genuine Gemini candidate/reconciled comparison cannot honestly be reported for these fixtures. Severe unreadable cases remain safely uncertain.

## 27. Real-package regression

All locally identified package regressions were rerun without product hardcoding. Gemini was unavailable because no backend key was configured, so each run correctly used OCR-only/fallback behavior:

| Package/file | Time | Accepted result summary |
|---|---:|---|
| Haldiram, backend/data/uploads/69104069-d0d6-42cc-9a61-4292ef2bb854.jpg | 17,238.4 ms | Consumer care and COO accepted; 2 PASS, 5 UNCERTAIN; manual review |
| Snackible, backend/data/uploads/cdc7f4ce-897a-40e7-b237-c336b17a1b44.jpeg | 15,147.4 ms | 55 g, ₹50, 03/08/2026 and phone accepted; 4 PASS, 3 UNCERTAIN |
| UNIBIC, backend/data/uploads/96c71c00-a8ca-4d5c-af33-6a517aebe08f.jpg | 37,008.6 ms current rerun | Marketer/contact accepted; net quantity and MRP deliberately empty; manual review |
| Green Basket, backend/data/uploads/c0bbaf39-9f05-4466-a46d-1dcc8451c2d7.png | 6,201.8 ms | Name/address, 500 g, ₹650.0, 15/08/2026, care and COO; 5 PASS, 1 FAIL, 1 UNCERTAIN |
| Khari, backend/data/uploads/81f71ec3-d66d-4229-9a65-9d4f269bea5e.jpg | 23,371 ms | COO only; 1 PASS, 6 UNCERTAIN; manual review |

UNIBIC inconsistency resolution:

1. Exact file used: C:\Users\amogh\OneDrive\Desktop\LabelGuard\backend\data\uploads\96c71c00-a8ca-4d5c-af33-6a517aebe08f.jpg.
2. Dimensions: 1600 × 720; size 164,520 bytes; SHA-256: 3D6CF434FC674F49D41D0E1495673B444B27BBCA7A8D3462808D9F6C755B6615.
3. Relevant raw OCR includes “Quantity per 100 g”, noisy “BISCUITS NET WEIGHT: 2270'S”, “BISCUITS NET WEIGHT. 2705”, “BISCUITS NET WEIGHT: 270”, “BISCUITS NET WE'GHT: 270g”, “MRP”, “Rs. 120. UU Rs .0.6”, “Rs.0.63 Per”, and “marketed by: Unibic Foods India Private Limited...”.
4. Extracted MRP: empty/unresolved, not ₹120.
5. Extracted net quantity: empty/unresolved, not 100 g.
6. Same real image previously tested: YES. Identical SHA-256 copies are stored as 208a38ed-fd86-47fd-9aa2-662667832144.jpeg, 7df8eda1-bd5f-4694-9a4f-ffb86f994b99.jpg, 9e7d5ec2-c2ca-4b5c-875e-cae1150f441d.jpg, and b8e4c52f-56b8-4b7a-8fab-2410126e1da0.jpeg.

Visual inspection of the real price panel supports approximately ₹170.00 and 270 g, but local OCR produced conflicting/noisy price text and did not deterministically validate the visible MRP. The earlier “100 g / ₹120” report was therefore an incorrect characterization of raw OCR artifacts from this same image: 100 g was nutrition context and ₹120 was a noisy price reading. Neither is accepted by the current extractor. With no live Gemini result and no successful targeted OCR corroboration, leaving both statutory fields uncertain is the correct safe behavior.

## 28. Backend tests

Final command: python -m pytest tests.

Result: 182 passed, 1 third-party Starlette/httpx deprecation warning, in 54.72 seconds. The suite includes API smoke tests, schema migration/historical records, mock Gemini agreement/OCR-only/Gemini-only/conflict paths, targeted OCR, timeout/retry/auth/quota/malformed/disabled/missing-key behavior, false-positive rejection, bbox conversion, caching, explanation success/fallback, and verdict-isolation tests.

## 29. Frontend gates

- npm run typecheck: PASS.
- npm run lint: PASS with zero warnings.
- npm run build: PASS using Next.js 15.5.24; ten routes/pages generated successfully.

## 30. npm audit

npm audit: PASS, 0 vulnerabilities. npm audit fix --force was not run. Python dependency audit also completed successfully after a transient PyPI timeout: no known vulnerabilities found.

## 31. Live Gemini test status

LIVE GEMINI TEST NOT RUN — API KEY NOT CONFIGURED

No success was fabricated and the misplaced frontend key was not reused. A newly rotated key must be configured only in the backend environment before a controlled live test.

## 32. Performance impact

OCR-only real/sample measurements ranged from about 2.2 seconds to 37.0 seconds depending on image complexity and OCR variants. Gemini request time is not available without a configured key. The configured server timeout is 15 seconds, with at most one controlled retry for a transient timeout/5xx failure. One inspection normally makes at most one visual extraction call and optionally one explanation call; targeted verification remains local OCR. Results are cached by image SHA-256, model, and schema version.

## 33. Remaining limitations

- A controlled live Gemini extraction/explanation run remains outstanding because no safe backend key is configured.
- The real UNIBIC image visibly appears to contain 270 g and ₹170.00, but the current local OCR did not validate the MRP. Its safe final state is manual review, not a claimed recovery.
- The complete requested real distorted-image matrix is not present in the repository; the available flat, rotated, and blurred fixtures were measured, while other failure types have unit/schema coverage.
- Tesseract is available; PaddleOCR is intentionally not installed and its optional fallback remains unavailable.
- The project root has no Git metadata, so historical secret scanning and an exact pre-edit rule JSON diff cannot be performed until a repository exists.
- The Starlette/httpx deprecation warning is third-party and non-failing but should be removed during a later dependency maintenance pass.

The double-verification implementation is ready for SIH integration and demo use in disabled/fallback mode. The project must not yet be described as “frozen”: rotate/configure a backend-only key, run one controlled live Gemini test, and recheck the UNIBIC image before freezing the release.

## FINAL VERDICT

**GEMINI DOUBLE-VERIFICATION READY FOR SIH**

This verdict means the architecture, deterministic safety controls, mocks, API/UI/PDF integration, migrations, and build/security gates are ready. It is not a claim that the project is frozen or that a live Gemini call has passed.

## FINAL REQUIRED QUESTIONS

1. Does rules.py remain the only automated compliance authority? **YES**
2. Can Gemini directly set overall_status? **NO**
3. Can Gemini directly set PASS/FAIL/UNCERTAIN? **NO**
4. Is Gemini extraction independent from initial OCR extraction? **YES**
5. Are OCR/Gemini disagreements handled deterministically? **YES**
6. Is a Gemini-only candidate corroborated before becoming statutory evidence? **YES**
7. Can Gemini bypass field validators? **NO**
8. Does nutrition 100 g remain rejected as Net Quantity? **YES**
9. Does unit sale price remain rejected as MRP? **YES**
10. Is COO still explicit-evidence-only? **YES**
11. Are business roles separate? **YES**
12. Does Gemini failure preserve OCR-only operation? **YES**
13. Is GEMINI_API_KEY backend-only? **YES**
14. Are Gemini responses structured/schema validated? **YES**
15. Is Gemini explanation generated only after deterministic verdict? **YES**
16. Can explanation change deterministic verdict? **NO**
17. Is a deterministic explanation fallback available? **YES**
18. Are original evidence coordinates preserved? **YES**
19. Do existing historical inspections still work? **YES**
20. Did all test/build/security gates pass? **YES**

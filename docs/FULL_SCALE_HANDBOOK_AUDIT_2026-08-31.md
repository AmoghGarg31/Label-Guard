# LabelGuard Full-Scale Handbook Audit — 2026-08-31

> Historical audit snapshot. Its extraction description is superseded by the Gemini-only implementation report; its statements about deterministic verdict authority and prototype scope remain applicable.

## Final assessment

LabelGuard is ready for its intended trusted local/SIH demonstration workflow. The handbook sample outcomes, deterministic rule path, correction/review workflow, reports, optional Gemini verification, and frontend routes were exercised successfully.

The project is **not** declared frozen or production-ready for unrestricted public or regulatory use. Authentication/RBAC and the other production controls listed below remain outside the implemented prototype scope.

## Defects found and fixed

1. **Visible malformed declarations were being dropped.** `MRP: ask retailer` was lost by extraction, so the malformed-MRP handbook fixture incorrectly became `manual_review_required`. The extractor now retains only high-confidence, same-line, anchored malformed MRP/net-quantity evidence. Multi-pass OCR provenance must agree when provenance exists, and nutrition, unit-price, date, phone, licence, multipack, and noisy bare-number false positives remain rejected.
2. **Backend Gemini configuration was not loaded during normal startup.** `backend/.env` is now loaded automatically before service construction. Process/Render environment variables retain priority. Tests explicitly disable inherited live Gemini configuration and continue to use mocks.
3. **The live Gemini structured schema was incompatible with the configured provider endpoint.** The provider rejected the Pydantic/OpenAPI conversion with an unsupported `additional_properties` field and rejected the full nested JSON schema. The integration now sends the provider-compatible `response_json_schema` subset, flattens references/nullable branches, and still applies the original strict Pydantic schema locally. The cache/prompt schema version is now `labelguard-gemini-vision-1.1`.
4. **The 15-second Gemini timeout was too short.** A real two-image structured vision request required about 32 seconds. Local configuration, defaults, the example environment, README, and `render.yaml` now use a 45-second bounded timeout.
5. **The demo runbook named files that did not exist.** It now uses the five real fixture names in `samples/`.
6. **The feature matrix and supporting docs were stale.** Targeted OCR, optional Gemini explanation, cloud deployment status, sample names, and current test wording were corrected.
7. **Local setup omitted an explicit backend environment step.** The README now documents backend-only Gemini configuration and automatic `.env` loading. `python-dotenv==1.2.3` is pinned.

## Extraction architecture re-audit

The final evidence path is:

1. Validate upload type, decoded image, dimensions, pixel limits, and quality.
2. Run deterministic OCR over orientation and enhancement candidates.
3. Rank spatially anchored declaration candidates and retain original-image bounding boxes.
4. Optionally ask Gemini to read visible declarations only; Gemini cannot produce a rule finding or verdict.
5. Apply semantic validators to model candidates and require targeted local OCR before Gemini-only evidence can become statutory evidence.
6. Resolve agreement/conflict explicitly. Unresolved evidence goes to review; it is not guessed.
7. Run the versioned deterministic LMPC rules and derive the overall status solely from those findings.
8. Generate an optional explanation after the verdict. Inconsistent or unavailable AI prose is replaced with deterministic fallback text.
9. Persist the original outcome, evidence, provenance, corrections, reviews, and audit events.

Failure of Gemini, its key, network, model, schema, quota, explanation, or cache does not fail the inspection. The OCR/rule result remains available and the provider error is redacted.

## Handbook fixture verification

All uploads used an isolated audit database and Domestic package scope where applicable.

| Fixture | Expected | Actual | Key evidence | Result |
|---|---|---|---|---|
| `01-readable-domestic.png` | compliant | compliant | MRP ₹95; net 250 g; six PASS | PASS |
| `02-missing-mrp.png` | manual review | manual review | MRP absent; five PASS, one UNCERTAIN | PASS |
| `03-rotated-90.png` | compliant after orientation | compliant, 90° | six PASS | PASS |
| `04-low-quality-blur.png` | quality/manual review | manual review | quality review; six UNCERTAIN | PASS |
| `05-malformed-mrp.png` | potential non-compliance | potential non-compliance | visible `ask retailer`; MRP FAIL with localized evidence | PASS |

These are synthetic handbook fixtures. This audit does not misidentify them as the previously discussed real UNIBIC package image.

## Real Gemini verification

A controlled live run used `samples/01-readable-domestic.png` with the configured backend-only key and `gemini-3.7-flash`.

- Both provider calls returned HTTP 200: visual extraction and downstream explanation.
- Visual status: `success`; readability: `clear`; candidates: 8.
- MRP and net quantity reconciliation states: `AGREED`.
- Accepted deterministic values remained MRP `₹95.00` and net quantity `250 g`.
- Overall status remained `compliant`; Gemini did not set or change it.
- Timings: deterministic OCR 3.01 s, Gemini visual 32.15 s, explanation 16.88 s, total 52.47 s.
- The run used an isolated temporary data directory and did not alter the user's normal inspection database.

## UI, workflow, and API verification

- `npm run dev` started successfully and compiled every exercised route without a frontend runtime or browser-console error.
- Routes exercised: dashboard, new inspection, history, inspection detail, review, rules, analytics, and system status.
- Desktop viewport: 1440×900. Mobile viewport: 390×844. No horizontal overflow was found on the tested pages.
- Live correction changed a missing MRP to `₹95.00`, re-ran rules, retained the original outcome, recorded the actor/reason, and displayed 100% human-correction provenance.
- Live review saved `VERIFIED`, reviewer, and note without mutating the automated verdict.
- Original image, evidence image, PDF, JSON export, CSV export, system status, rules, history, review queue, and analytics endpoints all returned the expected content/status.
- Security headers included `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY`.
- Audit history contained creation, quality, OCR, Gemini/reconciliation, rules, explanation, correction/rule-rerun, and review events.

## Final automated gates

| Gate | Final result |
|---|---|
| Backend pytest | **186 passed**, one third-party Starlette/httpx deprecation warning |
| Gemini focused tests | **28 passed** |
| Frontend lint | PASS, zero warnings |
| Frontend typecheck | PASS |
| Next.js production build | PASS, 10 generated routes/pages |
| `npm audit` | 0 known vulnerabilities |
| Python dependency audit | no known vulnerabilities |
| Secret scan outside ignored env files | no Google-key-shaped material found |
| Frontend Gemini-key scan | no Gemini key identifiers or key-shaped values found |

The first typecheck was accidentally launched concurrently with `next build`; both commands write `.next/types`, so it saw transient missing generated files. The authoritative sequential rerun after the successful build passed. This is a test-ordering race, not an application/type error.

## Remaining user-controlled or out-of-scope work

### Required security action

Rotate the Gemini API key because an earlier project state had placed a key in a frontend environment file. Put only the replacement value in `backend/.env` as `GEMINI_API_KEY`; never use a `NEXT_PUBLIC_*` Gemini variable. Restart the backend after rotation.

### Required only for Hindi labels

The installed Tesseract currently has `eng` and `osd`, not `hin`. Install `hin.traineddata` into `C:\Program Files\Tesseract-OCR\tessdata`, then restart the backend. `LABELGUARD_OCR_LANGUAGES=eng+hin` is already configured and safely skips unavailable languages.

### Required before a public operational deployment

Implement authentication/RBAC, tenant/data authorization, Postgres and object storage, distributed jobs/rate limiting, encryption and retention controls, centralized redacted observability, backup/restore drills, and qualified legal review of the active rule corpus. Until then, use the app only as a trusted prototype/screening aid.

### User-owned external actions

GitHub repository creation, Git credentials, Render account/disk, Vercel account/domain, production CORS origin, and production secrets require the user's accounts. The exact workflow is in `docs/DEPLOYMENT.md` and is summarized in the handoff message.

## Conclusion

The handbook-aligned local prototype implementation and audit are complete. No known code/test defect remains in the exercised scope. What remains is limited to the explicit security, language-pack, account/deployment, and production-hardening actions above; therefore this report does not call the project frozen.

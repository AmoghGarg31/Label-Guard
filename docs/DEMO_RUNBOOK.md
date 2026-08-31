# Demo Runbook

This runbook uses live Gemini extraction, the live API, and clearly watermarked synthetic fixtures. Never describe a fixture result as a pre-recorded live result, and never substitute hardcoded/mock data when a service is unavailable.

## Preflight

1. Confirm Node.js 20.9+, Python 3.12, and a valid backend-only Gemini API key are available.
2. From `backend`, create `.venv`, install `requirements.txt`, copy `.env.example` to `.env`, and configure `GEMINI_API_KEY`.
3. From `frontend`, run `npm install` once.
4. From the project root, run `npm run dev`; open `http://localhost:3000`.
5. Open **System**. Confirm database `ok`, Gemini-only extraction ready, the configured route/rate limit, rule engine `LMPC-ENGINE-2.0`, and seven active rules.
6. Keep `samples/` open in Explorer. These images are synthetic and visibly labelled `SYNTHETIC DEMO — NOT A REAL PRODUCT`.

## Primary judge demo (8–10 minutes)

1. On the dashboard, explain that every count is read from SQLite—there is no mock fallback.
2. Inspect `samples/01-readable-domestic.png` with package scope **Domestic**. Show the backend result, image-quality panel, all applicable declarations, rule sources, and evidence overlay.
3. Inspect `samples/02-missing-mrp.png`. Explain why missing evidence becomes **manual review / UNCERTAIN**, not an accusation of non-compliance.
4. Inspect `samples/05-malformed-mrp.png`. Show the visible malformed declaration and deterministic format-rule **FAIL**, presented cautiously as a potential issue.
5. Inspect `samples/03-rotated-90.png`. Show Gemini's localized evidence on the original image.
6. Inspect `samples/04-low-quality-blur.png`. Show the quality gate and manual-review outcome instead of an overconfident verdict.
7. Open one detail record. Zoom/rotate the evidence image, select a field, and explain confidence, provenance, citation, applicability, and engine version.
8. Correct one extracted field only after comparing it with the image. Submit the correction; show the same deterministic rules rerun and the original value/status retained in the audit trail.
9. Add a separate human review disposition and note. Show that this does not overwrite the automated outcome.
10. Open History, Review Queue, Analytics, Rule Explorer, and the PDF report. Finish on the System page and repeat the decision-support disclaimer.

## Backup demo (3–4 minutes)

If time is short, demonstrate only readable domestic, missing MRP, rotated 90°, one evidence detail, and the Rule Explorer. Existing records may be opened from History, but state clearly that they are persisted prior live runs. Do not present them as an upload performed moments ago.

## Fallbacks

### Gemini is unavailable or produces poor text

- Keep the live result visible and explain the actual quality/confidence evidence.
- Use the correction workflow to demonstrate human verification and deterministic re-evaluation.
- Open a previously persisted record only after labeling it as a prior live inspection.
- Do not edit the database or claim extracted values that were not produced.

### Camera is unavailable

Use **Choose image** with a fixture from `samples/`. Camera capture depends on browser/device permissions; file upload exercises the same validation, Gemini extraction, deterministic validation/rules, persistence, and evidence pipeline.

### Internet is unavailable

The active inspection path requires network access to Gemini. Existing saved inspections, local history, and PDFs remain available, but new image extraction cannot run offline.

### Server restart is required

1. Leave the browser open; stop only the failed service.
2. Restart FastAPI on port 8000 or Next.js on port 3000 with the preflight commands.
3. Refresh **System** and confirm readiness before resuming.
4. Existing records remain in SQLite. Never delete/reset the database as a recovery step.

## Closing language

Use: “LabelGuard provides automated compliance screening based on configured deterministic rules. Final statutory determination may require verification by an authorized Legal Metrology officer.”

Avoid claims of government approval, legal certification, perfect accuracy, zero false positives, or AI-determined compliance.

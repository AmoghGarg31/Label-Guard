LABELGUARD — GEMINI VISION DOUBLE-VERIFICATION + AI EXPLANATION PASS

PROJECT:
C:\Users\amogh\OneDrive\Desktop\LabelGuard

MODEL FOR CODEX:
GPT-5.6 Sol
Highest available reasoning.

GOAL:
Add Gemini multimodal vision as a SECOND independent package-declaration reader
and verifier while preserving the existing deterministic Legal Metrology rule
engine as the ONLY authority that produces PASS / FAIL / UNCERTAIN and
overall_status.

This is NOT a replacement for the existing OCR pipeline.

==================================================
ABSOLUTE ARCHITECTURE RULE
==================================================

The required system must become:

IMAGE
→ deterministic image-quality analysis
→ deterministic OpenCV enhancement
→ OCR extraction
           +
→ Gemini Vision extraction
           ↓
→ deterministic evidence reconciliation
→ existing deterministic rules.py
→ PASS / FAIL / UNCERTAIN
→ overall_status
→ optional Gemini plain-language explanation
→ 3–4 line recommendation

Gemini must NEVER directly determine:

PASS
FAIL
UNCERTAIN
compliant
potential_non_compliance
manual_review_required

Gemini must NEVER override rules.py.

No frontend code may determine compliance.

The existing deterministic rules engine must remain intact.

==================================================
WHY WE ARE ADDING GEMINI
==================================================

Current OCR works very well on flat labels but struggles with:

curved packets
perspective distortion
crumpled packaging
small printed text
glare
low contrast
complex layouts
thermal/date printing

Gemini Vision should act as an independent visual reader.

The design objective is:

OCR says X
Gemini says X
→ strong corroboration

OCR says X
Gemini says Y
→ disagreement / targeted retry / manual review

OCR cannot read field
Gemini proposes value
→ use Gemini region as a hint
→ run targeted OCR on that region
→ accept only if deterministically validated/corroborated
→ otherwise UNCERTAIN

Gemini must not become an oracle.

==================================================
PHASE 1 — READ CURRENT ARCHITECTURE
==================================================

Before modifying code, read:

backend/app.py
backend/ocr_engine.py
backend/extractor.py
backend/models.py
backend/image_quality.py
backend/evidence.py
backend/rules.py
backend/database.py
backend/report.py
backend/tests/*

and relevant frontend:

frontend/lib/api-client*
frontend/lib/types*
inspection wizard
inspection detail page
evidence viewer
compliance result
system status

Run baseline:

python -m pytest tests

npm run typecheck
npm run lint
npm run build

Do not discard existing work.

==================================================
PHASE 2 — GEMINI SDK
==================================================

Use Google's current official Python GenAI SDK:

google-genai

Do NOT use deprecated:

google-generativeai

Add it carefully to backend requirements.

Configuration must be server-side:

GEMINI_ENABLED=true|false
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.7-flash
GEMINI_TIMEOUT_SECONDS=<reasonable value>

Model name must be configurable.

Never put GEMINI_API_KEY in:

frontend
NEXT_PUBLIC variables
API responses
logs
Git
README examples containing real secrets.

Update .env examples using placeholders only.

==================================================
PHASE 3 — KEEP IMAGE ENHANCEMENT DETERMINISTIC
==================================================

Do NOT ask Gemini to hallucinate/reconstruct missing pixels.

Before OCR/Gemini, use existing deterministic image processing.

Preserve or improve carefully:

orientation
deskew
perspective correction
CLAHE
contrast
sharpening
denoise
upscaling
adaptive thresholding
mild local dewarping where already available

Generate only a small number of useful variants.

For example:

original
contrast-enhanced
sharpened/upscaled

Do not create excessive processing latency.

Gemini should normally receive:

original image

and, when quality analysis indicates benefit:

one best deterministic enhanced version.

==================================================
PHASE 4 — GEMINI IMAGE EXTRACTION SERVICE
==================================================

Create a clean isolated backend service, for example:

backend/gemini_vision.py

or equivalent.

It must NOT import or execute rules.py.

Its responsibility is ONLY:

visual reading
structured declaration extraction
region suggestions
readability assessment.

Use Gemini multimodal image input.

Prefer inline image bytes for normal LabelGuard package images.

Do not upload through Files API unless required by request size.

==================================================
PHASE 5 — STRICT STRUCTURED OUTPUT
==================================================

Use Gemini structured JSON output with a strict schema.

Do NOT parse free-form prose.

Create a Pydantic schema conceptually like:

GeminiFieldCandidate:
    field
    raw_text
    normalized_value
    readable
    model_score
    bbox_2d
    evidence_text
    notes

GeminiExtractionResponse:
    image_readability
    distortion_types
    fields
    warnings

Supported fields should include every currently active declaration:

common_name

manufacturer_name
manufacturer_address

packer_name
packer_address

marketer_name
marketer_address

importer_name
importer_address

net_quantity

mrp

manufacture_date
packing_date

best_before
use_by
expiry_date

consumer_phone
consumer_email
consumer_website
consumer_address

country_of_origin

and other currently supported rule fields.

Maintain backward compatibility with current API.

==================================================
PHASE 6 — GEMINI EXTRACTION PROMPT
==================================================

Gemini must receive strict instructions similar to:

"You are reading statutory declarations from a packaged commodity image.

Read only text visibly supported by the image.

Do not infer missing declarations.

Do not infer Country of Origin from company address.

Do not treat nutrition quantities as Net Quantity.

Do not treat unit sale price as MRP.

Do not treat Best Before/Use By as Manufacture Date.

Keep Manufacturer, Packer, Marketer and Importer separate.

If characters are unreadable, return null rather than guessing.

Do not determine legal compliance.

Do not output PASS/FAIL.

Return only structured extraction according to the supplied schema."

==================================================
PHASE 7 — GEMINI BOUNDING BOXES
==================================================

Gemini may provide bbox_2d using normalized image coordinates.

Treat Gemini boxes as:

REGION HINTS

not automatically authoritative evidence.

Convert carefully to original-image pixels.

Existing public evidence remains:

[xmin,ymin,xmax,ymax]

absolute original image pixels.

When Gemini identifies a possible region:

use that region for targeted OCR.

Whenever possible, final statutory evidence bbox should come from OCR token
geometry after corroboration.

Never display a fake precise evidence rectangle merely because Gemini guessed
a region.

==================================================
PHASE 8 — INDEPENDENT OCR + GEMINI READERS
==================================================

Run the two extraction systems independently.

A:

Tesseract/OCR
→ OCR field candidates

B:

Gemini Vision
→ Gemini field candidates

Gemini must NOT be shown OCR extracted values during the initial visual pass.

This prevents confirmation bias.

The first Gemini visual extraction should be independent.

==================================================
PHASE 9 — DETERMINISTIC RECONCILIATION ENGINE
==================================================

Create a new deterministic module such as:

backend/evidence_reconciler.py

This code — not Gemini — decides which extracted evidence is trusted enough
to enter the deterministic rule engine.

Use existing normalization/validators.

For each field compare:

OCR candidate
Gemini candidate

Possible states:

AGREED
OCR_ONLY
GEMINI_ONLY
CONFLICT
UNREADABLE
MISSING

==================================================
AGREEMENT
==================================================

Example:

OCR:
₹170.00

Gemini:
₹170

normalized:

170.00 == 170.00

→ AGREED

The accepted field can use the OCR evidence box and record:

verification_source = OCR_GEMINI_AGREED

Do not automatically set confidence to 100%.

==================================================
OCR ONLY
==================================================

OCR has a strong valid field.
Gemini does not detect it.

Preserve OCR candidate when existing deterministic thresholds consider it
reliable.

Record:

verification_source = OCR_ONLY

Do not discard good OCR simply because Gemini missed it.

==================================================
GEMINI ONLY
==================================================

Gemini reads:

₹170.00

but OCR has no valid MRP.

Do NOT immediately trust Gemini.

Instead:

1. use Gemini region hint
2. crop that area from original/enhanced image
3. run targeted OCR
4. validate datatype/context
5. compare result

If targeted OCR corroborates:

accept.

Otherwise:

UNCERTAIN / manual review.

==================================================
CONFLICT
==================================================

Example:

OCR:
₹120

Gemini:
₹170

Do NOT choose one blindly.

Run targeted OCR on the best candidate region.

Compare multiple OCR variants.

If conflict remains:

field = uncertain
confidence lowered
review_required = true

Preserve both candidate readings for inspector review.

==================================================
PHASE 10 — FIELD VALIDATORS STILL APPLY
==================================================

Gemini candidates must pass the SAME generic field validators.

Examples:

Nutrition:
100 g
must not become Net Quantity.

Unit Sale Price:
₹0.63 per g
must not become MRP.

Indian company/address
must not become Country of Origin.

Marketed By
must not silently become Manufacturer.

Manufacturer address prose
must not become Date.

Gemini cannot bypass deterministic validation.

==================================================
PHASE 11 — PROVENANCE
==================================================

Extend internal metadata additively.

For each extracted field retain provenance such as:

ocr_value
ocr_confidence

gemini_value
gemini_readability/model_score

targeted_ocr_value

verification_state:
AGREED
OCR_ONLY
GEMINI_ONLY_UNVERIFIED
CONFLICT
MANUALLY_CORRECTED

accepted_source

Do not break the existing public:

text
confidence

fields.

Expose additional metadata only where useful.

==================================================
PHASE 12 — GEMINI FAILURE MUST NOT BREAK INSPECTION
==================================================

Gemini is an enhancement.

It must never become a single point of failure.

If:

API key missing
Gemini disabled
network unavailable
quota exceeded
API timeout
5xx response
malformed structured output
model unavailable

then:

continue using existing OCR + deterministic rule engine.

Display:

AI visual verification unavailable

without failing inspection.

Do NOT silently replace deterministic functionality.

==================================================
PHASE 13 — TIMEOUT / RETRY
==================================================

Use a reasonable server-side timeout.

At most a small controlled retry for transient failures.

Do not leave an inspection hanging indefinitely.

Do not retry quota/auth errors repeatedly.

==================================================
PHASE 14 — CACHE GEMINI RESULT
==================================================

Do NOT call Gemini repeatedly because the inspector clicked Back/Next.

Cache Gemini extraction per inspection/image hash.

Store:

model
prompt/schema version
timestamp
structured output
status

Do not unnecessarily store duplicate image bytes.

==================================================
PHASE 15 — COST CONTROL
==================================================

One inspection should normally require:

1 Gemini Vision extraction call

plus optionally:

1 downstream explanation call

Do NOT call Gemini independently for every field.

Do NOT call Gemini repeatedly for every preprocessing variant.

Use targeted local OCR locally instead.

==================================================
PHASE 16 — PRIVACY / UI DISCLOSURE
==================================================

When GEMINI_ENABLED=true, the package image is being sent to an external
Gemini API.

Add a concise product disclosure such as:

"AI-assisted visual verification enabled. Package imagery is processed using
the configured Gemini service."

Do not imply everything remains purely local when Gemini is enabled.

Do not expose technical clutter during normal use.

==================================================
PHASE 17 — INSPECTION PIPELINE UX
==================================================

Update processing stages carefully.

Suggested UI:

1. Image Quality
2. Local OCR
3. AI Visual Verification
4. Evidence Reconciliation
5. Deterministic Rule Evaluation
6. Report Preparation

Do not show fake percentages.

Show state chips such as:

OCR Read
AI Verified
OCR + AI Agreed
Verification Conflict
Manual Review Required

==================================================
PHASE 18 — DECLARATION UI
==================================================

For each declaration optionally show small provenance:

OCR
AI verified
OCR + AI
Conflict
Manual correction

Example:

MRP
₹170.00
94%
OCR + AI verified

Do NOT make Gemini branding visually dominate the compliance result.

==================================================
PHASE 19 — COMPLIANCE RULES REMAIN UNCHANGED
==================================================

After deterministic reconciliation, build the same accepted extracted_fields
structure currently expected by rules.py.

Then call:

evaluate_rules(...)

and:

overall_status(...)

exactly through the existing backend architecture.

Gemini must have no ability to set finding.status or overall_status.

==================================================
PHASE 20 — SECOND GEMINI CALL: HUMAN EXPLANATION
==================================================

After rules.py has COMPLETELY finished:

Gemini may generate a human-readable explanation.

This is a separate downstream task.

Gemini receives ONLY authoritative backend facts such as:

overall_status
deterministic findings
rule IDs
rule descriptions
legal citations already configured by backend
accepted extracted declarations
confidence
review requirements

The explanation prompt must explicitly say:

"You are explaining an already-computed deterministic screening result.

Do not change the verdict.
Do not invent violations.
Do not introduce legal requirements that are not present in the supplied
findings.
Do not claim government certification.
Explain the supplied result in simple language."

==================================================
PHASE 21 — HUMAN-LANGUAGE REPORT
==================================================

Generate a concise section:

AI-ASSISTED PLAIN-LANGUAGE EXPLANATION

Example style:

"The package could be read clearly for four of the six declarations checked.
Net Quantity and Consumer Care were successfully verified. The MRP could not
be confirmed because OCR and visual verification disagreed, so the inspection
has been sent for manual review. No final violation should be inferred from
that uncertain field."

The explanation must derive from deterministic findings.

==================================================
PHASE 22 — RECOMMENDATION
==================================================

Generate only 3–4 lines.

Example:

RECOMMENDED NEXT STEP

"Review the highlighted MRP region and capture a closer image if necessary.
The remaining verified declarations do not require further action. After the
MRP is confirmed or corrected, LabelGuard will automatically rerun the
deterministic rule engine."

Recommendations are operational guidance.

Do NOT generate:

legal penalties
prosecution recommendations
official enforcement orders
unsupported legal conclusions.

==================================================
PHASE 23 — EXPLANATION FAILURE
==================================================

If Gemini explanation call fails:

do not fail the result screen.

Generate a deterministic template-based fallback explanation from findings.

There must ALWAYS be a usable report.

==================================================
PHASE 24 — PDF REPORT
==================================================

Add carefully:

Automated Deterministic Screening Result

Evidence / Findings

AI Visual Verification status

Plain-Language Explanation

Recommended Next Step

Inspector Review if present

Audit Trail

Include disclaimer:

"The compliance screening result is generated by LabelGuard's configured
deterministic rule engine. AI-assisted visual verification and explanations
are advisory and do not independently determine legal compliance."

==================================================
PHASE 25 — AUDIT TRAIL
==================================================

Add events such as:

IMAGE_QUALITY_COMPLETED
OCR_COMPLETED
GEMINI_VERIFICATION_COMPLETED
GEMINI_VERIFICATION_UNAVAILABLE
EVIDENCE_RECONCILED
RULES_EVALUATED
AI_EXPLANATION_GENERATED

Do not log API keys or full request payloads.

==================================================
PHASE 26 — SYSTEM STATUS
==================================================

Update /system/status to report independently:

Tesseract available
PaddleOCR available/unavailable
Gemini enabled
Gemini configured
Gemini last error if safe
rule engine version

Do not expose GEMINI_API_KEY.

==================================================
PHASE 27 — PADDLEOCR
==================================================

Do NOT install PaddleOCR as part of this pass.

Current Tesseract pipeline has already been extensively tested.

Keep the Paddle fallback architecture unchanged unless compatibility requires
a tiny adjustment.

Gemini is being introduced independently.

==================================================
PHASE 28 — ENVIRONMENT
==================================================

Update backend environment example:

GEMINI_ENABLED=false
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.7-flash

Default GEMINI_ENABLED to false if no key exists.

If enabled without API key:

show clear configuration status,
but do not crash.

==================================================
PHASE 29 — SECURITY
==================================================

API key must stay backend-only.

Verify:

no NEXT_PUBLIC Gemini key
no API key in logs
no API key in database
no API key in Git
no key returned by /system/status
no image bytes dumped into logs

Respect existing upload limits and rate limits.

==================================================
PHASE 30 — MOCK GEMINI CLIENT FOR TESTS
==================================================

Unit tests must NOT depend on live Gemini service.

Create injectable Gemini client/service.

Tests should use deterministic mocks.

Test:

Gemini agreement
OCR-only
Gemini-only
Gemini-only + targeted OCR verification
conflict
timeout
quota error
auth error
malformed response
missing key
disabled Gemini
hallucinated invalid field
unit-price false positive
nutrition false positive
bbox normalization
explanation success
explanation failure

==================================================
PHASE 31 — CRITICAL INTEGRITY TESTS
==================================================

Prove:

Gemini says COMPLIANT
→ ignored as legal decision.

Gemini says FAIL
→ ignored as legal decision.

Gemini explanation contradicts backend status
→ backend status remains unchanged.

Gemini extracts "100 g" from nutrition
→ validator rejects it.

Gemini extracts "₹0.63 per g" as MRP
→ validator rejects it.

Gemini hallucinates Country of Origin
without explicit evidence
→ reject/uncertain.

==================================================
PHASE 32 — DOUBLE-VERIFICATION TEST
==================================================

Synthetic test:

Visible:
MRP ₹170
Net Weight 270 g
MFG 20/01/2027

OCR and Gemini agree.

Verify accepted values and deterministic rules.

Then test conflicts:

OCR MRP ₹120
Gemini MRP ₹170

Expected:

targeted OCR
then either:
verified value

or:
UNCERTAIN

Never arbitrary selection.

==================================================
PHASE 33 — DISTORTED IMAGE REGRESSION
==================================================

Use available test-suite images:

flat
perspective
rotation
mild curvature
strong curvature
crumpled
glare
low contrast
blur
low resolution
shadow
occlusion

Measure:

OCR-only result
Gemini candidate
reconciled result

Do not require severe images to magically become readable.

Success is:

correct evidence when recoverable

OR

safe UNCERTAIN.

==================================================
PHASE 34 — EXISTING REAL PACKAGE REGRESSION
==================================================

Rerun locally available:

Haldiram
Snackible
UNIBIC
Green Basket
Khari
other real uploads

Do not hardcode any of them.

Report whether Gemini:

corroborated OCR
recovered a field later verified by targeted OCR
identified a conflict
or correctly left field uncertain.

==================================================
PHASE 35 — PERFORMANCE
==================================================

Measure:

OCR-only processing time
Gemini request time
total inspection time

Do not make the prototype unusably slow.

Gemini failures must fail fast enough for a demo.

==================================================
PHASE 36 — FRONTEND
==================================================

Do not broadly redesign the UI.

Only integrate the new architecture cleanly.

Add where appropriate:

AI Visual Verification status
provenance badges
plain-language explanation
3–4 line recommendation

Keep the existing polished design system.

==================================================
PHASE 37 — API CONTRACT
==================================================

Do not break existing fields.

Existing:

id
overall_status
extracted_fields
findings

must remain compatible.

Add optional metadata such as:

verification
ai_summary
recommendation

without breaking existing clients.

==================================================
PHASE 38 — NO GEMINI RESULT IN VERDICT PATH
==================================================

Perform repository-wide search after implementation.

There must be NO path similar to:

overall_status = gemini_response
finding.status = gemini_response
if gemini says compliant: ...
if gemini says fail: ...

Gemini may provide evidence candidates only.

Rules remain deterministic.

==================================================
PHASE 39 — FINAL GATES
==================================================

Run:

python -m pytest tests

npm run typecheck
npm run lint
npm run build

npm audit

Verify API smoke tests.

Do not run npm audit fix --force.

==================================================
PHASE 40 — OPTIONAL LIVE GEMINI TEST
==================================================

If GEMINI_API_KEY is available in the environment:

perform one controlled live integration test.

Do not print the key.

Do not require live Gemini for the normal automated test suite.

If no API key exists:

report LIVE GEMINI TEST NOT RUN — API KEY NOT CONFIGURED.

Do not fabricate success.

==================================================
FINAL REPORT
==================================================

Return:

LABELGUARD GEMINI DOUBLE-VERIFICATION IMPLEMENTATION REPORT

1. Architecture before
2. Architecture after
3. Files changed
4. Gemini SDK/model/configuration
5. Image preprocessing
6. Gemini structured schema
7. Independent OCR flow
8. Independent Gemini flow
9. Evidence reconciler
10. Agreement behavior
11. OCR-only behavior
12. Gemini-only behavior
13. Conflict behavior
14. Targeted OCR verification
15. Field validator integrity
16. Evidence/bbox integrity
17. Rule-engine isolation proof
18. Plain-language explanation
19. Recommendation generation
20. Deterministic explanation fallback
21. UI changes
22. PDF changes
23. Audit trail
24. Security/API-key audit
25. Failure/fallback behavior
26. Distorted-image benchmark
27. Real-package regression
28. Backend tests
29. Frontend gates
30. npm audit
31. Live Gemini test status
32. Performance impact
33. Remaining limitations

FINAL VERDICT:

GEMINI DOUBLE-VERIFICATION READY FOR SIH

or

BLOCKERS REMAIN

==================================================
FINAL REQUIRED QUESTIONS
==================================================

Answer YES/NO:

1. Does rules.py remain the only automated compliance authority? YES required
2. Can Gemini directly set overall_status? NO required
3. Can Gemini directly set PASS/FAIL/UNCERTAIN? NO required
4. Is Gemini extraction independent from initial OCR extraction? YES required
5. Are OCR/Gemini disagreements handled deterministically? YES required
6. Is a Gemini-only candidate corroborated before becoming statutory evidence? YES required
7. Can Gemini bypass field validators? NO required
8. Does nutrition 100 g remain rejected as Net Quantity? YES required
9. Does unit sale price remain rejected as MRP? YES required
10. Is COO still explicit-evidence-only? YES required
11. Are business roles separate? YES required
12. Does Gemini failure preserve OCR-only operation? YES required
13. Is GEMINI_API_KEY backend-only? YES required
14. Are Gemini responses structured/schema validated? YES required
15. Is Gemini explanation generated only after deterministic verdict? YES required
16. Can explanation change deterministic verdict? NO required
17. Is a deterministic explanation fallback available? YES required
18. Are original evidence coordinates preserved? YES required
19. Do existing historical inspections still work? YES required
20. Did all test/build/security gates pass? YES required

Do not declare completion if any critical answer differs.

START NOW.
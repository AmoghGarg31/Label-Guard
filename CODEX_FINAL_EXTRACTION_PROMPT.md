# LABELGUARD — FINAL LAYOUT-INDEPENDENT EXTRACTION PASS

**Project:** `C:\Users\amogh\OneDrive\Desktop\LabelGuard`  
**Model:** GPT-5.6 Sol  
**Reasoning:** Highest available reasoning level.

## Goal

Fix the remaining extraction weakness so LabelGuard detects statutory package declarations using **meaning + valid datatype + OCR geometry**, not fixed layout, line order, expected position, or brand-specific rules.

Do **not** redesign UI, deployment, CI, analytics, or unrelated features. Focus on OCR/extraction/generalization and regression safety.

## Non-negotiable architecture

Compliance must remain:

`Image → OCR/CV → structured extraction → deterministic backend rules.py → PASS/FAIL/UNCERTAIN → overall_status`

No LLM and no frontend code may determine compliance.

Human corrections must continue to:
store correction → rerun deterministic backend rules → preserve audit trail.

## Critical requirement — no fixed layout

LabelGuard must not assume:

- MRP is bottom-right
- Date is near MRP
- Net Quantity is bottom
- Manufacturer is top
- Consumer Care is right
- Country of Origin is near barcode

Declarations may appear anywhere in the visible image.

The same field must still be detected if moved:
top, bottom, left, right, center, another column, another panel, above/below/left/right of anchor.

Production code must not use fixed field-specific coordinates.

## Read and audit

Read and trace completely:

- `backend/ocr_engine.py`
- `backend/extractor.py`
- `backend/image_quality.py`
- `backend/evidence.py`
- `backend/rules.py`
- `backend/models.py`
- `backend/app.py`
- `backend/database.py`
- `backend/tests/*`

Trace how every field gets `text`, `confidence`, and `bounding_box`.

Find why incorrect nearby text can be associated with the wrong field.

Known failure:

`Manufacture / pre-pack date = "BY: FOR MANUFACTURING UNIT ADDRESS, SEE FIRST..."` with high confidence.

This must become impossible.

## Target extraction architecture

Use:

`FULL IMAGE OCR → word/token coordinates → dynamic rows/blocks/columns → global anchor search → global datatype candidate search → field-specific validation → spatial/semantic scoring → reject invalid candidates → honest confidence → structured evidence`

Do not flatten multi-column labels into one dangerous text sequence.

OCR token representation should preserve:

- text
- OCR confidence
- `[xmin,ymin,xmax,ymax]`
- OCR pass/orientation provenance when useful

All final evidence coordinates must map back to the **original uploaded image**.

## Search all supported fields globally

Search the entire visible image for all active declaration fields, including:

- Common / generic commodity name
- Manufacturer
- Manufacturer address
- Packer
- Marketer
- Importer
- Net Quantity
- MRP / Retail Sale Price
- Manufacture / Packing / Pre-pack date
- Consumer Care
- Country of Origin
- every other field used by active rules/UI/PDF

No field may depend on a predefined region.

## Anchor families

Support OCR-tolerant variants such as:

**MRP:** MRP, M.R.P., Maximum Retail Price, Retail Sale Price  
**NET:** Net Weight, Net Wt, NETWT, Net Quantity, Net Contents  
**DATE:** MFG DATE, MFD, MFG, Date of Manufacture, Manufactured On, Packed On, Packing Date, PKD, Pre-packed  
**BUSINESS:** Manufactured By, Packed By, Marketed By, Imported By  
**CONSUMER:** Consumer Care, Customer Care, Contact, Phone, Email, Website  
**COO:** Country of Origin, Made in, Product of  
**COMMON NAME:** Common Name, Generic Name, Name of Commodity, Product Name

Use bounded fuzzy matching for OCR errors, not overly permissive matching.

## Field-specific validators

### Date
Accept real date-like values such as:
`20/01/2027`, `20-01-2027`, `01/2027`, `JAN 2027`, `12 AUG 2026`.

Reject:
addresses, company names, instructions, license numbers, nutrition text, random prose.

`FOR MANUFACTURING UNIT ADDRESS...` must never be accepted as a date.

Differentiate where possible:
manufacture date, packing date, best-before, use-by, expiry.

### MRP
Accept:
`₹170`, `₹170.00`, `Rs 170`, `Rs.170/-`, `INR 170`.

Reject:
nutrition values, phone numbers, dates, license numbers, percentages.

Differentiate package MRP from unit-sale price such as `₹0.63 per g`.

### Net Quantity
Require numeric quantity + valid unit:
`270 g`, `1 kg`, `500 ml`, `2 L`, `4 units`.

Reject nutrition values such as `Protein 11.6 g` or `Sugar 32.4 g`.

### Consumer Care
Accept validated phone/email/web/contact address.

Reject:
license numbers, barcodes, batch IDs.

### Country of Origin
Require explicit origin evidence such as:
`Country of Origin: India`, `Made in India`, `Product of India`.

Do not infer from:
Indian address, +91 number, company name, FSSAI.

### Business Roles
Keep manufacturer, packer, marketer, importer semantically separate.

`Marketed by XYZ` must not silently become manufacturer.

### Common / Generic Name
Detect explicit commodity identity when visible.
Do not fabricate it from brand/manufacturer.

## Search around anchors in all directions

Support all of these:

`MRP ₹170`  
`₹170 MRP`

and:

```
MRP
₹170
```

and:

```
₹170
MRP
```

Likewise for Date, Net Quantity, Consumer Care, etc.

Search:
same row, right, left, above, below, same column, same dynamic block/panel.

Semantic validity must outrank simple proximity.

## Global datatype candidate discovery

Also scan the entire image independently for:

- prices
- quantities
- dates
- phones
- emails
- URLs
- countries
- company-like text

This helps when value OCR is good but anchor OCR is weak.

Anchorless classification must use stricter thresholds. If ambiguous → `UNCERTAIN`.

## Candidate scoring

Use deterministic scoring based on:

- anchor quality
- datatype validity
- OCR confidence
- spatial distance
- same row/block/column
- supporting context
- candidate ambiguity

with penalties for:

- cross-column jump
- wrong datatype
- nutrition context
- conflicting field anchor
- unit-sale-price context
- address context

Invalid datatype candidates should be **hard rejected**, not merely scored lower.

OCR confidence is not the same as field confidence.

A 95%-confidence OCR sentence that is not a date must have 0 confidence as DATE.

## Cross-field contamination prevention

Prevent:

- nutrition grams → Net Quantity
- nutrition numbers → MRP
- unit sale price → MRP
- address → Date
- license number → Consumer Phone
- Indian address → Country of Origin
- manufacturer → common name

Wrong confident extraction is worse than `UNCERTAIN`.

## Multi-column / panel support

Handle layouts such as:

- manufacturer left
- consumer care right
- nutrition center
- MRP/date separate sticker
- net quantity elsewhere

Use dynamic blocks/columns from OCR geometry. Do not use hardcoded field locations.

## Orientation

Preserve/verify automatic:
`0°`, `90°`, `180°`, `270°`.

The same package should produce equivalent extraction after rotation.

If useful, use targeted local OCR for vertically printed regions, without unreasonable brute-force latency.

## Evidence

Accepted fields must keep tight evidence:

`[xmin,ymin,xmax,ymax]`

in original uploaded-image coordinates.

Prefer anchor + matched value only.

Rejected candidates must not show fake evidence.

## No brand hardcoding

Search production code for:

- Haldiram
- Snackible
- UNIBIC
- Green Basket
- known sample values
- known filenames
- known image dimensions

Brand names may appear in tests/fixtures/docs only.

Production extraction must be generic.

## Mandatory tests

Add tests proving:

1. MFG DATE + valid date → accepted
2. date above anchor → accepted
3. date below anchor → accepted
4. manufacturing address prose → rejected as date
5. `Manufactured by XYZ` → not a date anchor
6. MRP ₹170 → accepted
7. ₹170 above/below/left/right of MRP anchor → accepted
8. ₹0.63 per g does not replace explicit MRP ₹170
9. Net Weight 270 g → accepted
10. Protein 11.6 g → not net quantity
11. Consumer Care phone → accepted
12. License number → not consumer phone
13. Country of Origin India → accepted
14. Indian address alone → no COO
15. Marketed by → marketer
16. Manufactured by → manufacturer

## Layout-invariance test

Create a generic synthetic package with identical declarations and render multiple layouts:

- single-column
- two-column
- MRP top-left
- MRP bottom-right
- date above anchor
- value below anchor
- separate MRP/date sticker
- nutrition table between declarations
- random declaration ordering
- random non-overlapping positions

All layouts must return equivalent normalized fields.

Also test several deterministic random seeds.

This is mandatory proof that extraction is not position-based.

## Rotation × layout test

For at least:
single-column, two-column, panel, random layout

test:
`0°`, `90°`, `180°`, `270°`.

Verify extracted values and evidence coordinates.

## False-positive stress test

Include distractors such as:

- Protein 11.6 g
- Sugar 32.4 g
- ₹0.63 per g
- license number
- barcode
- batch number
- manufacturing address
- Best Before 6 Months

alongside:

- MRP ₹170
- Net Weight 270 g
- MFG DATE 20/01/2027

Expected:
MRP = ₹170  
Net Quantity = 270 g  
Date = 20/01/2027

## Real regression tests

If locally available rerun:

- Haldiram
- Snackible
- UNIBIC
- Green Basket
- new package that caused date/address misassociation

These are regression tests only. Do not tune production code specifically to them.

## Safe uncertainty

If evidence is unclear:

return empty/low-confidence + `UNCERTAIN`.

Never guess just to populate the UI.

The system cannot detect declarations that are:
not visible, on another unseen side, occluded, too blurred, or destroyed by glare.

Those should become manual review, not invented violations.

## Preserve existing features

Do not break:

- human correction
- deterministic re-evaluation
- review status
- audit trail
- history
- old SQLite records
- PDF
- frontend API contract

Current public API must remain backwards-compatible.

## Final verification

Run:

Backend:
`python -m pytest tests`

Frontend:
`npm run typecheck`
`npm run lint`
`npm run build`

Security:
`npm audit`

Also smoke-test:

- GET /health
- GET /system/status
- GET /rules
- POST /inspect
- GET /history
- GET /inspection/{id}
- GET /report/{id}
- review
- correction
- audit

## Final report

Return:

# LABELGUARD FINAL LAYOUT-INDEPENDENT EXTRACTION REPORT

1. Root cause found
2. Architecture before/after
3. Files changed
4. Global full-image extraction method
5. Field validators
6. Candidate scoring
7. Multi-column handling
8. Above/below/left/right handling
9. Cross-field false-positive protection
10. Confidence calibration
11. Orientation handling
12. Evidence coordinate integrity
13. Layout randomization results
14. Rotation × layout results
15. False-positive stress test
16. Haldiram regression
17. Snackible regression
18. UNIBIC regression
19. Green Basket regression
20. New package regression
21. Backend tests
22. Frontend typecheck/lint/build
23. npm audit
24. Remaining limitations

Final verdict must be exactly one:

`LAYOUT-INDEPENDENT EXTRACTION PASS COMPLETE — READY TO FREEZE FOR SIH`

or

`LAYOUT-INDEPENDENT EXTRACTION PASS INCOMPLETE — BLOCKERS REMAIN`

## Final required checks

Answer YES/NO:

1. Does any production field rely on fixed image position? Required NO
2. Can MRP appear anywhere visible? Required YES
3. Can Net Quantity appear anywhere visible? Required YES
4. Can Date appear anywhere visible? Required YES
5. Can Consumer Care appear anywhere visible? Required YES
6. Can business information appear anywhere visible? Required YES
7. Are above/below/left/right values supported? Required YES
8. Are multi-column layouts supported? Required YES
9. Can arbitrary prose become Date? Required NO
10. Can nutrition values become MRP/Net Quantity? Required NO
11. Can unit sale price replace MRP? Required NO
12. Can Indian address alone create COO? Required NO
13. Is marketer distinct from manufacturer? Required YES
14. Is field confidence different from OCR confidence? Required YES
15. Are invalid candidates rejected? Required YES
16. Does uncertainty safely become manual review? Required YES
17. Are evidence coordinates original-image pixels? Required YES
18. Are 0/90/180/270 tested? Required YES
19. Are randomized layouts tested? Required YES
20. Is production extraction brand-independent? Required YES
21. Does correction still rerun deterministic rules? Required YES
22. Does any frontend code decide compliance? Required NO
23. Does any LLM decide compliance? Required NO
24. Did all backend/frontend gates pass? Required YES
25. Are there presentation-blocking extraction defects? Required NO

If a critical requirement fails, do not claim completion.

START NOW.

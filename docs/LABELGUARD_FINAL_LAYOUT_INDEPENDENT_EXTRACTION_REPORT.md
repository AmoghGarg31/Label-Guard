# LABELGUARD FINAL LAYOUT-INDEPENDENT EXTRACTION REPORT

> Historical OCR extraction report. It is retained for engineering traceability but no longer describes the active `/inspect` image-reader path. See `GEMINI_ONLY_IMPLEMENTATION_REPORT.md`.

## 1. Root cause found

OCR initially produced word geometry, but `ocr_engine.py` collapsed it into ordered lines and discarded token, block, pass, and column provenance. `extractor.py` then selected the first inline match or searched only to the right/below with fixed pixel thresholds. The date anchor accepted broad manufacturing words and a malformed-value fallback promoted arbitrary text after an anchor while copying OCR confidence directly. That combination caused `BY: FOR MANUFACTURING UNIT ADDRESS, SEE FIRST...` to become a high-confidence date.

## 2. Architecture before/after

Before: full-image OCR → flattened Y-ordered lines → first-match/fixed-distance extraction → OCR confidence copied as field confidence → deterministic rules.

After: full-image OCR → word/token coordinates and OCR provenance → dynamic rows/columns/blocks → global bounded anchors and datatype candidates → strict field validators → deterministic semantic/spatial scoring and hard rejection → calibrated field confidence and tight evidence → deterministic `rules.py` PASS/FAIL/UNCERTAIN → `overall_status`.

The backend remains the only compliance authority. Human corrections still persist, rerun deterministic rules, and append audit events.

## 3. Files changed

- `backend/models.py`: added backwards-compatible OCR token/provenance representation.
- `backend/ocr_engine.py`: retained full-image token boxes, OCR pass/block/line provenance, sparse-pass datatype lines, and original-coordinate mapping.
- `backend/extractor.py`: replaced list-order/fixed-direction matching with global geometry-aware extraction, validators, scoring, confidence calibration, role separation, and contamination rejection.
- `backend/rules/net_quantity.json`: added recognized count-unit declarations while retaining deterministic rule behavior.
- `backend/rules/consumer_care.json`: added validated postal-contact support.
- `backend/tests/test_extractor.py`, `test_orientation.py`, `test_review_and_precision.py`: updated obsolete assumptions and added token/provenance checks.
- `backend/tests/test_layout_independent_extraction.py`: added required datatype, direction, layout, rotation, randomized, and stress matrices.
- `backend/tests/test_final_api_smoke.py`: added the exact required endpoint smoke.
- `docs/LABELGUARD_FINAL_LAYOUT_INDEPENDENT_EXTRACTION_REPORT.md`: this release report.

No UI, deployment, CI, analytics, or database implementation was changed.

## 4. Global full-image extraction method

Both Tesseract full-image passes now retain tokens with confidence, bounding boxes, block/paragraph/line IDs, and source pass. Paddle line polygons are deterministically subdivided into word spans when its adapter supplies line-level recognition only. Extraction builds dynamic rows, column bands, and blocks from the observed geometry. It searches all nodes for MRP, net quantity, date, business-role, consumer, origin, and commodity anchors, and independently discovers price, quantity, date, phone, email, URL, country, company, and address candidates. No production field is assigned an absolute image region.

## 5. Field validators

- Date: calendar-valid day/month/year, month/year, month-name/year, and day/month-name/year only; manufacture/packing anchors are distinct from best-before/use-by/expiry. Prose, address, license, nutrition, and invalid calendar values are rejected.
- MRP: recognized rupee/Rs/INR and anchored numeric prices; phone/date/license/nutrition/percentage/unit-sale contexts are rejected. OCR-confused currency punctuation is accepted only between an explicit MRP anchor and the price, never as a numeric percentage suffix.
- Net Quantity: numeric mass, volume, or count unit; split numeric/unit OCR tokens can be joined geometrically. Nutrition and unit-price contexts are rejected.
- Consumer Care: validated phone, email, URL, or explicitly associated postal contact. License, barcode, batch, and nutrition contexts are rejected.
- Country of Origin: an explicit origin anchor is mandatory. An Indian address, +91 number, company, or FSSAI evidence alone cannot create COO.
- Business roles: manufacturer, packer, marketer, and importer have separate anchor families and outputs.
- Common name: requires explicit commodity-name semantics and cannot be fabricated from a brand, company, address, or nutrition line.

## 6. Candidate scoring

Anchored candidates are scored deterministically using anchor quality (0.28), datatype validity (0.27), OCR confidence (0.14), geometric relation (0.23), and context (0.08), with cross-column and distance penalties. Invalid datatypes and forbidden contexts are hard rejected before ranking. Anchorless recovery is allowed only for intrinsically explicit datatypes at a stricter threshold. Ties resolve by score, distance, geometry, and normalized value, never incoming OCR list order.

## 7. Multi-column handling

Rows are clustered from vertical overlap/centres; column boundaries come from meaningful gaps relative to observed label width and median text height; OCR block IDs are preserved with dynamic block fallback. Same-row, same-column, and same-block relations receive distinct scores. Cross-column jumps are penalized unless the geometry strongly supports the association. The two-column, main-panel/sticker, and nutrition-between-declarations tests all return the same normalized fields.

## 8. Above/below/left/right handling

Association is symmetric. Same-line values before or after an anchor and separate values above, below, left, or right are supported. Tests cover MRP in all four directions, date above and below, value-below layouts, and a consumer phone above its anchor.

## 9. Cross-field false-positive protection

Nutrition grams cannot become Net Quantity; nutrition numbers cannot become MRP; unit sale price cannot replace package MRP; address prose cannot become Date; expiry dates cannot become manufacture dates; FSSAI/license/barcode/batch numbers cannot become consumer phones; an Indian address cannot become COO; manufacturer/company text cannot become common name; and marketed-by does not silently become manufacturer.

## 10. Confidence calibration

Field confidence is calculated from candidate score, OCR confidence, and datatype strength. It is not copied from OCR confidence. Rejected or empty fields always have confidence `0.0` and no evidence box. A high-confidence OCR sentence that is not a date therefore has zero Date confidence.

## 11. Orientation handling

Automatic `0°`, `90°`, `180°`, and `270°` selection remains in `OCRService`. Actual Tesseract OCR tests pass at all four angles. The layout×rotation matrix additionally covers single-column, two-column, separate-panel, and randomized layouts at all four angles.

## 12. Evidence coordinate integrity

Evidence uses OCR word boxes when present, falls back to deterministic span geometry otherwise, and unions only the accepted anchor/value/support tokens. `app.py` maps upright evidence through `map_bbox_to_original` before findings, storage, UI, or PDF use. Rotation tests verify non-empty bounded evidence in original uploaded-image dimensions. Rejected candidates have no evidence.

## 13. Layout randomization results

PASS. Equivalent normalized output was verified for single-column, two-column, MRP top-left, MRP bottom-right, date above, value below, separate price/date sticker, nutrition-between-declarations, and eight deterministic shuffled non-overlapping position seeds.

## 14. Rotation × layout results

PASS. The 16-case matrix (four layouts × four rotations) preserved every expected normalized field and valid original-coordinate evidence. Four additional actual-OCR orientation cases also passed.

## 15. False-positive stress test

PASS. Distractors included `Protein 11.6 g`, `Sugar 32.4 g`, `₹0.63 per g`, FSSAI license, barcode, batch/date, manufacturing address prose, and `Best Before 6 Months`. Expected and obtained values were MRP `₹170.00`, Net Quantity `270 g`, and manufacture date `20/01/2027`.

## 16. Haldiram regression

PASS. Local real-image OCR recovered manufacturer and marketer `Haldiram Snacks Pvt. Ltd.`, address, `200 g`, `₹60.00`, `10/05/2024`, consumer phone/web/email, and India origin. Nutrition did not contaminate statutory values. Brand text exists only in regression data/reporting, not production extraction.

## 17. Snackible regression

PASS with safe uncertainty. Local real-image OCR recovered `55 g`, `₹50`, `03/08/2026`, phone, and website. Allergen/facility prose was no longer promoted to manufacturer; fields without sound evidence remained empty.

## 18. UNIBIC regression

PASS with safe uncertainty. Local real-image OCR recovered marketer `Unibic Foods India Private Limited`, its address, `100 g`, `₹120`, and consumer phone/email/web. It did not silently populate manufacturer; unreadable/unanchored date and origin remained empty.

## 19. Green Basket regression

PASS. Local real-image OCR recovered manufacturer/address, split `500` + `g` as `500 g`, OCR-confused explicit MRP as `₹650.0`, `15/08/2026`, consumer phone, and India origin.

## 20. New package regression

PASS. On the exact local package containing `MFD-BY: FOR MANUFACTURING UNIT ADDRESS, SEE FIRST...`, manufacture date is empty with `0.0` confidence and no evidence. The distant Haryana PIN/license area is also not guessed as MRP. Readable `100 g`, care email/web, and explicit India origin remain available. The record routes unresolved fields to safe uncertainty/manual review.

## 21. Backend tests

PASS: `python -m pytest tests` → `133 passed`, exit `0`. The sole warning is a non-blocking Starlette/httpx test-client deprecation warning.

The explicit API smoke passed GET `/health`, GET `/system/status`, GET `/rules`, POST `/inspect`, GET `/history`, GET `/inspection/{id}`, GET `/report/{id}`, review, correction, and audit. It verified `FIELD_CORRECTED` and `RULES_RE_EVALUATED` audit events and human-correction source tracking.

Tests used isolated temporary runtime data. A read-only compatibility check confirmed the existing production data remains accessible (65 inspections, 9 reviews, 4 corrections, and 53 audit events); no database schema migration or production-record rewrite was performed.

## 22. Frontend typecheck/lint/build

PASS. `npm run typecheck` exited cleanly. `npm run lint` completed with zero warnings. `npm run build` completed with exit `0` and generated all static/dynamic routes successfully.

## 23. npm audit

PASS. `npm audit --audit-level=low` → `found 0 vulnerabilities`.

## 24. Remaining limitations

The system cannot extract declarations that are absent from the visible side, occluded, destroyed by blur/glare, or not recognized sufficiently by OCR. Strict rejection intentionally leaves ambiguous fields empty and routes them to manual review. Very unusual OCR segmentation can still require human correction. Paddle adapters that expose only a line polygon use deterministic per-word subspans inside that polygon; Tesseract supplies native word boxes. These are safe-uncertainty limitations, not presentation-blocking extraction defects.

`LAYOUT-INDEPENDENT EXTRACTION PASS COMPLETE — READY TO FREEZE FOR SIH`

## Final required checks

1. Does any production field rely on fixed image position? **NO**
2. Can MRP appear anywhere visible? **YES**
3. Can Net Quantity appear anywhere visible? **YES**
4. Can Date appear anywhere visible? **YES**
5. Can Consumer Care appear anywhere visible? **YES**
6. Can business information appear anywhere visible? **YES**
7. Are above/below/left/right values supported? **YES**
8. Are multi-column layouts supported? **YES**
9. Can arbitrary prose become Date? **NO**
10. Can nutrition values become MRP/Net Quantity? **NO**
11. Can unit sale price replace MRP? **NO**
12. Can Indian address alone create COO? **NO**
13. Is marketer distinct from manufacturer? **YES**
14. Is field confidence different from OCR confidence? **YES**
15. Are invalid candidates rejected? **YES**
16. Does uncertainty safely become manual review? **YES**
17. Are evidence coordinates original-image pixels? **YES**
18. Are 0/90/180/270 tested? **YES**
19. Are randomized layouts tested? **YES**
20. Is production extraction brand-independent? **YES**
21. Does correction still rerun deterministic rules? **YES**
22. Does any frontend code decide compliance? **NO**
23. Does any LLM decide compliance? **NO**
24. Did all backend/frontend gates pass? **YES**
25. Are there presentation-blocking extraction defects? **NO**

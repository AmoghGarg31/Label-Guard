# Synthetic demo fixtures

These images are generated, not market evidence and not real products. Regenerate them with:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\generate_demo_labels.py
```

- `01-readable-domestic.png`: readable declarations for the happy-path demo.
- `02-missing-mrp.png`: readable label without an MRP declaration.
- `03-rotated-90.png`: the happy-path panel rotated 90 degrees.
- `04-low-quality-blur.png`: intentionally blurred retake/manual-review case.
- `05-malformed-mrp.png`: an MRP anchor with a visibly present invalid value.

OCR outcomes can vary across Tesseract versions. Judges should treat the images as repeatable input fixtures, not assertions that legal compliance is certified.

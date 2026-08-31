"""Standalone OCR smoke test.

Run from the API artifact directory:
    python3 scripts/ocr_sanity.py path/to/label.jpg
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from image_quality import analyze_image_quality  # noqa: E402
from ocr_engine import OCRService  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/ocr_sanity.py path/to/label-image.jpg")
        return 2

    image_path = Path(sys.argv[1])
    if not image_path.is_file():
        print(f"Image not found: {image_path}")
        return 2

    image_bytes = image_path.read_bytes()
    quality = analyze_image_quality(image_bytes)
    result = OCRService().extract(image_bytes)
    print(json.dumps({
        "image": str(image_path),
        "quality": quality,
        "engine": result.engine,
        "error": result.error,
        "lines": [
            {
                "text": line.text,
                "confidence": round(line.confidence, 3),
                "bounding_box": line.bounding_box,
            }
            for line in result.lines
        ],
        "text": result.text,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
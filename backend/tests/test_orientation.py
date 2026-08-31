from io import BytesIO
from pathlib import Path
import gc

import pytest
from PIL import Image, ImageDraw, ImageFont

from extractor import extract_fields
from ocr_engine import OCRService


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_arial = Path(r"C:\Windows\Fonts\arial.ttf")
    if windows_arial.exists():
        return ImageFont.truetype(str(windows_arial), size)
    return ImageFont.load_default()


def _synthetic_label(rotation: int) -> bytes:
    image = Image.new("RGB", (820, 430), "white")
    draw = ImageDraw.Draw(image)
    title = _font(32)
    body = _font(26)
    draw.rectangle((24, 24, 796, 406), outline="black", width=3)
    draw.text((55, 45), "ACME TEST LABEL", fill="black", font=title)
    rows = [
        "Common name: Roasted chickpea snack",
        "Net Quantity: 500 g",
        "MRP: Rs. 120",
        "MFD: 08/2026",
    ]
    for index, row in enumerate(rows):
        draw.text((55, 112 + index * 67), row, fill="black", font=body)
    rotated = image.rotate(rotation, expand=True, fillcolor="white")
    output = BytesIO()
    rotated.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("input_rotation", [0, 90, 180, 270])
def test_real_ocr_auto_orientation_on_four_right_angles(input_rotation: int) -> None:
    service = OCRService()
    service.preference = "pytesseract"
    if not service.capabilities().get("available"):
        pytest.skip("Tesseract is unavailable in this runtime")

    result = service.extract(_synthetic_label(input_rotation))
    fields = extract_fields(result.lines)

    assert result.orientation_degrees == input_rotation
    assert fields["net_quantity"].value == "500 g"
    assert fields["mrp"].value == "₹120"
    assert fields["date_of_manufacture"].value == "08/2026"
    assert len(result.lines) >= 5
    assert any(line.tokens for line in result.lines)
    assert all(
        token.bounding_box is not None
        for line in result.lines
        for token in line.tokens
    )
    del fields, result, service
    gc.collect()


@pytest.mark.parametrize(
    ("angle", "rotated_box", "expected"),
    [
        (0, (10, 20, 30, 40), (10, 20, 30, 40)),
        (90, (20, 70, 40, 90), (70, 60, 90, 80)),
        (180, (70, 60, 90, 80), (10, 20, 30, 40)),
        (270, (60, 10, 80, 30), (70, 60, 90, 80)),
    ],
)
def test_bbox_mapping_is_bounded_and_deterministic(
    angle: int, rotated_box: tuple[int, int, int, int], expected: tuple[int, int, int, int]
) -> None:
    assert OCRService.map_bbox_to_original(rotated_box, angle, 100, 100) == expected

import random

import pytest

from extractor import extract_fields, targeted_ocr_requests, values_only
from models import OcrLine, OcrToken
from ocr_engine import OCRService


EXPECTED = {
    "common_or_generic_name": "Roasted chickpea snack",
    "manufacturer_name": "Example Foods Pvt. Ltd.",
    "manufacturer_address": "Plot 12, Industrial Estate, Pune 411001, India",
    "net_quantity": "500 g",
    "mrp": "₹170.00",
    "date_of_manufacture": "12 AUG 2026",
    "consumer_care_contact": "1800 123 4567",
    "country_of_origin": "India",
}


DECLARATIONS = [
    "Common name: Roasted chickpea snack",
    "Manufactured by: Example Foods Pvt. Ltd., Plot 12, Industrial Estate, Pune 411001, India",
    "Net Quantity: 500 g",
    "MRP: ₹170.00",
    "MFD: 12 AUG 2026",
    "Consumer Care: 1800 123 4567",
    "Country of Origin: India",
]


def _line(text: str, x: int, y: int, width: int = 430, block: str | None = None) -> OcrLine:
    return OcrLine(text, 0.94, (x, y, x + width, y + 28), block_id=block)


def _assert_expected(lines: list[OcrLine]) -> None:
    fields = extract_fields(lines)
    for field, expected in EXPECTED.items():
        assert fields[field].value == expected, (field, fields[field], values_only(fields))
        assert fields[field].confidence >= 0.55
        assert fields[field].bounding_box is not None


@pytest.mark.parametrize("value", ["20/01/2027", "20-01-2027", "01/2027", "JAN 2027", "12 AUG 2026"])
def test_date_validator_accepts_supported_manufacture_dates(value: str) -> None:
    fields = extract_fields([_line(f"MFD: {value}", 100, 100)])
    assert fields["date_of_manufacture"].value == value


@pytest.mark.parametrize(
    ("anchor_box", "value_box"),
    [
        ((100, 100, 230, 130), (300, 100, 430, 130)),  # right
        ((300, 100, 430, 130), (100, 100, 230, 130)),  # left
        ((200, 180, 380, 210), (200, 100, 380, 130)),  # above
        ((200, 100, 380, 130), (200, 180, 380, 210)),  # below
    ],
)
def test_mrp_anchor_value_association_in_every_direction(anchor_box, value_box) -> None:
    lines = [OcrLine("MRP", 0.91, anchor_box), OcrLine("₹170.00", 0.93, value_box)]
    assert extract_fields(lines)["mrp"].value == "₹170.00"


def test_date_value_above_anchor() -> None:
    lines = [_line("20/01/2027", 200, 80), _line("Date of Manufacture", 200, 140)]
    assert extract_fields(lines)["date_of_manufacture"].value == "20/01/2027"


def test_date_value_below_anchor() -> None:
    lines = [_line("Date of Manufacture", 200, 80), _line("20/01/2027", 200, 140)]
    assert extract_fields(lines)["date_of_manufacture"].value == "20/01/2027"


def test_address_prose_and_known_regression_phrase_are_not_dates() -> None:
    lines = [
        _line("Manufactured by: Example Foods Pvt. Ltd.", 20, 20),
        _line("BY: FOR MANUFACTURING UNIT ADDRESS, SEE FIRST PANEL", 20, 70),
        _line("Plot 20, Industrial Estate, Pune 411001, India", 20, 120),
    ]
    evidence = extract_fields(lines)["date_of_manufacture"]
    assert evidence.value is None
    assert evidence.confidence == 0.0
    assert evidence.bounding_box is None


def test_manufactured_by_business_anchor_is_not_a_date_anchor() -> None:
    fields = extract_fields([_line("Manufactured by: Example Foods Pvt. Ltd.", 10, 10)])
    assert fields["manufacturer_name"].value == "Example Foods Pvt. Ltd."
    assert fields["date_of_manufacture"].value is None


def test_mrp_validator_accepts_currency_and_rejects_unit_price() -> None:
    lines = [
        _line("MRP", 20, 20, 100),
        _line("₹3 per g", 160, 20, 130),
        _line("Rs. 170.00", 330, 20, 180),
    ]
    assert extract_fields(lines)["mrp"].value == "₹170.00"


def test_inline_package_price_beats_inline_unit_sale_price() -> None:
    fields = extract_fields([_line("MRP Rs. 170.00   Rs.0.63 per g", 20, 20)])
    assert fields["mrp"].value == "₹170.00"


def test_mrp_rejects_usp_slash_unit_with_ocr_whitespace() -> None:
    lines = [
        _line("MRP: ₹180.00", 20, 20),
        _line("USP: ₹0.51/ g", 20, 70),
    ]
    assert extract_fields(lines)["mrp"].value == "₹180.00"


def test_unit_price_classification_is_reconciled_across_ocr_passes() -> None:
    lines = [
        OcrLine("MRP", 0.92, (100, 100, 170, 130), source_pass="tesseract-psm6"),
        OcrLine("Rs. 170.00", 0.88, (260, 100, 380, 130), source_pass="tesseract-psm6"),
        OcrLine("Rs. 0.6", 0.86, (430, 100, 510, 130), source_pass="tesseract-psm6"),
        OcrLine("Rs. 0.63 Per g", 0.91, (425, 99, 570, 132), source_pass="tesseract-psm11"),
    ]
    assert extract_fields(lines)["mrp"].value == "₹170.00"


@pytest.mark.parametrize("text", ["MRP ₹0.63 per g", "MRP Rs 2 per ml", "MRP ₹5/10g", "MRP Rs.0.63 Per s"])
def test_denominator_price_is_never_mrp_even_with_an_mrp_anchor(text: str) -> None:
    assert extract_fields([_line(text, 20, 20)])["mrp"].value is None


def test_mrp_does_not_select_a_nearby_multipack_count() -> None:
    lines = [_line("(4 Units x 67.5 g)", 20, 20), _line("MRP", 20, 65)]
    assert extract_fields(lines)["mrp"].value is None


def test_mrp_does_not_select_untyped_isolated_integers_from_another_panel() -> None:
    lines = [
        OcrLine("5", 0.91, (50, 100, 65, 120), source_pass="tesseract-psm11"),
        OcrLine("131028", 0.88, (50, 140, 130, 160), source_pass="tesseract-psm11"),
        OcrLine("MRP", 0.93, (350, 100, 410, 125), source_pass="tesseract-psm11"),
    ]
    assert extract_fields(lines)["mrp"].value is None


def test_ocr_pass_disagreement_returns_uncertain_and_requests_local_retry() -> None:
    lines = [
        OcrLine("MRP Rs. 120.00", 0.86, (100, 100, 300, 135), source_pass="tesseract-psm6"),
        OcrLine("MRP Rs. 170.00", 0.86, (100, 100, 300, 135), source_pass="tesseract-psm11"),
    ]
    fields = extract_fields(lines)
    assert fields["mrp"].value is None
    requests = targeted_ocr_requests(lines, fields)
    assert [request.field for request in requests] == ["mrp"]


def test_disagreement_never_promotes_an_unrelated_third_number() -> None:
    lines = [
        OcrLine("NET QUANTITY", 0.95, (100, 100, 350, 135), source_pass="tesseract-psm6"),
        OcrLine("500", 0.95, (100, 145, 260, 190), source_pass="tesseract-psm6"),
        OcrLine("g", 0.95, (270, 145, 300, 190), source_pass="tesseract-psm6"),
        OcrLine("MRP: 3650.00", 0.86, (100, 220, 350, 255), source_pass="tesseract-psm6"),
        OcrLine("MRP: 650.00", 0.86, (100, 220, 350, 255), source_pass="tesseract-psm11"),
    ]
    assert extract_fields(lines)["mrp"].value is None


def test_two_ocr_passes_agree_on_price() -> None:
    lines = [
        OcrLine("MRP Rs. 170.00", 0.86, (100, 100, 300, 135), source_pass="tesseract-psm6"),
        OcrLine("MRP Rs. 170.00", 0.88, (101, 100, 301, 135), source_pass="tesseract-psm11"),
    ]
    evidence = extract_fields(lines)["mrp"]
    assert evidence.value == "₹170.00"
    assert evidence.confidence >= 0.90


@pytest.mark.parametrize("anchor", ["M.R.P.", "Maximum Retail Price", "Retail Sale Price"])
def test_mrp_anchor_family_variants(anchor: str) -> None:
    assert extract_fields([_line(f"{anchor}: Rs.170/-", 20, 20)])["mrp"].value == "₹170"


@pytest.mark.parametrize("anchor", ["NETWT", "Net Contents", "Net Quantity"])
def test_net_anchor_family_variants(anchor: str) -> None:
    assert extract_fields([_line(f"{anchor}: 270 g", 20, 20)])["net_quantity"].value == "270 g"


@pytest.mark.parametrize("anchor", ["Packing Date", "Pre-packed", "Manufactured On"])
def test_date_anchor_family_variants(anchor: str) -> None:
    assert extract_fields([_line(f"{anchor}: 20/01/2027", 20, 20)])["date_of_manufacture"].value == "20/01/2027"


def test_net_quantity_accepts_count_and_rejects_nutrition_protein() -> None:
    count = extract_fields([_line("Net Quantity: 4 units", 20, 20)])
    assert count["net_quantity"].value == "4 units"
    distractor = extract_fields([_line("Nutrition Facts Protein 12 g", 20, 20)])
    assert distractor["net_quantity"].value is None


@pytest.mark.parametrize(
    "text",
    [
        "Quantity per 100 g: Energy 490 kcal",
        "Quantity per 100 g",
        "Protein 11.6 g",
        "11.6 g Protein",
    ],
)
def test_nutrition_quantity_is_hard_rejected_even_when_quantity_precedes_nutrition(text: str) -> None:
    evidence = extract_fields([_line(text, 20, 20)])["net_quantity"]
    assert evidence.value is None
    assert evidence.bounding_box is None


def test_net_weight_does_not_fall_back_to_a_multipack_component() -> None:
    lines = [
        _line("NET WEIGHT: 270?", 20, 20),
        _line("(4 Units x 67.5 g)", 20, 65),
        _line("Quantity per 100 g: Energy 490 kcal", 20, 110),
    ]
    assert extract_fields(lines)["net_quantity"].value is None


def test_fuzzy_weight_anchor_does_not_turn_pack_count_into_weight() -> None:
    lines = [
        OcrLine("BISCUITS NETWEICHT: 270?", 0.72, (20, 20, 330, 50), source_pass="tesseract-psm11"),
        OcrLine("4 units", 0.95, (340, 20, 430, 50), source_pass="tesseract-psm11"),
    ]
    assert extract_fields(lines)["net_quantity"].value is None


def test_distant_nutrition_value_inside_targeted_crop_cannot_bind_to_net_anchor() -> None:
    lines = [
        OcrLine("Sodium", 0.95, (450, 300, 520, 325), block_id="nutrition"),
        OcrLine("13.0 mg", 0.95, (550, 300, 630, 325), block_id="nutrition"),
        OcrLine("NET WEIGHT", 0.93, (450, 900, 600, 930), block_id="sticker"),
    ]
    assert extract_fields(lines)["net_quantity"].value is None


def test_batch_number_and_distant_unit_fragment_cannot_form_net_quantity() -> None:
    lines = [
        _line("NET WEIGHT", 100, 700),
        OcrLine("61520513", 0.96, (260, 520, 420, 565), source_pass="targeted-psm11"),
        OcrLine("g", 0.95, (20, 790, 35, 825), source_pass="targeted-psm11"),
    ]
    assert extract_fields(lines)["net_quantity"].value is None


def test_explicit_net_unit_glyph_can_use_nearby_multipack_unit_corroboration() -> None:
    lines = [
        OcrLine(
            "BISCUITS NET WEIGHT: 2705...",
            0.86,
            (100, 100, 430, 135),
            source_pass="tesseract-psm11",
        ),
        OcrLine(
            "(4 Units x 67.5 g)",
            0.95,
            (270, 145, 470, 180),
            source_pass="tesseract-psm11",
        ),
    ]
    assert extract_fields(lines)["net_quantity"].value == "270 g"
    assert extract_fields(lines[:1])["net_quantity"].value is None


def test_consumer_phone_is_accepted_but_license_number_is_not() -> None:
    care = extract_fields([_line("Consumer Care Phone: +91 99203 35511", 20, 20)])
    assert care["consumer_care_contact"].value == "+91 99203 35511"
    license_only = extract_fields([_line("FSSAI License No: 123456789012", 20, 20)])
    assert license_only["consumer_care_contact"].value is None


def test_consumer_context_does_not_turn_ean_barcode_into_phone() -> None:
    barcode = extract_fields([_line("Consumer Care Barcode: 8904063226402", 20, 20)])
    assert barcode["consumer_care_contact"].value is None


def test_consumer_accepts_india_prefixed_toll_free_number() -> None:
    care = extract_fields([_line("Consumer Care: +91 1800 123 4567", 20, 20)])
    assert care["consumer_care_contact"].value == "+91 1800 123 4567"


def test_nearby_business_address_is_not_consumer_postal_contact() -> None:
    lines = [
        _line("Packed and Marketed by: Example Foods Pvt. Ltd., Plot 90, Pune 411001", 20, 20),
        _line("Customer Care: unreadable", 20, 70),
    ]
    assert extract_fields(lines)["consumer_care_contact"].value is None


def test_consumer_phone_can_be_above_its_anchor() -> None:
    lines = [_line("1800 123 4567", 200, 50), _line("Consumer Care", 200, 110)]
    assert extract_fields(lines)["consumer_care_contact"].value == "1800 123 4567"


def test_far_date_digits_cannot_join_a_consumer_contact() -> None:
    lines = [
        _line("Consumer Care", 100, 100),
        _line("+91 96061 22221", 100, 145),
        _line("MFG DATE", 100, 600),
        _line("2170742026", 100, 645),
    ]
    assert extract_fields(lines)["consumer_care_contact"].value == "+91 96061 22221"


def test_country_requires_explicit_origin_anchor() -> None:
    explicit = extract_fields([_line("Country of Origin: India", 20, 20)])
    assert explicit["country_of_origin"].value == "India"
    address_only = extract_fields([_line("Plot 12, Industrial Estate, Pune 411001, India", 20, 20)])
    assert address_only["country_of_origin"].value is None


def test_explicit_origin_supports_country_names_outside_fixture_shortlist() -> None:
    fields = extract_fields([_line("Made in Luxembourg", 20, 20)])
    assert fields["country_of_origin"].value == "Luxembourg"


def test_business_roles_remain_distinct() -> None:
    lines = [
        _line("Manufactured by: Factory Foods Pvt. Ltd.", 20, 20),
        _line("Marketed by: Market Foods Pvt. Ltd.", 520, 20),
    ]
    fields = extract_fields(lines)
    assert fields["manufacturer_name"].value == "Factory Foods Pvt. Ltd."
    assert fields["marketer_name"].value == "Market Foods Pvt. Ltd."


def test_contact_instruction_does_not_become_marketer_role() -> None:
    lines = [
        _line("Marketed by: Das Foodtech Private Limited", 20, 20),
        _line("marketed by address, call or email us at", 20, 70),
        _line("support@example.test", 20, 120),
    ]
    fields = extract_fields(lines)
    assert fields["marketer_name"].value == "Das Foodtech Private Limited"
    assert fields["consumer_care_contact"].value == "support@example.test"


def test_pintola_like_curved_label_regression_is_semantically_safe() -> None:
    phone_tokens = (
        OcrToken("78080", 0.97, (115, 540, 205, 575)),
        OcrToken("58080", 0.96, (215, 540, 305, 575)),
        OcrToken("Energy", 0.18, (620, 540, 700, 575)),
    )
    lines = [
        _line("ured By: Das Superfoods Private Limited", 100, 40, 440),
        _line("Marketed By: Das Foodtech Private Limited", 100, 190, 460),
        _line("consumer care cell at the", 100, 490, 350),
        OcrLine(
            "78080 58080 Energy",
            0.48,
            (115, 540, 700, 575),
            tokens=phone_tokens,
            source_pass="tesseract-psm6",
        ),
        _line("marketed by address, call or email us at", 100, 575, 450),
        _line("support@pintola.in", 100, 620, 300),
        _line("MRP", 100, 690, 80),
        _line("₹180.00", 290, 690, 130),
        _line("USP", 100, 775, 80),
        _line("₹0.51/ g", 290, 775, 130),
        _line("BATCH NO.", 100, 825, 130),
        _line("61520513", 290, 825, 150),
        _line("MFG. DATE", 100, 875, 150),
        _line("01/06/2026", 290, 875, 170),
        _line("USE BY", 100, 925, 120),
        _line("31/05/2027", 290, 925, 170),
        _line("Net Weight", 100, 990, 150),
        _line("350¢g", 290, 990, 100),
        _line("Nutrition information per 100 g", 620, 760, 350),
    ]
    fields = extract_fields(lines)
    assert fields["manufacturer_name"].value == "Das Superfoods Private Limited"
    assert fields["marketer_name"].value == "Das Foodtech Private Limited"
    assert fields["mrp"].value == "₹180.00"
    assert fields["net_quantity"].value == "350 g"
    assert fields["date_of_manufacture"].value == "01/06/2026"
    assert "support@pintola.in" in (fields["consumer_care_contact"].value or "")
    assert "78080 58080" in (fields["consumer_care_contact"].value or "")
    assert fields["common_or_generic_name"].value is None
    assert fields["country_of_origin"].value is None
    assert fields["mrp"].bounding_box is not None
    assert fields["mrp"].bounding_box[3] < 800


def _layout(name: str, seed: int = 0) -> list[OcrLine]:
    if name == "single_column":
        return [_line(text, 40, 40 + index * 70) for index, text in enumerate(DECLARATIONS)]
    if name == "two_column":
        return [_line(text, 40 + (index % 2) * 600, 40 + (index // 2) * 90) for index, text in enumerate(DECLARATIONS)]
    if name == "mrp_top_left":
        order = [3, 0, 1, 2, 4, 5, 6]
        return [_line(DECLARATIONS[index], 30 + (pos % 2) * 560, 30 + (pos // 2) * 85) for pos, index in enumerate(order)]
    if name == "mrp_bottom_right":
        order = [0, 1, 2, 4, 5, 6, 3]
        return [_line(DECLARATIONS[index], 30 + (pos % 2) * 560, 30 + (pos // 2) * 85) for pos, index in enumerate(order)]
    if name == "date_above":
        lines = [_line(text, 50, 80 + index * 65) for index, text in enumerate(DECLARATIONS) if not text.startswith("MFD")]
        lines.extend([_line("12 AUG 2026", 720, 30), _line("Date of Manufacture", 720, 90)])
        return lines
    if name == "value_below":
        lines = [_line(text, 50, 80 + index * 65) for index, text in enumerate(DECLARATIONS) if not text.startswith("MRP")]
        lines.extend([_line("MRP", 720, 30), _line("₹170.00", 720, 90)])
        return lines
    if name == "separate_panel":
        lines: list[OcrLine] = []
        main_y = 40
        sticker_y = 70
        for index, text in enumerate(DECLARATIONS):
            if index in {3, 4}:
                lines.append(_line(text, 700, sticker_y, block="price-date-sticker"))
                sticker_y += 80
            else:
                lines.append(_line(text, 60, main_y, block="main-panel"))
                main_y += 75
        return lines
    if name == "nutrition_between":
        lines = [_line(text, 40, 40 + index * 80) for index, text in enumerate(DECLARATIONS)]
        lines.extend([_line("Nutrition Facts Protein 12 g", 620, 110), _line("Unit sale price ₹3 per g", 620, 180)])
        return lines
    if name == "random":
        rng = random.Random(seed)
        points = [(20 + column * 500, 20 + row * 120) for row in range(3) for column in range(3)]
        rng.shuffle(points)
        points = points[:len(DECLARATIONS)]
        lines = [_line(text, x, y, 390) for text, (x, y) in zip(DECLARATIONS, points)]
        rng.shuffle(lines)
        return lines
    raise AssertionError(name)


@pytest.mark.parametrize(
    "layout_name",
    ["single_column", "two_column", "mrp_top_left", "mrp_bottom_right", "date_above", "value_below", "separate_panel", "nutrition_between"],
)
def test_layout_invariance_matrix(layout_name: str) -> None:
    _assert_expected(_layout(layout_name))


@pytest.mark.parametrize("seed", range(8))
def test_randomized_position_and_input_order_invariance(seed: int) -> None:
    _assert_expected(_layout("random", seed))


@pytest.mark.parametrize("layout_name", ["single_column", "two_column", "separate_panel", "random"])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotation_by_layout_matrix_preserves_values_and_original_coordinate_evidence(layout_name: str, rotation: int) -> None:
    lines = _layout(layout_name, seed=17)
    fields = extract_fields(lines)
    source_width, source_height = 1500, 900
    original_width, original_height = (source_width, source_height) if rotation in {0, 180} else (source_height, source_width)
    for field, expected in EXPECTED.items():
        evidence = fields[field]
        assert evidence.value == expected
        mapped = OCRService.map_bbox_to_original(evidence.bounding_box, rotation, original_width, original_height)
        assert mapped is not None
        x1, y1, x2, y2 = mapped
        assert 0 <= x1 < x2 <= original_width
        assert 0 <= y1 < y2 <= original_height


def test_false_positive_stress_pack_returns_only_expected_statutory_values() -> None:
    lines = [
        _line("Nutrition Facts Protein 11.6 g Sugar 32.4 g", 20, 20),
        _line("Unit sale price ₹0.63 per g", 20, 70),
        _line("FSSAI License No 123456789012 Batch 20/01/2027", 20, 120),
        _line("Barcode 8901234567890", 20, 170),
        _line("Best Before 6 Months", 20, 220),
        _line("BY: FOR MANUFACTURING UNIT ADDRESS, SEE FIRST PANEL", 20, 270),
        _line("Plot 20, Industrial Estate, Pune 411001, India", 20, 320),
        _line("Net Weight: 270 g", 650, 20),
        _line("MRP: ₹170.00", 650, 70),
        _line("MFG DATE: 20/01/2027", 650, 120),
        _line("Consumer Care: care@example.test", 650, 170),
        _line("Country of Origin: India", 650, 220),
    ]
    fields = extract_fields(lines)
    assert fields["net_quantity"].value == "270 g"
    assert fields["mrp"].value == "₹170.00"
    assert fields["date_of_manufacture"].value == "20/01/2027"
    assert fields["consumer_care_contact"].value == "care@example.test"
    assert fields["country_of_origin"].value == "India"


def test_word_token_evidence_uses_tight_token_coordinates() -> None:
    tokens = (
        OcrToken("MRP", 0.90, (10, 10, 60, 35)),
        OcrToken("₹170.00", 0.92, (300, 10, 390, 35)),
    )
    line = OcrLine("MRP ₹170.00", 0.91, (10, 10, 390, 35), tokens=tokens, block_id="panel-1")
    evidence = extract_fields([line])["mrp"]
    assert evidence.value == "₹170.00"
    assert evidence.bounding_box == (10, 10, 390, 35)


def test_field_confidence_is_calibrated_not_copied_from_ocr() -> None:
    evidence = extract_fields([_line("MRP: ₹170.00", 20, 20)])["mrp"]
    assert evidence.confidence >= 0.55
    assert evidence.confidence != 0.94

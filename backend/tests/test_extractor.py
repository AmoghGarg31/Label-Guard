from extractor import extract_fields, format_extracted_fields
from models import OcrLine


def test_normalizes_quantity_with_metric_unit() -> None:
    fields = extract_fields([
        OcrLine("Net Quantity: 500 g", 0.95, (1, 2, 120, 30)),
    ])
    assert fields["net_quantity"].value == "500 g"


def test_normalizes_mrp_with_rupee_symbol() -> None:
    fields = extract_fields([
        OcrLine("MRP: Rs 650.00", 0.95, (1, 2, 180, 30)),
    ])
    assert fields["mrp"].value == "₹650.00"


def test_mrp_separators_and_anchors() -> None:
    cases = [
        ("M.R.P. = : 60.00", "₹60.00"),
        ("M.R.P.: Rs. 60.00", "₹60.00"),
        ("MRP ₹60", "₹60"),
        ("Maximum Retail Price INR 60.00", "₹60.00"),
    ]
    for text, expected in cases:
        fields = extract_fields([OcrLine(text, 0.90, (10, 10, 100, 30))])
        assert fields["mrp"].value == expected, f"Failed on {text}, got {fields['mrp'].value}"


def test_mrp_does_not_match_sugars_or_trailing_rs_words() -> None:
    lines = [
        OcrLine("Total Sugars 2.39", 0.95, (10, 10, 100, 30)),
        OcrLine("Pending Orders 45.00", 0.95, (10, 10, 100, 30)),
        OcrLine("Batch Numbers 12.5", 0.95, (10, 10, 100, 30)),
    ]
    fields = extract_fields(lines)
    assert fields["mrp"].value is None


def test_mrp_anchored_candidate_takes_precedence_over_sugars() -> None:
    lines = [
        OcrLine("TO THE CONSUMER SERVICE MANAGER AT Total Sugars 2.39", 0.99, (10, 10, 100, 30)),
        OcrLine("M.R.P. = : 60.00 *Approximate Values", 0.85, (50, 10, 100, 30)),
    ]
    fields = extract_fields(lines)
    assert fields["mrp"].value == "₹60.00"


def test_manufacturer_multiline_heading_and_name() -> None:
    lines = [
        OcrLine("TURED & MARKETED BY:", 0.95, (10, 10, 100, 30)),
        OcrLine("Example Snacks Pvt. Ltd.", 0.90, (20, 10, 100, 30)),
    ]
    fields = extract_fields(lines)
    assert fields["manufacturer_name"].value == "Example Snacks Pvt. Ltd."
    assert fields["manufacturer_name"].confidence >= 0.55
    assert fields["manufacturer_name"].confidence != 0.90


def test_empty_value_confidence_is_strictly_zero() -> None:
    fields = extract_fields([
        OcrLine("Some unrelated label noise", 0.98, (10, 10, 100, 30)),
    ])
    formatted = format_extracted_fields(fields)
    assert formatted["mrp"]["text"] == ""
    assert formatted["mrp"]["confidence"] == 0.0
    assert formatted["manufacturer_name"]["text"] == ""
    assert formatted["manufacturer_name"]["confidence"] == 0.0
    assert formatted["net_quantity"]["text"] == ""
    assert formatted["net_quantity"]["confidence"] == 0.0


def test_manufacturer_address_excludes_nutrition_serving_size() -> None:
    lines = [
        OcrLine("MARKETED BY:", 0.95, (10, 10, 100, 30)),
        OcrLine("Example Snacks Pvt. Ltd.", 0.90, (20, 10, 100, 30)),
        OcrLine("A-1, Sector-68, Noida-201307 Serving Size 30g", 0.85, (30, 10, 100, 30)),
        OcrLine("Gautam Buddha Nagar, (U.P.) India", 0.88, (40, 10, 100, 30)),
    ]
    fields = extract_fields(lines)
    address = fields["marketer_address"].value or ""
    assert "Serving Size 30g" not in address
    assert "Noida-201307" in address
    assert "India" in address


def test_common_name_and_month_year_are_extracted_without_brand_logic() -> None:
    lines = [
        OcrLine("Common name: Roasted chickpea snack", 0.91, (10, 10, 310, 35)),
        OcrLine("MFD: 08/2026", 0.89, (10, 45, 180, 70)),
    ]
    fields = extract_fields(lines)
    assert fields["common_or_generic_name"].value == "Roasted chickpea snack"
    assert fields["date_of_manufacture"].value == "08/2026"


def test_mfg_abbreviation_accepts_month_year() -> None:
    fields = extract_fields([OcrLine("MFG: 08/2026", 0.94, (10, 10, 180, 40))])
    assert fields["date_of_manufacture"].value == "08/2026"


def test_unambiguous_malformed_mrp_and_net_are_retained_for_format_rules() -> None:
    fields = extract_fields([
        OcrLine("MRP: ask retailer", 0.93, (10, 10, 240, 40)),
        OcrLine("NET QUANTITY: five handfuls", 0.92, (10, 50, 320, 80)),
        OcrLine("MFG: see batch", 0.91, (10, 90, 220, 120)),
    ])
    assert fields["mrp"].value == "ask retailer"
    assert fields["mrp"].confidence >= 0.55
    assert fields["net_quantity"].value == "five handfuls"
    assert fields["net_quantity"].confidence >= 0.55
    assert fields["date_of_manufacture"].value is None


def test_single_pass_malformed_value_stays_uncertain_when_provenance_exists() -> None:
    fields = extract_fields([
        OcrLine(
            "MRP: ask retailer",
            0.93,
            (10, 10, 240, 40),
            source_pass="tesseract-psm6",
        ),
    ])
    assert fields["mrp"].value is None


def test_two_ocr_passes_can_confirm_same_malformed_value() -> None:
    fields = extract_fields([
        OcrLine("MRP: ask retailer", 0.93, (10, 10, 240, 40), source_pass="tesseract-psm6"),
        OcrLine("MRP: ask retailer", 0.91, (10, 10, 240, 40), source_pass="tesseract-psm11"),
    ])
    assert fields["mrp"].value == "ask retailer"


def test_consumer_care_contact_extraction() -> None:
    lines = [
        OcrLine("FOR FEEDBACK OR QUERIES, WRITE TO:", 0.90, (10, 10, 100, 30)),
        OcrLine("CARE@EXAMPLE.TEST", 0.92, (20, 10, 100, 30)),
        OcrLine("VISIT US AT WWW.EXAMPLE.TEST", 0.91, (30, 10, 100, 30)),
    ]
    fields = extract_fields(lines)
    contact = fields["consumer_care_contact"].value or ""
    assert "care@example.test" in contact


def test_consumer_care_accepts_web_only_channel() -> None:
    fields = extract_fields([OcrLine("Consumer Care: www.example.test", 0.92, (10, 10, 260, 35))])
    assert fields["consumer_care_contact"].value == "www.example.test"


def test_extracts_net_quantity_with_dot_colon_and_no_space() -> None:
    cases = [
        ("NETWT.: 55g", "55 g"),
        ("NET WT: 55 g", "55 g"),
        ("NET WT.: 55 g", "55 g"),
        ("Quantity: 100 ml", "100 ml"),
    ]
    for text, expected in cases:
        fields = extract_fields([OcrLine(text, 0.90, (10, 10, 100, 30))])
        assert fields["net_quantity"].value == expected, f"Failed on {text}, got {fields['net_quantity'].value}"


def test_extracts_mrp_with_slash_dash_and_noise() -> None:
    cases = [
        ("MRP ₹: 50/-", "₹50"),
        ("MRP: 50/-", "₹50"),
        ("WRP: 50) [o])", "₹50"),
        ("MRP %: 50/-", "₹50"),
    ]
    for text, expected in cases:
        fields = extract_fields([OcrLine(text, 0.90, (10, 10, 100, 30))])
        assert fields["mrp"].value == expected, f"Failed on {text}, got {fields['mrp'].value}"


def test_percentage_value_is_not_an_mrp() -> None:
    fields = extract_fields([OcrLine("MRP: 20%", 0.95, (10, 10, 150, 35))])
    assert fields["mrp"].value is None


def test_extracts_packaging_and_mfg_dates() -> None:
    cases = [
        ("DATE OF PKG: 03/08/2026", "03/08/2026"),
        ("PKD: 03/08/2026", "03/08/2026"),
        ("DATE OF PACKING: 15-08-2024", "15-08-2024"),
        ("MFD: 10/05/2024", "10/05/2024"),
    ]
    for text, expected in cases:
        fields = extract_fields([OcrLine(text, 0.90, (10, 10, 100, 30))])
        assert fields["date_of_manufacture"].value == expected, f"Failed on {text}, got {fields['date_of_manufacture'].value}"


def test_extracts_phone_numbers_with_spaces() -> None:
    lines = [
        OcrLine("Phone: +91 99203 35511", 0.88, (10, 10, 100, 30)),
    ]
    fields = extract_fields(lines)
    assert fields["consumer_care_contact"].value == "+91 99203 35511"


def test_facility_allergen_statement_is_never_extracted_as_manufacturer() -> None:
    lines = [
        OcrLine("Contains milk & soy products. Manufactured in a facility that also processes wheat", 0.92, (10, 10, 200, 30)),
        OcrLine("Manufactured by: Lightsaber Food Ventures Pvt. Ltd.", 0.89, (10, 40, 200, 60)),
        OcrLine("Nalasopara West, Vasai, Maharashtra - 401203", 0.85, (10, 70, 200, 90)),
    ]
    fields = extract_fields(lines)
    assert fields["manufacturer_name"].value == "Lightsaber Food Ventures Pvt. Ltd."
    assert "facility" not in (fields["manufacturer_name"].value or "").lower()
    assert "wheat" not in (fields["manufacturer_address"].value or "").lower()


def test_spatial_key_value_association_across_columns() -> None:
    lines = [
        OcrLine("NET WEIGHT", 0.34, (50, 100, 150, 120)),
        OcrLine(": 200 g", 0.913, (300, 100, 380, 120)),
    ]
    fields = extract_fields(lines)
    assert fields["net_quantity"].value == "200 g"
    assert fields["net_quantity"].confidence >= 0.55
    assert fields["net_quantity"].confidence != 0.913
    assert fields["net_quantity"].bounding_box == (50, 100, 380, 120)


def test_mrp_spatial_confidence_preservation() -> None:
    lines = [
        OcrLine("M.R.P.", 0.40, (50, 150, 120, 170)),
        OcrLine(": 60.00", 0.935, (300, 150, 380, 170)),
    ]
    fields = extract_fields(lines)
    assert fields["mrp"].value == "₹60.00"
    assert fields["mrp"].confidence >= 0.55
    assert fields["mrp"].confidence != 0.935
    assert fields["mrp"].bounding_box == (50, 150, 380, 170)


def test_date_spatial_confidence_preservation() -> None:
    lines = [
        OcrLine("DATE OF MANUFACTURE", 0.45, (50, 200, 220, 220)),
        OcrLine(": 10/05/2024", 0.92, (300, 200, 420, 220)),
    ]
    fields = extract_fields(lines)
    assert fields["date_of_manufacture"].value == "10/05/2024"
    assert fields["date_of_manufacture"].confidence >= 0.55
    assert fields["date_of_manufacture"].confidence != 0.92
    assert fields["date_of_manufacture"].bounding_box == (50, 200, 420, 220)

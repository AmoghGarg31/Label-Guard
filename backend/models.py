"""Small internal data structures shared by the inspection pipeline."""

from dataclasses import dataclass


BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class OcrToken:
    """One OCR token in the coordinate space of the selected upright image."""

    text: str
    confidence: float
    bounding_box: BBox | None
    block_id: str | None = None
    paragraph_id: str | None = None
    line_id: str | None = None
    source_pass: str | None = None


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    bounding_box: BBox | None
    tokens: tuple[OcrToken, ...] = ()
    block_id: str | None = None
    line_id: str | None = None
    source_pass: str | None = None


@dataclass(frozen=True)
class FieldEvidence:
    value: str | None
    confidence: float
    bounding_box: BBox | None


FIELD_NAMES = (
    "common_or_generic_name",
    "manufacturer_name",
    "manufacturer_address",
    "packer_name",
    "packer_address",
    "importer_name",
    "importer_address",
    "marketer_name",
    "marketer_address",
    "net_quantity",
    "mrp",
    "date_of_manufacture",
    "consumer_care_contact",
    "country_of_origin",
)

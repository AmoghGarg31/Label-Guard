"""Layout-independent, deterministic extraction from OCR text and geometry.

The extractor deliberately separates OCR confidence from field confidence. It
discovers anchors and datatype candidates across the complete image, validates
the candidates, and associates them through a dynamic row/column/block graph.
No label brand, absolute position, or OCR list order participates in a decision.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from statistics import median
from typing import Any, Iterable

from models import BBox, FIELD_NAMES, FieldEvidence, OcrLine


MONTH = r"(?:JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
DATE_VALUE_RE = re.compile(
    rf"(?<![A-Z0-9])(?:"
    rf"[0-3]?\d[./-][01]?\d[./-](?:19|20)?\d{{2}}|"
    rf"(?:19|20)\d{{2}}[./-][01]?\d[./-][0-3]?\d|"
    rf"[01]?\d[./-](?:19|20)\d{{2}}|"
    rf"[0-3]?\d\s+{MONTH}\s+(?:19|20)\d{{2}}|"
    rf"{MONTH}\s+(?:19|20)\d{{2}}"
    rf")(?![A-Z0-9])",
    re.I,
)
CURRENCY_NUMBER_RE = re.compile(
    r"(?<![A-Z0-9])(?P<currency>₹|RS\.?|INR)?\s*(?P<number>[0-9][0-9,]*(?:\.[0-9]{1,2})?)(?:\s*/-)?(?![A-Z0-9])",
    re.I,
)
NET_VALUE_RE = re.compile(
    r"(?<![A-Z0-9])(?P<number>[0-9]+(?:[.,][0-9]+)?)[\s¢|:;₹-]{0,3}"
    r"(?P<unit>KG|GMS?|GM|MG|G|ML|CL|L|UNITS?|PCS?|PIECES?)(?![A-Z])",
    re.I,
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
WEB_RE = re.compile(r"\b(?:HTTPS?://)?WWW\.[A-Z0-9-]+(?:\.[A-Z0-9-]+)+(?::\d+)?(?:/[^\s,;]*)?", re.I)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+91[\s-]*)?(?:1800[\s-]*\d{3}[\s-]*\d{3,4}|\d{5}[\s-]*\d{5}|\d{3,5}[\s-]*\d{6,8}|\d{10,11})(?!\d)"
)

NUTRITION_RE = re.compile(
    r"\b(?:NUTRITION(?:AL)?|SERVING\s*SIZE|SERVINGS?\s+PER|ENERGY|CALORIES?|PROTEIN|"
    r"CARBOHYDRATE|TOTAL\s+(?:FAT|SUGARS?)|ADDED\s+SUGARS?|TRANS\s+FAT|SATURATED\s+FAT|"
    r"CHOLESTEROL|SODIUM|POTASSIUM|DIETARY\s+FIBER|APPROXIMATE\s+VALUES?)\b",
    re.I,
)
PER_SERVING_RE = re.compile(
    r"\b(?:QUANTITY\s+)?PER\s+(?:100\s*)?(?:G|GM|KG|ML|L|SERVING)\b|"
    r"\bPER\s+SERVING\b",
    re.I,
)
MULTIPACK_COMPONENT_RE = re.compile(
    r"\b[0-9]+\s*(?:UNITS?|PCS?|PIECES?)\s*[X×]\s*[0-9]+(?:[.,][0-9]+)?\s*"
    r"(?:KG|GMS?|GM|MG|G|ML|CL|L)\b",
    re.I,
)
UNIT_PRICE_RE = re.compile(
    r"\b(?:UNIT\s+SALE\s+PRICE|USP)\b|"
    r"\bPER\s*(?:[0-9]+(?:[.,][0-9]+)?\s*)?(?:G|GM|KG|ML|L|UNIT|PIECE|PC|[A-Z0-9])\b|"
    r"/\s*(?:[0-9]+(?:[.,][0-9]+)?\s*)?(?:G|GM|KG|ML|L|UNIT|PIECE|PC)\b",
    re.I,
)
LICENSE_RE = re.compile(
    r"\b(?:FSSAI|LIC(?:ENCE|ENSE)?\s*(?:NO|NUMBER)?|GSTIN?|BAR\s*CODE|BARCODE|BATCH|LOT\s*(?:NO|NUMBER)?)\b",
    re.I,
)
EXPIRY_RE = re.compile(r"\b(?:BEST\s+BEFORE|USE\s+BY|EXP(?:IRY|IRES?|\.)?|SELL\s+BY)\b", re.I)
ADDRESS_RE = re.compile(
    r"\b(?:PLOT|ROAD|RD\.?|STREET|ST\.?|LANE|SECTOR|ESTATE|INDUSTRIAL|VILLAGE|TALUK|"
    r"DISTRICT|DIST\.?|NAGAR|MUMBAI|DELHI|PUNE|BENGALURU|BANGALORE|CHENNAI|KOLKATA|"
    r"MAHARASHTRA|KARNATAKA|GUJARAT|RAJASTHAN|HARYANA|PUNJAB|KERALA|TAMIL\s+NADU|"
    r"MADHYA\s+PRADESH|UTTAR\s+PRADESH|WEST\s+BENGAL|TELANGANA|ANDHRA\s+PRADESH|INDIA|PIN(?:CODE)?|P\.O\.)\b",
    re.I,
)
COMPANY_RE = re.compile(
    r"\b(?:PVT\.?|PRIVATE|LTD\.?|LIMITED|LLP|INC\.?|CORP(?:ORATION)?|COMPANY|CO\.?|"
    r"INDUSTRIES|FOODS?|ENTERPRISES?|VENTURES?|TRADERS?|PRODUCTS?)\b",
    re.I,
)
FACILITY_RE = re.compile(
    r"\b(?:FACILITY|SHARED\s+EQUIPMENT|MAY\s+CONTAIN|ALLERGEN|CROSS\s*CONTAMINATION)\b",
    re.I,
)
CONTACT_INSTRUCTION_RE = re.compile(
    r"\b(?:ADDRESS|CALL|EMAIL|PHONE|CONTACT|WEBSITE|WRITE|REACH|QUERY|QUERIES|"
    r"FEEDBACK|COMPLAINTS?|CONSUMER|CUSTOMER)\b",
    re.I,
)


ANCHOR_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "mrp": (
        re.compile(r"\bM\s*\.?\s*R\s*\.?\s*P\s*\.?\b", re.I),
        re.compile(r"\bMAX(?:IMUM)?\s+RETAIL\s+PRICE\b", re.I),
        re.compile(r"\bRETAIL\s+SALE\s+PRICE\b", re.I),
        re.compile(r"\bW\s*\.?\s*R\s*\.?\s*P\s*\.?\b", re.I),
    ),
    "net_quantity": (
        re.compile(r"\bNET\s*(?:WT|WEIGHT|QUANTITY|QTY)\s*\.?\b", re.I),
        re.compile(r"\bNET\s+CONTENTS?\b", re.I),
        re.compile(r"\b(?:QUANTITY|QTY)\s*\.?(?!\s+PER\b)\b", re.I),
    ),
    "date_of_manufacture": (
        re.compile(r"\b(?:MFD|MFG|DOM|PKD|PKG)\s*\.?\b", re.I),
        re.compile(r"\bDATE\s+OF\s+(?:MANUFACTURE|MANUFACTURING|MFG|PACKING|PACKAGING|PKG)\b", re.I),
        re.compile(r"\b(?:MANUFACTURED|PACKED|PACKAGED)\s+(?:ON|DATE)\b", re.I),
        re.compile(r"\b(?:PACKING\s+DATE|PRE[\s-]*PACKED)\b", re.I),
    ),
    "common_or_generic_name": (
        re.compile(r"\bCOMMON\s+(?:(?:OR\s+)?GENERIC\s+)?NAME\b", re.I),
        re.compile(r"\bGENERIC\s+NAME\b", re.I),
        re.compile(r"\bNAME\s+OF\s+(?:THE\s+)?COMMODITY\b", re.I),
        re.compile(r"\b(?:PRODUCT\s+NAME|COMMODITY|CONTENTS?)\b", re.I),
    ),
    "country_of_origin": (
        re.compile(r"\bCOUNTRY\s+OF\s+ORIGIN\b", re.I),
        re.compile(r"\b(?:MADE\s+IN|PRODUCT\s+OF)\b", re.I),
    ),
    "consumer_care_contact": (
        re.compile(r"\b(?:CONSUMER|CUSTOMER)\s+(?:CARE|SERVICE|SUPPORT|COMPLAINTS?)\b", re.I),
        re.compile(r"\b(?:FEEDBACK|QUERIES|HELPLINE|TOLL\s*FREE|CONTACT(?:\s+US)?|CALL\s+US|WRITE\s+TO|REACH\s+US|EMAIL(?:\s+US)?|PHONE|WEBSITE|WEB)\b", re.I),
    ),
    "manufacturer": (
        re.compile(r"\b(?:MANUFACTURED|MFD|MFG|PRODUCED)\s*(?:(?:&|AND)\s*(?:PACKED|MARKETED)\s*)?(?:BY|FOR)\b", re.I),
        re.compile(r"\bT?URED\s*(?:(?:&|AND)\s*(?:PACKED|MARKETED)\s*)?BY\b", re.I),
    ),
    "packer": (
        re.compile(r"\b(?:PACKED|PKD)\s*(?:(?:&|AND)\s*MARKETED\s*)?BY\b", re.I),
        re.compile(r"\bPACKER\b", re.I),
    ),
    "importer": (
        re.compile(r"\bIMPORTED\s+BY\b", re.I),
        re.compile(r"\bIMPORTER\b", re.I),
    ),
    "marketer": (
        re.compile(r"\b(?:MARKETED|MKTD)\s+BY\b", re.I),
        re.compile(r"\bBRAND\s+OWNER\b", re.I),
    ),
}

ANCHOR_PHRASES: dict[str, tuple[str, ...]] = {
    "mrp": ("mrp", "maximum retail price", "retail sale price", "wrp"),
    "net_quantity": ("net weight", "net quantity", "net wt", "net contents", "quantity"),
    "date_of_manufacture": ("date of manufacture", "date of packing", "packing date", "manufactured on", "packed on", "pre packed"),
    "common_or_generic_name": ("common name", "generic name", "name of commodity", "product name"),
    "country_of_origin": ("country of origin", "made in", "product of"),
    "consumer_care_contact": ("consumer care", "customer care", "consumer complaints", "contact us"),
    "manufacturer": ("manufactured by", "manufactured for", "produced by"),
    "packer": ("packed by", "packer"),
    "importer": ("imported by", "importer"),
    "marketer": ("marketed by", "brand owner"),
}

ALL_DECLARATIONS_RE = re.compile(
    r"\b(?:M\s*\.?\s*R\s*\.?\s*P\s*\.?|NET\s*(?:WT|WEIGHT|QUANTITY)|MFD|MFG|DOM|PKD|"
    r"DATE\s+OF|CONSUMER\s+CARE|CUSTOMER\s+CARE|COUNTRY\s+OF\s+ORIGIN|MADE\s+IN|"
    r"MANUFACTURED\s+BY|PACKED\s+BY|IMPORTED\s+BY|MARKETED\s+BY|COMMON\s+NAME)\b",
    re.I,
)

COUNTRIES = {
    "afghanistan", "argentina", "australia", "austria", "bangladesh", "belgium", "bhutan",
    "brazil", "canada", "chile", "china", "colombia", "denmark", "egypt", "finland", "france",
    "germany", "greece", "hong kong", "india", "indonesia", "ireland", "israel", "italy", "japan",
    "kenya", "malaysia", "mexico", "myanmar", "nepal", "netherlands", "new zealand", "nigeria",
    "norway", "pakistan", "philippines", "poland", "portugal", "russia", "saudi arabia", "singapore",
    "south africa", "south korea", "spain", "sri lanka", "sweden", "switzerland", "taiwan", "thailand",
    "turkey", "uae", "united arab emirates", "uk", "united kingdom", "usa", "united states",
    "united states of america", "vietnam",
}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _union_boxes(boxes: Iterable[BBox | None]) -> BBox | None:
    valid = [box for box in boxes if box is not None]
    if not valid:
        return None
    return (
        min(box[0] for box in valid),
        min(box[1] for box in valid),
        max(box[2] for box in valid),
        max(box[3] for box in valid),
    )


def compute_precise_bbox(line_text: str | None, bbox: BBox | None, match_span: tuple[int, int] | None) -> BBox | None:
    """Approximate a token span when word-level boxes are not available."""
    if not bbox or not line_text or not match_span:
        return bbox
    left, top, right, bottom = bbox
    width = right - left
    start = max(0.0, match_span[0] / len(line_text))
    end = min(1.0, match_span[1] / len(line_text))
    return (max(left, left + int(start * width) - 4), top, min(right, left + int(end * width) + 4), bottom)


def _span_bbox(line: OcrLine, span: tuple[int, int]) -> BBox | None:
    """Use OCR word boxes for evidence, with a deterministic line fallback."""
    if not line.tokens:
        return compute_precise_bbox(line.text, line.bounding_box, span)
    cursor = 0
    selected: list[BBox | None] = []
    for token in line.tokens:
        start = line.text.find(token.text, cursor)
        if start < 0:
            start = cursor
        end = start + len(token.text)
        cursor = end
        if end > span[0] and start < span[1]:
            selected.append(token.bounding_box)
    return _union_boxes(selected) or compute_precise_bbox(line.text, line.bounding_box, span)


def _span_confidence(line: OcrLine, span: tuple[int, int]) -> float:
    """Use the OCR confidence of matched words, not unrelated words in a merged line."""

    if not line.tokens:
        return max(0.0, min(float(line.confidence), 1.0))
    cursor = 0
    selected: list[float] = []
    for token in line.tokens:
        start = line.text.find(token.text, cursor)
        if start < 0:
            start = cursor
        end = start + len(token.text)
        cursor = end
        if end > span[0] and start < span[1]:
            selected.append(max(0.0, min(float(token.confidence), 1.0)))
    if not selected:
        return max(0.0, min(float(line.confidence), 1.0))
    return sum(selected) / len(selected)


@dataclass
class _Node:
    index: int
    line: OcrLine
    row: int = -1
    column: int = -1
    block: str = ""

    @property
    def text(self) -> str:
        return self.line.text

    @property
    def box(self) -> BBox | None:
        return self.line.bounding_box

    @property
    def center(self) -> tuple[float, float]:
        if not self.box:
            return (0.0, 0.0)
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)


@dataclass
class _Layout:
    nodes: list[_Node]
    median_height: float
    width: float
    height: float
    diagonal: float


def _build_layout(lines: list[OcrLine]) -> _Layout:
    nodes = [_Node(index, line) for index, line in enumerate(lines) if normalize_text(line.text)]
    boxes = [node.box for node in nodes if node.box]
    heights = [max(1, box[3] - box[1]) for box in boxes]
    med_h = float(median(heights)) if heights else 20.0
    min_x = min((box[0] for box in boxes), default=0)
    min_y = min((box[1] for box in boxes), default=0)
    max_x = max((box[2] for box in boxes), default=1)
    max_y = max((box[3] for box in boxes), default=1)
    width = float(max(1, max_x - min_x))
    height = float(max(1, max_y - min_y))

    row_centres: list[float] = []
    for node in sorted(nodes, key=lambda item: (item.center[1], item.center[0], item.index)):
        if not node.box:
            continue
        cy = node.center[1]
        eligible = [(abs(cy - centre), idx) for idx, centre in enumerate(row_centres)]
        if eligible and min(eligible)[0] <= max(med_h * 0.8, (node.box[3] - node.box[1]) * 0.65):
            _, node.row = min(eligible)
            row_centres[node.row] = (row_centres[node.row] + cy) / 2
        else:
            node.row = len(row_centres)
            row_centres.append(cy)

    centres = sorted({round(node.center[0], 2) for node in nodes if node.box})
    split_threshold = max(med_h * 5.0, width * 0.16)
    boundaries = [(left + right) / 2 for left, right in zip(centres, centres[1:]) if right - left > split_threshold]
    for node in nodes:
        if node.box:
            node.column = sum(node.center[0] > boundary for boundary in boundaries)
        if node.line.block_id:
            node.block = node.line.block_id
        else:
            vertical_band = int((node.center[1] - min_y) // max(med_h * 5.0, 1.0)) if node.box else -1
            node.block = f"dynamic:{node.column}:{vertical_band}"

    return _Layout(nodes, med_h, width, height, math.hypot(width, height))


@dataclass(frozen=True)
class _Anchor:
    family: str
    node_index: int
    span: tuple[int, int]
    quality: float


@dataclass(frozen=True)
class _Candidate:
    value: str
    node_index: int
    span: tuple[int, int]
    datatype: float = 1.0
    context: float = 1.0
    requires_anchor: bool = False
    support: tuple[tuple[int, tuple[int, int]], ...] = ()


@dataclass(frozen=True)
class _Ranked:
    candidate: _Candidate
    anchor: _Anchor | None
    score: float
    confidence: float
    relation: str
    distance: float


@dataclass(frozen=True)
class TargetedOcrRequest:
    """A bounded OCR retry around an unresolved, semantically strong anchor."""

    field: str
    bounding_box: BBox
    psms: tuple[int, ...] = (6, 11)


def _fuzzy_anchor(text: str, phrases: tuple[str, ...]) -> tuple[tuple[int, int], float] | None:
    words = [(match.group(0).lower(), match.span()) for match in re.finditer(r"[A-Z0-9]+", text, re.I)]
    best: tuple[tuple[int, int], float] | None = None
    for phrase in phrases:
        expected = phrase.split()
        for size in {max(1, len(expected) - 1), len(expected), len(expected) + 1}:
            for start in range(0, len(words) - size + 1):
                chunk = " ".join(word for word, _ in words[start : start + size])
                quality = SequenceMatcher(None, chunk, phrase).ratio()
                if quality < 0.88:
                    continue
                span = (words[start][1][0], words[start + size - 1][1][1])
                if best is None or quality > best[1]:
                    best = (span, quality)
    return best


def _anchors(layout: _Layout, family: str) -> list[_Anchor]:
    result: list[_Anchor] = []
    for node in layout.nodes:
        if family == "net_quantity" and PER_SERVING_RE.search(node.text) and not re.search(
            r"\bNET\s*(?:WT|WEIGHT|QUANTITY|QTY|CONTENTS?)\b", node.text, re.I
        ):
            continue
        exact = [match for pattern in ANCHOR_PATTERNS[family] for match in pattern.finditer(node.text)]
        if exact:
            best = max(exact, key=lambda match: len(match.group(0)))
            if family in {"manufacturer", "packer", "importer", "marketer"}:
                trailing = node.text[best.end() :].lstrip(" \t:;=-–—|,")
                if trailing and CONTACT_INSTRUCTION_RE.match(trailing):
                    continue
            result.append(_Anchor(family, node.index, best.span(), 1.0))
            continue
        fuzzy = _fuzzy_anchor(node.text, ANCHOR_PHRASES[family])
        if fuzzy:
            # Similar role phrases are not interchangeable: an exact marketer,
            # packer, or importer declaration must never become manufacturer.
            if family == "manufacturer" and re.search(r"\b(?:MARKETED|PACKED|IMPORTED)\s+BY\b", node.text, re.I):
                continue
            if family == "manufacturer" and not re.search(r"\b(?:BY|FOR)\b", node.text[fuzzy[0][0]:fuzzy[0][1]], re.I):
                continue
            result.append(_Anchor(family, node.index, fuzzy[0], round(fuzzy[1], 3)))
    return result


def _node(layout: _Layout, index: int) -> _Node:
    return next(node for node in layout.nodes if node.index == index)


def _relation(layout: _Layout, anchor: _Anchor, candidate: _Candidate) -> tuple[float, str, float, float]:
    a_node = _node(layout, anchor.node_index)
    c_node = _node(layout, candidate.node_index)
    if a_node.index == c_node.index:
        gap = max(0, max(anchor.span[0], candidate.span[0]) - min(anchor.span[1], candidate.span[1]))
        return max(0.90, 1.0 - gap / max(1, len(a_node.text)) * 0.18), "same_line", float(gap), 0.0
    if not a_node.box or not c_node.box:
        return 0.0, "no_geometry", float("inf"), 0.35
    ax, ay = a_node.center
    cx, cy = c_node.center
    distance = math.hypot(cx - ax, cy - ay)
    normalized = distance / max(layout.diagonal, 1.0)
    penalty = 0.0
    if a_node.row >= 0 and a_node.row == c_node.row:
        relation = "same_row"
        relation_score = max(0.68, 0.96 - normalized * 0.65)
    elif a_node.column >= 0 and a_node.column == c_node.column:
        relation = "same_column"
        relation_score = max(0.60, 0.88 - normalized * 0.75)
    elif a_node.block == c_node.block:
        relation = "same_block"
        relation_score = max(0.54, 0.78 - normalized * 0.7)
    else:
        relation = "nearby"
        relation_score = max(0.18, 0.62 - normalized * 0.8)
        if a_node.column != c_node.column:
            penalty += 0.10
    return relation_score, relation, distance, penalty


def _field_confidence(score: float, candidate: _Candidate, line: OcrLine) -> float:
    ocr = _span_confidence(line, candidate.span)
    calibrated = max(0.0, min(0.60 * score + 0.24 * ocr + 0.16 * candidate.datatype, 0.99))
    if abs(calibrated - ocr) < 0.0005:
        calibrated = max(0.0, calibrated - 0.001)
    return round(calibrated, 3)


def _rank(layout: _Layout, family: str, candidates: list[_Candidate], *, require_anchor: bool, allow_anchorless: bool = False) -> list[_Ranked]:
    anchors = _anchors(layout, family)
    ranked: list[_Ranked] = []
    for candidate in candidates:
        line = _node(layout, candidate.node_index).line
        options: list[_Ranked] = []
        for anchor in anchors:
            if family == "net_quantity":
                anchor_text = _node(layout, anchor.node_index).text
                candidate_unit = candidate.value.rsplit(" ", 1)[-1].lower()
                anchor_fragment = re.sub(r"[^a-z]", "", anchor_text[anchor.span[0] : anchor.span[1]].lower())
                weight_semantics = bool(
                    re.search(r"\bNET\s*(?:WT|WEIGHT)\b", anchor_text, re.I)
                    or SequenceMatcher(None, anchor_fragment, "netweight").ratio() >= 0.76
                    or SequenceMatcher(None, anchor_fragment, "netwt").ratio() >= 0.80
                )
                if weight_semantics and candidate_unit in {
                    "unit", "units", "pc", "pcs", "piece", "pieces"
                }:
                    continue
            relation_score, relation, distance, penalty = _relation(layout, anchor, candidate)
            if relation_score <= 0:
                continue
            if family in {"mrp", "net_quantity", "date_of_manufacture"}:
                if relation == "nearby":
                    continue
                if relation == "same_row" and distance > max(
                    layout.median_height * 14.0, layout.width * 0.35
                ):
                    continue
                if relation in {"same_column", "same_block"} and distance > max(
                    layout.median_height * 10.0, layout.height * 0.15
                ):
                    continue
            if family == "consumer_care_contact" and candidate.requires_anchor:
                if relation == "nearby" or distance > max(
                    layout.median_height * 12.0, layout.diagonal * 0.12
                ):
                    continue
            if (
                family == "mrp"
                and candidate.datatype < 1.0
                and relation != "same_line"
                and "." not in candidate.value
            ):
                continue
            anchor_line = _node(layout, anchor.node_index).line
            candidate_ocr = _span_confidence(line, candidate.span)
            score = round(max(0.0, min(
                0.28 * anchor.quality + 0.27 * candidate.datatype
                + 0.09 * candidate_ocr
                + 0.05 * max(0.0, min(anchor_line.confidence, 1.0))
                + 0.23 * relation_score + 0.08 * candidate.context - penalty,
                1.0,
            )), 4)
            options.append(_Ranked(candidate, anchor, score, _field_confidence(score, candidate, line), relation, distance))
        if options:
            ranked.append(max(options, key=lambda item: (item.score, -item.distance, item.anchor.quality if item.anchor else 0)))
        elif allow_anchorless and not require_anchor and not candidate.requires_anchor:
            score = round(0.45 * candidate.datatype + 0.28 * line.confidence + 0.27 * candidate.context, 4)
            if score >= 0.82:
                ranked.append(_Ranked(candidate, None, score, _field_confidence(score, candidate, line), "global_datatype", 0.0))
    return sorted(ranked, key=lambda item: (
        -item.score,
        item.distance,
        (_node(layout, item.candidate.node_index).box or (0, 0, 0, 0))[1],
        (_node(layout, item.candidate.node_index).box or (0, 0, 0, 0))[0],
        item.candidate.value,
    ))


def _normalized_rank_value(family: str, value: str) -> str:
    if family == "mrp":
        numeric = re.sub(r"[^0-9.]", "", value)
        try:
            return f"{float(numeric):.2f}"
        except ValueError:
            pass
    return re.sub(r"\s+", " ", value.strip().lower())


def _nearby_boxes(layout: _Layout, left: BBox | None, right: BBox | None) -> bool:
    if left is None or right is None:
        return False
    lx, ly = ((left[0] + left[2]) / 2, (left[1] + left[3]) / 2)
    rx, ry = ((right[0] + right[2]) / 2, (right[1] + right[3]) / 2)
    overlaps = min(left[2], right[2]) > max(left[0], right[0]) and min(left[3], right[3]) > max(
        left[1], right[1]
    )
    return overlaps or math.hypot(lx - rx, ly - ry) <= max(
        layout.median_height * 1.8, layout.diagonal * 0.015
    )


def _apply_agreement(layout: _Layout, family: str, ranked: list[_Ranked]) -> list[_Ranked]:
    """Calibrate ranked evidence with localized OCR-pass agreement and disagreement."""

    calibrated: list[_Ranked] = []
    for item in ranked:
        item_node = _node(layout, item.candidate.node_index)
        item_box = _span_bbox(item_node.line, item.candidate.span)
        normalized = _normalized_rank_value(family, item.candidate.value)
        agreeing_passes = {
            _node(layout, other.candidate.node_index).line.source_pass
            for other in ranked
            if _normalized_rank_value(family, other.candidate.value) == normalized
            and _nearby_boxes(
                layout,
                item_box,
                _span_bbox(_node(layout, other.candidate.node_index).line, other.candidate.span),
            )
            and _node(layout, other.candidate.node_index).line.source_pass
        }
        conflicting_passes = {
            _node(layout, other.candidate.node_index).line.source_pass
            for other in ranked
            if _normalized_rank_value(family, other.candidate.value) != normalized
            and other.score >= item.score - 0.07
            and _nearby_boxes(
                layout,
                item_box,
                _span_bbox(_node(layout, other.candidate.node_index).line, other.candidate.span),
            )
            and _node(layout, other.candidate.node_index).line.source_pass
        }
        agreement_bonus = min(0.05, max(0, len(agreeing_passes) - 1) * 0.025)
        disagreement_penalty = min(0.12, len(conflicting_passes) * 0.06)
        score = round(max(0.0, min(1.0, item.score + agreement_bonus - disagreement_penalty)), 4)
        confidence = round(max(0.0, min(0.99, item.confidence + agreement_bonus - disagreement_penalty)), 3)
        calibrated.append(
            _Ranked(item.candidate, item.anchor, score, confidence, item.relation, item.distance)
        )
    return sorted(calibrated, key=lambda item: (-item.score, item.distance, item.candidate.value))


def _select_ranked(layout: _Layout, family: str, ranked: list[_Ranked]) -> _Ranked | None:
    if not ranked:
        return None
    # Resolve direct OCR disagreement before applying penalties. Otherwise two
    # conflicting readings can both be demoted below an unrelated third value.
    raw_top = ranked[0]
    raw_top_node = _node(layout, raw_top.candidate.node_index)
    raw_top_box = _span_bbox(raw_top_node.line, raw_top.candidate.span)
    raw_top_value = _normalized_rank_value(family, raw_top.candidate.value)

    def pass_support(value: str, box: BBox | None) -> set[str]:
        return {
            source
            for item in ranked
            if _normalized_rank_value(family, item.candidate.value) == value
            and _nearby_boxes(
                layout,
                box,
                _span_bbox(_node(layout, item.candidate.node_index).line, item.candidate.span),
            )
            if (source := _node(layout, item.candidate.node_index).line.source_pass)
        }

    raw_top_support = pass_support(raw_top_value, raw_top_box)
    for other in ranked[1:]:
        if _normalized_rank_value(family, other.candidate.value) == raw_top_value:
            continue
        other_node = _node(layout, other.candidate.node_index)
        other_box = _span_bbox(other_node.line, other.candidate.span)
        if other.score >= raw_top.score - 0.055 and _nearby_boxes(layout, raw_top_box, other_box):
            other_support = pass_support(
                _normalized_rank_value(family, other.candidate.value), other_box
            )
            if len(raw_top_support) == len(other_support):
                return None
    calibrated = _apply_agreement(layout, family, ranked)
    top = calibrated[0]
    top_node = _node(layout, top.candidate.node_index)
    top_box = _span_bbox(top_node.line, top.candidate.span)
    top_value = _normalized_rank_value(family, top.candidate.value)

    for other in calibrated[1:]:
        if _normalized_rank_value(family, other.candidate.value) == top_value:
            continue
        other_node = _node(layout, other.candidate.node_index)
        if other.score >= top.score - 0.055 and _nearby_boxes(
            layout, top_box, _span_bbox(other_node.line, other.candidate.span)
        ):
            return None

    # A low-quality value emitted by just one real OCR pass is unresolved. It
    # may be retried locally, but it must not become a confident statutory fact.
    if family in {"mrp", "net_quantity", "date_of_manufacture"} and top_node.line.source_pass:
        confirming_passes = {
            _node(layout, item.candidate.node_index).line.source_pass
            for item in calibrated
            if _normalized_rank_value(family, item.candidate.value) == top_value
            and _nearby_boxes(
                layout,
                top_box,
                _span_bbox(_node(layout, item.candidate.node_index).line, item.candidate.span),
            )
            and _node(layout, item.candidate.node_index).line.source_pass
        }
        if top_node.line.confidence < 0.78 and len(confirming_passes) < 2:
            return None
    return top


def _evidence(layout: _Layout, ranked: _Ranked | None) -> FieldEvidence:
    if ranked is None or ranked.score < 0.55:
        return FieldEvidence(None, 0.0, None)
    value_node = _node(layout, ranked.candidate.node_index)
    boxes: list[BBox | None] = [_span_bbox(value_node.line, ranked.candidate.span)]
    for support_index, support_span in ranked.candidate.support:
        support_node = _node(layout, support_index)
        boxes.append(_span_bbox(support_node.line, support_span))
    if ranked.anchor:
        anchor_node = _node(layout, ranked.anchor.node_index)
        boxes.append(_span_bbox(anchor_node.line, ranked.anchor.span))
    return FieldEvidence(ranked.candidate.value, ranked.confidence, _union_boxes(boxes))


def _malformed_same_line_evidence(
    layout: _Layout, family: str, ranked: list[_Ranked]
) -> FieldEvidence:
    """Retain an unambiguous malformed declaration for deterministic format rules.

    Valid candidates and OCR disagreements must stay on the normal ranked path.
    This fallback is deliberately limited to exact, high-confidence MRP/net
    anchors whose value is on the same line. When OCR pass provenance exists,
    at least two independent local passes must agree on the malformed text.
    """

    if ranked or family not in {"mrp", "net_quantity"}:
        return FieldEvidence(None, 0.0, None)

    candidates: list[tuple[str, _Anchor, _Node, tuple[int, int]]] = []
    for anchor in _anchors(layout, family):
        node = _node(layout, anchor.node_index)
        if anchor.quality < 0.97 or node.line.confidence < 0.78:
            continue

        raw_end = len(node.text)
        next_declaration = ALL_DECLARATIONS_RE.search(node.text, anchor.span[1])
        if next_declaration:
            raw_end = next_declaration.start()
        raw_start = anchor.span[1]
        leading = re.match(r"[\s:;=\-–—.]*", node.text[raw_start:raw_end])
        value_start = raw_start + (leading.end() if leading else 0)
        value = normalize_text(node.text[value_start:raw_end]).strip(" ,;:-–—")
        if not value or len(value) > 80 or not re.search(r"[A-Z0-9]", value, re.I):
            continue

        if family == "mrp":
            qualifier_only = re.fullmatch(
                r"\(?\s*(?:(?:INCL|INCLUSIVE)\.?\s+OF\s+)?ALL\s+TAXES\s*\)?",
                value,
                re.I,
            )
            contaminated = bool(
                qualifier_only
                or "%" in value
                or UNIT_PRICE_RE.search(value)
                or NUTRITION_RE.search(node.text)
                or PHONE_RE.search(value)
                or DATE_VALUE_RE.search(value)
                or LICENSE_RE.search(value)
                or NET_VALUE_RE.search(value)
                or MULTIPACK_COMPONENT_RE.search(value)
            )
        else:
            contaminated = bool(
                NUTRITION_RE.search(node.text)
                or PER_SERVING_RE.search(node.text)
                or UNIT_PRICE_RE.search(value)
                or MULTIPACK_COMPONENT_RE.search(value)
                or PHONE_RE.search(value)
                or DATE_VALUE_RE.search(value)
                or LICENSE_RE.search(value)
                # A bare/noisy number is commonly a recoverable OCR unit loss,
                # so keep it uncertain instead of turning it into a format FAIL.
                or re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?\s*[^A-Z0-9]*", value, re.I)
            )
        if contaminated:
            continue
        candidates.append((value, anchor, node, (anchor.span[0], raw_end)))

    if not candidates:
        return FieldEvidence(None, 0.0, None)

    groups: dict[str, list[tuple[str, _Anchor, _Node, tuple[int, int]]]] = {}
    for candidate in candidates:
        groups.setdefault(normalize_text(candidate[0]).casefold(), []).append(candidate)

    def support(group: list[tuple[str, _Anchor, _Node, tuple[int, int]]]) -> set[str]:
        return {item[2].line.source_pass for item in group if item[2].line.source_pass}

    ordered = sorted(
        groups.values(),
        key=lambda group: (
            -len(support(group)),
            -len(group),
            -max(item[2].line.confidence for item in group),
            normalize_text(group[0][0]).casefold(),
        ),
    )
    chosen = ordered[0]
    chosen_support = support(chosen)
    if chosen_support and len(chosen_support) < 2:
        return FieldEvidence(None, 0.0, None)
    if len(ordered) > 1:
        runner_up = ordered[1]
        if len(support(runner_up)) == len(chosen_support) and len(runner_up) == len(chosen):
            return FieldEvidence(None, 0.0, None)

    value, anchor, node, span = max(chosen, key=lambda item: item[2].line.confidence)
    confidence = round(min(0.95, node.line.confidence * 0.96, anchor.quality), 3)
    return FieldEvidence(value, confidence, _span_bbox(node.line, span) or node.box)


def _nearest_semantic(text: str, span: tuple[int, int]) -> str | None:
    centre = (span[0] + span[1]) / 2
    labels: list[tuple[float, str]] = []
    for pattern in ANCHOR_PATTERNS["date_of_manufacture"]:
        labels.extend((abs((m.start() + m.end()) / 2 - centre), "manufacture") for m in pattern.finditer(text))
    labels.extend((abs((m.start() + m.end()) / 2 - centre), "expiry") for m in EXPIRY_RE.finditer(text))
    return min(labels)[1] if labels else None


def _valid_date(value: str) -> bool:
    clean = normalize_text(value).upper()
    try:
        if re.fullmatch(r"(?:19|20)\d{2}[./-][01]?\d[./-][0-3]?\d", clean):
            year, month, day = re.split(r"[./-]", clean)
            datetime(int(year), int(month), int(day))
        elif re.fullmatch(r"[0-3]?\d[./-][01]?\d[./-](?:19|20)?\d{2}", clean):
            day, month, year = re.split(r"[./-]", clean)
            datetime(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day))
        elif re.fullmatch(r"[01]?\d[./-](?:19|20)\d{2}", clean):
            month, year = re.split(r"[./-]", clean)
            datetime(int(year), int(month), 1)
        elif re.fullmatch(rf"[0-3]?\d\s+{MONTH}\s+(?:19|20)\d{{2}}", clean, re.I):
            try:
                datetime.strptime(clean, "%d %b %Y")
            except ValueError:
                datetime.strptime(clean, "%d %B %Y")
        elif re.fullmatch(rf"{MONTH}\s+(?:19|20)\d{{2}}", clean, re.I):
            try:
                datetime.strptime(clean, "%b %Y")
            except ValueError:
                datetime.strptime(clean, "%B %Y")
        else:
            return False
    except ValueError:
        return False
    return True


def _date_candidates(layout: _Layout) -> list[_Candidate]:
    result: list[_Candidate] = []
    manufacture_anchors = _anchors(layout, "date_of_manufacture")

    def box_distance(left: BBox, right: BBox) -> float:
        lcx = (left[0] + left[2]) / 2
        lcy = (left[1] + left[3]) / 2
        rcx = (right[0] + right[2]) / 2
        rcy = (right[1] + right[3]) / 2
        overlap_x = max(0, min(left[2], right[2]) - max(left[0], right[0]))
        overlap_y = max(0, min(left[3], right[3]) - max(left[1], right[1]))
        min_width = max(1, min(left[2] - left[0], right[2] - right[0]))
        min_height = max(1, min(left[3] - left[1], right[3] - right[1]))
        # Curved labels commonly give neighboring words slightly staggered
        # token boxes. A small real overlap still means the declaration is on
        # the same visual row/column.
        axis_aligned = overlap_x / min_width >= 0.15 or overlap_y / min_height >= 0.15
        distance = math.hypot(lcx - rcx, lcy - rcy)
        return distance * (0.45 if axis_aligned else 1.0)

    def semantic_distance(node: _Node, span: tuple[int, int], *, expiry: bool) -> float:
        candidate_box = _span_bbox(node.line, span)
        if not candidate_box:
            return float("inf")
        distances: list[float] = []
        if expiry:
            semantic_nodes = [
                (other, match.span())
                for other in layout.nodes
                for match in EXPIRY_RE.finditer(other.text)
            ]
        else:
            semantic_nodes = [
                (_node(layout, anchor.node_index), anchor.span)
                for anchor in manufacture_anchors
            ]
        has_same_pass_semantic = bool(
            node.line.source_pass
            and any(
                semantic_node.line.source_pass == node.line.source_pass
                for semantic_node, _ in semantic_nodes
            )
        )
        for semantic_node, semantic_span in semantic_nodes:
            if (
                has_same_pass_semantic
                and semantic_node.line.source_pass != node.line.source_pass
            ):
                continue
            semantic_box = _span_bbox(semantic_node.line, semantic_span)
            if not semantic_box:
                continue
            distance = box_distance(candidate_box, semantic_box)
            if distance <= max(layout.median_height * 12.0, layout.diagonal * 0.12):
                distances.append(distance)
        return min(distances, default=float("inf"))

    for node in layout.nodes:
        for match in DATE_VALUE_RE.finditer(node.text):
            value = normalize_text(match.group(0))
            if not _valid_date(value):
                continue
            semantic = _nearest_semantic(node.text, match.span())
            if semantic == "expiry":
                continue
            manufacture_distance = semantic_distance(node, match.span(), expiry=False)
            expiry_distance = semantic_distance(node, match.span(), expiry=True)
            if expiry_distance < float("inf") and expiry_distance < manufacture_distance * 0.90:
                continue
            before = node.text[: match.start()]
            if (LICENSE_RE.search(node.text) or NUTRITION_RE.search(before) or ADDRESS_RE.search(node.text)) and semantic != "manufacture":
                continue
            result.append(_Candidate(value, node.index, match.span(), 1.0, 1.0, True))

    # When OCR separates a date label and its values, an expiry date beneath
    # the manufacturing row may lack a readable expiry label in one pass. Keep
    # the value nearest each manufacturing anchor in that pass instead of
    # treating both dates as equally plausible manufacture dates.
    nearest: dict[tuple[str, int], float] = {}
    assignments: dict[int, tuple[tuple[str, int], float]] = {}
    for candidate_index, candidate in enumerate(result):
        node = _node(layout, candidate.node_index)
        options: list[tuple[float, _Anchor]] = []
        candidate_box = _span_bbox(node.line, candidate.span)
        if not candidate_box:
            continue
        has_same_pass_anchor = bool(
            node.line.source_pass
            and any(
                _node(layout, anchor.node_index).line.source_pass
                == node.line.source_pass
                for anchor in manufacture_anchors
            )
        )
        for anchor in manufacture_anchors:
            anchor_node = _node(layout, anchor.node_index)
            if (
                has_same_pass_anchor
                and anchor_node.line.source_pass != node.line.source_pass
            ):
                continue
            anchor_box = _span_bbox(anchor_node.line, anchor.span)
            if not anchor_box:
                continue
            options.append((box_distance(candidate_box, anchor_box), anchor))
        if not options:
            continue
        distance, anchor = min(options, key=lambda item: item[0])
        key = (node.line.source_pass or "unattributed", anchor.node_index)
        assignments[candidate_index] = (key, distance)
        nearest[key] = min(nearest.get(key, float("inf")), distance)
    return [
        candidate
        for index, candidate in enumerate(result)
        if index not in assignments
        or assignments[index][1] <= nearest[assignments[index][0]] * 1.15 + layout.median_height * 0.15
    ]


def _mrp_candidates(layout: _Layout) -> list[_Candidate]:
    result: list[_Candidate] = []

    def line_marks_unit_price(
        text: str,
        price_matches: list[re.Match[str]],
        price: re.Match[str],
        denominator_matches: list[re.Match[str]],
    ) -> bool:
        span = price.span()
        for denominator in denominator_matches:
            if span[0] < denominator.end() and span[1] > denominator.start():
                return True
            preceding = [candidate for candidate in price_matches if candidate.end() <= denominator.start()]
            if preceding and preceding[-1].span() == span:
                return True
            if re.search(r"\b(?:UNIT\s+SALE\s+PRICE|USP)\b", text[:span[0]], re.I):
                later_mrp = max(
                    (
                        anchor.end()
                        for pattern in ANCHOR_PATTERNS["mrp"]
                        for anchor in pattern.finditer(text[:span[0]])
                    ),
                    default=-1,
                )
                unit_anchor = max(
                    (
                        anchor.end()
                        for anchor in re.finditer(
                            r"\b(?:UNIT\s+SALE\s+PRICE|USP)\b", text[:span[0]], re.I
                        )
                    ),
                    default=-1,
                )
                if unit_anchor > later_mrp:
                    return True
        return False

    # A weak OCR pass may lose the denominator while another pass reads it.
    # Preserve the unit-price classification across overlapping pass geometry
    # when the numeric readings are equivalent within OCR decimal tolerance.
    unit_price_regions: list[tuple[float, BBox | None]] = []
    for unit_node in layout.nodes:
        unit_prices = list(CURRENCY_NUMBER_RE.finditer(unit_node.text))
        denominators = list(UNIT_PRICE_RE.finditer(unit_node.text))
        for price in unit_prices:
            if line_marks_unit_price(unit_node.text, unit_prices, price, denominators):
                try:
                    numeric = float(price.group("number").replace(",", ""))
                except ValueError:
                    continue
                unit_price_regions.append(
                    (numeric, _span_bbox(unit_node.line, price.span()))
                )

    for node in layout.nodes:
        text = node.text
        price_matches = list(CURRENCY_NUMBER_RE.finditer(text))
        denominator_matches = list(UNIT_PRICE_RE.finditer(text))
        for match in price_matches:
            span = match.span()
            nutrition = NUTRITION_RE.search(text)
            unit_price = line_marks_unit_price(
                text, price_matches, match, denominator_matches
            )
            if not unit_price:
                try:
                    candidate_number = float(match.group("number").replace(",", ""))
                except ValueError:
                    candidate_number = -1.0
                candidate_box = _span_bbox(node.line, span)
                for known_number, known_box in unit_price_regions:
                    if (
                        candidate_number >= 0
                        and abs(candidate_number - known_number)
                        <= max(0.05, known_number * 0.12)
                        and candidate_box
                        and known_box
                    ):
                        cx = (candidate_box[0] + candidate_box[2]) / 2
                        cy = (candidate_box[1] + candidate_box[3]) / 2
                        kx = (known_box[0] + known_box[2]) / 2
                        ky = (known_box[1] + known_box[3]) / 2
                        if math.hypot(cx - kx, cy - ky) <= max(
                            layout.median_height * 4.0, layout.diagonal * 0.04
                        ):
                            unit_price = True
                            break
            if unit_price or LICENSE_RE.search(text) or (nutrition and span[0] >= nutrition.start()):
                continue
            if DATE_VALUE_RE.search(text) or PHONE_RE.search(text) or re.match(r"\s*%", text[span[1]:]):
                continue
            if ADDRESS_RE.search(text) and not any(pattern.search(text) for pattern in ANCHOR_PATTERNS["mrp"]):
                continue
            currency = match.group("currency")
            if currency is None and (NET_VALUE_RE.search(text) or MULTIPACK_COMPONENT_RE.search(text)):
                continue
            digits = re.sub(r"\D", "", match.group("number").split(".")[0])
            if currency is None and len(digits) > 6:
                continue
            percent_currency_noise = bool(
                currency is None
                and any(pattern.search(text) for pattern in ANCHOR_PATTERNS["mrp"])
                and re.search(r"%\s*[:=\-–]*\s*$", text[:span[0]])
            )
            datatype = 1.0 if currency else (0.97 if percent_currency_noise else 0.92)
            result.append(_Candidate(f"₹{match.group('number')}", node.index, span, datatype, 1.0, True))
    return result


def _strong_net_match(text: str) -> re.Match[str] | None:
    return re.search(r"\bNET\s*(?:WT|WEIGHT|QUANTITY|QTY|CONTENTS?)\s*\.?\b", text, re.I)


def _net_nutrition_contaminated(layout: _Layout, node: _Node, span: tuple[int, int]) -> bool:
    """Reject nutrition quantities at line, row, block, and local-region scope."""

    text = node.text
    if any(span[0] < match.end() and span[1] > match.start() for match in MULTIPACK_COMPONENT_RE.finditer(text)):
        return True
    for per_match in PER_SERVING_RE.finditer(text):
        if span[0] <= per_match.end() + 4 and span[1] >= per_match.start() - 4:
            return True

    nutrition_matches = list(NUTRITION_RE.finditer(text))
    strong = _strong_net_match(text)
    if nutrition_matches:
        candidate_centre = (span[0] + span[1]) / 2
        nutrition_distance = min(abs((match.start() + match.end()) / 2 - candidate_centre) for match in nutrition_matches)
        strong_distance = (
            abs((strong.start() + strong.end()) / 2 - candidate_centre) if strong else float("inf")
        )
        if nutrition_distance <= strong_distance:
            return True

    if strong:
        return False
    for other in layout.nodes:
        if other.index == node.index or not NUTRITION_RE.search(other.text):
            continue
        if not node.box or not other.box:
            continue
        same_region = (
            (node.row >= 0 and node.row == other.row)
            or (node.block == other.block)
            or (node.column >= 0 and node.column == other.column)
        )
        if same_region and math.hypot(node.center[0] - other.center[0], node.center[1] - other.center[1]) <= max(
            layout.median_height * 4.0, layout.diagonal * 0.055
        ):
            return True
    return False


def _plausible_net_value(number_text: str, unit_text: str) -> bool:
    """Reject identifiers and dates before they can bind to a stray unit glyph."""

    try:
        number = float(number_text.replace(",", "."))
    except ValueError:
        return False
    if not math.isfinite(number) or number <= 0:
        return False
    unit = unit_text.casefold()
    if unit in {"kg", "l", "cl"}:
        return number <= 100_000
    return number <= 1_000_000


def _net_candidates(layout: _Layout) -> list[_Candidate]:
    result: list[_Candidate] = []
    units = {"gm": "g", "gms": "g", "unit": "unit", "units": "units", "pc": "pc", "pcs": "pcs", "piece": "piece", "pieces": "pieces"}
    for node in layout.nodes:
        for match in NET_VALUE_RE.finditer(node.text):
            if not _plausible_net_value(match.group("number"), match.group("unit")):
                continue
            if _net_nutrition_contaminated(layout, node, match.span()):
                continue
            local = node.text[max(0, match.start() - 28): min(len(node.text), match.end() + 25)]
            if UNIT_PRICE_RE.search(local) or LICENSE_RE.search(node.text):
                continue
            unit = units.get(match.group("unit").lower(), match.group("unit").lower())
            result.append(_Candidate(f"{match.group('number')} {unit}", node.index, match.span(), 1.0, 1.0, True))

    # On reflective or ribbed film, Tesseract sometimes retains the net number
    # but turns a final "g" into s/3/5 or drops it. Repair that unit only when
    # the same local OCR pass also contains an explicit multipack component
    # with a readable mass/volume unit. The quantity itself is never derived
    # from or calculated from the component declaration.
    for node in layout.nodes:
        strong = _strong_net_match(node.text)
        strong_span = strong.span() if strong else None
        if strong_span is None and re.search(r"\bNET\b", node.text, re.I):
            fuzzy = _fuzzy_anchor(
                node.text, ("net weight", "net wt", "net quantity", "net contents")
            )
            if fuzzy and fuzzy[1] >= 0.79:
                strong_span = fuzzy[0]
        if strong_span is None or not node.box:
            continue
        tail = node.text[strong_span[1] :]
        noisy = re.search(
            r"(?<!\d)(?P<number>[0-9]{1,6})(?:\s*[-'’]?\s*(?P<glyph>[S53]))?"
            r"(?=\s*(?:[.,;:'’|—-]|$))",
            tail,
            re.I,
        )
        if not noisy:
            continue
        number = noisy.group("number")
        # A trailing OCR digit may actually be the unit glyph (2705 -> 270 g).
        if not noisy.group("glyph") and len(number) >= 3 and number[-1] in {"3", "5"}:
            number = number[:-1]
        if not number:
            continue
        nearby_components: list[tuple[_Node, re.Match[str]]] = []
        for other in layout.nodes:
            if other.index == node.index or not other.box:
                continue
            if math.hypot(
                node.center[0] - other.center[0], node.center[1] - other.center[1]
            ) > max(layout.median_height * 8.0, layout.diagonal * 0.10):
                continue
            if not MULTIPACK_COMPONENT_RE.search(other.text):
                continue
            component_values = [
                match
                for match in NET_VALUE_RE.finditer(other.text)
                if match.group("unit").casefold()
                not in {"unit", "units", "pc", "pcs", "piece", "pieces"}
            ]
            if not component_values:
                continue
            nearby_components.append((other, component_values[-1]))
        has_same_pass_component = bool(
            node.line.source_pass
            and any(
                other.line.source_pass == node.line.source_pass
                for other, _ in nearby_components
            )
        )
        for other, component in nearby_components:
            if (
                has_same_pass_component
                and other.line.source_pass != node.line.source_pass
            ):
                continue
            unit = units.get(
                component.group("unit").casefold(), component.group("unit").casefold()
            )
            if not _plausible_net_value(number, unit):
                continue
            number_start = strong_span[1] + noisy.start("number")
            number_end = strong_span[1] + noisy.end("number")
            result.append(
                _Candidate(
                    f"{number} {unit}",
                    node.index,
                    (number_start, number_end),
                    0.94,
                    0.96,
                    True,
                    ((other.index, component.span()),),
                )
            )
            break

    # Sparse OCR often emits a large printed number and its unit as separate
    # tokens/lines. Join only geometrically aligned, datatype-pure fragments.
    number_nodes: list[tuple[_Node, re.Match[str]]] = []
    unit_nodes: list[tuple[_Node, re.Match[str]]] = []
    for node in layout.nodes:
        number = re.fullmatch(r"\s*([0-9]+(?:[.,][0-9]+)?)\s*", node.text)
        unit = re.fullmatch(r"\s*(KG|GMS?|GM|MG|G|ML|CL|L|UNITS?|PCS?|PIECES?)\s*", node.text, re.I)
        if number:
            number_nodes.append((node, number))
        if unit:
            unit_nodes.append((node, unit))
    for number_node, number_match in number_nodes:
        if not number_node.box:
            continue
        if _net_nutrition_contaminated(layout, number_node, number_match.span()):
            continue
        for unit_node, unit_match in unit_nodes:
            if not unit_node.box or number_node.index == unit_node.index:
                continue
            overlap = max(
                0,
                min(number_node.box[3], unit_node.box[3])
                - max(number_node.box[1], unit_node.box[1]),
            )
            min_height = max(
                1,
                min(
                    number_node.box[3] - number_node.box[1],
                    unit_node.box[3] - unit_node.box[1],
                ),
            )
            vertical_overlap = overlap / min_height >= 0.45
            gap = max(0, unit_node.box[0] - number_node.box[2], number_node.box[0] - unit_node.box[2])
            if (
                not vertical_overlap
                or gap > max(layout.median_height * 3.0, 80.0)
                or not _plausible_net_value(number_match.group(1), unit_match.group(1))
            ):
                continue
            unit = units.get(unit_match.group(1).lower(), unit_match.group(1).lower())
            result.append(
                _Candidate(
                    f"{number_match.group(1)} {unit}",
                    number_node.index,
                    number_match.span(),
                    0.98,
                    1.0,
                    True,
                    ((unit_node.index, unit_match.span()),),
                )
            )
    return result


def _trim_value(text: str, span: tuple[int, int], *, prefer_after: bool = True) -> tuple[str, tuple[int, int]] | None:
    choices: list[tuple[str, tuple[int, int]]] = []
    after_start = span[1]
    after = text[after_start:]
    next_decl = ALL_DECLARATIONS_RE.search(after)
    if next_decl:
        after = after[:next_decl.start()]
    after_raw = after.lstrip(" \t:=-–|,;")
    offset = len(after) - len(after_raw)
    after_clean = normalize_text(after_raw).strip(" ,;:-–=|")
    if after_clean:
        choices.append((after_clean, (after_start + offset, after_start + offset + len(after_clean))))
    before = text[:span[0]].rstrip(" \t:=-–|,;")
    prior = list(ALL_DECLARATIONS_RE.finditer(before))
    before_start = prior[-1].end() if prior else 0
    before_raw = before[before_start:].lstrip(" \t:=-–|,;")
    before_offset = len(before[before_start:]) - len(before_raw)
    before_clean = normalize_text(before_raw).strip(" ,;:-–=|")
    if before_clean:
        choices.append((before_clean, (before_start + before_offset, before_start + before_offset + len(before_clean))))
    if not choices:
        return None
    return choices[0] if prefer_after else choices[-1]


def _clean_before_nutrition(text: str) -> tuple[str, tuple[int, int]]:
    stop = NUTRITION_RE.search(text)
    end = stop.start() if stop else len(text)
    raw = text[:end]
    leading = len(raw) - len(raw.lstrip(" \t:=-–|,;"))
    clean = normalize_text(raw[leading:]).strip(" ,;:-–=|")
    return clean, (leading, leading + len(clean))


def _is_common_name(value: str) -> bool:
    return (
        2 <= len(value) <= 90 and bool(re.search(r"[A-Z]", value, re.I))
        and not NUTRITION_RE.search(value) and not COMPANY_RE.search(value)
        and not ADDRESS_RE.search(value) and not ALL_DECLARATIONS_RE.search(value)
        and not LICENSE_RE.search(value)
    )


def _common_candidates(layout: _Layout) -> list[_Candidate]:
    result: list[_Candidate] = []
    for anchor in _anchors(layout, "common_or_generic_name"):
        node = _node(layout, anchor.node_index)
        inline = _trim_value(node.text, anchor.span)
        if inline and _is_common_name(inline[0]):
            result.append(_Candidate(inline[0], node.index, inline[1], 0.98, 1.0, True))
    for node in layout.nodes:
        clean, span = _clean_before_nutrition(node.text)
        if _is_common_name(clean):
            result.append(_Candidate(clean, node.index, span, 0.88, 0.95, True))
    return result


def _country_value(value: str) -> str | None:
    clean = normalize_text(value).strip(" ,;:-–=|.")
    lowered = clean.lower()
    if lowered not in COUNTRIES:
        return None
    if lowered in {"usa", "uae", "uk"}:
        return clean.upper()
    return " ".join(word.capitalize() for word in clean.split())


def _explicit_country_value(value: str) -> str | None:
    """Validate an explicit origin tail without limiting it to a regional sample list."""
    known = _country_value(value)
    if known:
        return known
    clean = normalize_text(value).strip(" ,;:-–=|.")
    if not (2 <= len(clean) <= 45) or len(clean.split()) > 5 or not re.fullmatch(r"[A-Z][A-Z .'-]*", clean, re.I):
        return None
    if ADDRESS_RE.search(clean) or COMPANY_RE.search(clean) or LICENSE_RE.search(clean) or ALL_DECLARATIONS_RE.search(clean):
        return None
    return " ".join(word.capitalize() for word in clean.split())


def _country_candidates(layout: _Layout) -> list[_Candidate]:
    result: list[_Candidate] = []
    for anchor in _anchors(layout, "country_of_origin"):
        node = _node(layout, anchor.node_index)
        inline = _trim_value(node.text, anchor.span)
        if inline:
            country = _explicit_country_value(inline[0])
            if country:
                result.append(_Candidate(country, node.index, inline[1], 1.0, 1.0, True))
    for node in layout.nodes:
        country = _country_value(node.text)
        if country:
            result.append(_Candidate(country, node.index, (0, len(node.text)), 1.0, 1.0, True))
    return result


def _contact_candidates(layout: _Layout) -> list[_Candidate]:
    result: list[_Candidate] = []
    for node in layout.nodes:
        for match in EMAIL_RE.finditer(node.text):
            local = node.text[max(0, match.start() - 24) : match.end() + 24]
            if not LICENSE_RE.search(local):
                result.append(_Candidate(match.group(0).lower(), node.index, match.span(), 1.0, 1.0, False))
        for match in WEB_RE.finditer(node.text):
            local = node.text[max(0, match.start() - 24) : match.end() + 24]
            if not LICENSE_RE.search(local):
                result.append(_Candidate(match.group(0).lower().rstrip(".,;"), node.index, match.span(), 1.0, 1.0, False))
        for match in PHONE_RE.finditer(node.text):
            local = node.text[max(0, match.start() - 24) : match.end() + 24]
            if LICENSE_RE.search(local):
                continue
            digits = re.sub(r"\D", "", match.group(0))
            local_semantic = any(pattern.search(node.text) for pattern in ANCHOR_PATTERNS["consumer_care_contact"])
            international_india = match.group(0).lstrip().startswith("+91")
            if not (
                len(digits) in {10, 11}
                or (international_india and len(digits) in {12, 13})
            ):
                continue
            result.append(_Candidate(normalize_text(match.group(0)), node.index, match.span(), 1.0, 1.0, not local_semantic))
    return result


def _is_address(value: str) -> bool:
    if not value or NUTRITION_RE.search(value) or LICENSE_RE.search(value) or ALL_DECLARATIONS_RE.search(value):
        return False
    hints = len(ADDRESS_RE.findall(value))
    pin = bool(re.search(r"(?<!\d)\d{6}(?!\d)", value))
    numeric_place = bool(re.search(r"\d", value) and ("," in value or "-" in value))
    return pin or hints >= 2 or (hints >= 1 and numeric_place)


def _consumer_evidence(layout: _Layout) -> FieldEvidence:
    ranked = _rank(layout, "consumer_care_contact", _contact_candidates(layout), require_anchor=False, allow_anchorless=True)
    ranked = _apply_agreement(layout, "consumer_care_contact", ranked)
    accepted = [item for item in ranked if item.score >= 0.62 and item.confidence >= 0.84]
    if not accepted:
        addresses: list[_Candidate] = []
        for anchor in _anchors(layout, "consumer_care_contact"):
            node = _node(layout, anchor.node_index)
            inline = _trim_value(node.text, anchor.span)
            if inline and _is_address(inline[0]):
                addresses.append(_Candidate(inline[0], node.index, inline[1], 0.90, 0.95, True))
        accepted = [item for item in _rank(layout, "consumer_care_contact", addresses, require_anchor=True) if item.score >= 0.62][:1]
    if not accepted:
        return FieldEvidence(None, 0.0, None)
    direct_channels = [
        item
        for item in accepted
        if EMAIL_RE.fullmatch(item.candidate.value) or PHONE_RE.fullmatch(item.candidate.value)
    ]
    if direct_channels:
        # A domain/path is more vulnerable to OCR concatenation than a bounded
        # phone or email. Preserve web-only care declarations, but prefer direct
        # channels when both are present.
        accepted = direct_channels
    unique: list[_Ranked] = []
    seen: set[str] = set()
    primary_anchor = accepted[0].anchor.node_index if accepted[0].anchor else None
    for item in accepted:
        key = item.candidate.value.lower()
        if re.fullmatch(PHONE_RE, item.candidate.value):
            digits = re.sub(r"\D", "", item.candidate.value)
            key = f"phone:{digits[-10:]}"
        if key in seen:
            continue
        if primary_anchor is not None and item.anchor and item.anchor.node_index != primary_anchor:
            primary_node = _node(layout, primary_anchor)
            item_anchor_node = _node(layout, item.anchor.node_index)
            coherent = bool(
                primary_node.box
                and item_anchor_node.box
                and (
                    primary_node.column == item_anchor_node.column
                    or primary_node.block == item_anchor_node.block
                    or math.hypot(
                        primary_node.center[0] - item_anchor_node.center[0],
                        primary_node.center[1] - item_anchor_node.center[1],
                    )
                    <= max(layout.median_height * 6.0, layout.diagonal * 0.06)
                )
            )
            if not coherent:
                continue
        seen.add(key)
        unique.append(item)
    boxes: list[BBox | None] = []
    for item in unique:
        value_node = _node(layout, item.candidate.node_index)
        boxes.append(_span_bbox(value_node.line, item.candidate.span))
        if item.anchor:
            anchor_node = _node(layout, item.anchor.node_index)
            boxes.append(_span_bbox(anchor_node.line, item.anchor.span))
    return FieldEvidence(", ".join(item.candidate.value for item in unique), round(sum(item.confidence for item in unique) / len(unique), 3), _union_boxes(boxes))


def _is_business_name(value: str) -> bool:
    if not (2 <= len(value) <= 130) or not re.search(r"[A-Z]", value, re.I):
        return False
    if (
        FACILITY_RE.search(value)
        or NUTRITION_RE.search(value)
        or LICENSE_RE.search(value)
        or CONTACT_INSTRUCTION_RE.search(value)
    ):
        return False
    if re.search(r"\b(?:MANUFACTURED|TURED|MFD|MFG|PACKED|PKD|MARKETED|MKTD|IMPORTED|PRODUCED)\b", value, re.I):
        return False
    if DATE_VALUE_RE.search(value) or EMAIL_RE.search(value) or PHONE_RE.search(value):
        return False
    if _is_address(value) and not COMPANY_RE.search(value):
        return False
    return not ALL_DECLARATIONS_RE.fullmatch(value.strip())


def _split_business(value: str, span: tuple[int, int]) -> tuple[tuple[str, tuple[int, int]], tuple[str, tuple[int, int]] | None]:
    marker = re.search(r",?\s+(?=(?:#\s*\d+|PLOT|SURVEY|ROAD|STREET|LANE|SECTOR|INDUSTRIAL\s+ESTATE|VILLAGE|DISTRICT|[A-Z]-?\d+\b))", value, re.I)
    if not marker:
        return (value, span), None
    name = value[:marker.start()].strip(" ,")
    address = value[marker.end():].strip(" ,")
    address_start = span[0] + marker.end() + (len(value[marker.end():]) - len(value[marker.end():].lstrip(" ,")))
    return (name, (span[0], span[0] + len(name))), (address, (address_start, address_start + len(address)))


def _role_evidence(layout: _Layout, role: str) -> tuple[FieldEvidence, FieldEvidence]:
    anchors = _anchors(layout, role)
    if not anchors:
        empty = FieldEvidence(None, 0.0, None)
        return empty, empty
    names: list[_Candidate] = []
    inline_addresses: list[_Candidate] = []
    for anchor in anchors:
        node = _node(layout, anchor.node_index)
        inline = _trim_value(node.text, anchor.span)
        if inline:
            residual = re.match(r"(?i)^(?:BY|FOR)\s*:?\s*", inline[0])
            if residual:
                inline = (
                    inline[0][residual.end() :],
                    (inline[1][0] + residual.end(), inline[1][1]),
                )
            name_part, address_part = _split_business(*inline)
            if _is_business_name(name_part[0]):
                names.append(_Candidate(name_part[0], node.index, name_part[1], 0.98, 1.0, True))
            if address_part and _is_address(address_part[0]):
                inline_addresses.append(_Candidate(address_part[0], node.index, address_part[1], 0.96, 1.0, True))
    for node in layout.nodes:
        clean, span = _clean_before_nutrition(node.text)
        residual = re.match(r"(?i)^(?:BY|FOR)\s*:?\s*", clean)
        if residual:
            clean = clean[residual.end() :]
            span = (span[0] + residual.end(), span[1])
        is_anchor_text = any(pattern.search(clean) for patterns in ANCHOR_PATTERNS.values() for pattern in patterns)
        name_part, _ = _split_business(clean, span)
        if _is_business_name(name_part[0]) and not is_anchor_text:
            names.append(_Candidate(name_part[0], node.index, name_part[1], 0.90 if COMPANY_RE.search(name_part[0]) else 0.82, 0.95, True))
    ranked_names = _rank(layout, role, names, require_anchor=True)
    best_name = ranked_names[0] if ranked_names and ranked_names[0].score >= 0.58 else None
    name_evidence = _evidence(layout, best_name)
    if best_name is None:
        return name_evidence, FieldEvidence(None, 0.0, None)

    addresses = list(inline_addresses)
    for node in layout.nodes:
        clean, span = _clean_before_nutrition(node.text)
        if node.index == best_name.candidate.node_index and clean == best_name.candidate.value:
            continue
        _, split_address = _split_business(clean, span)
        address_value, address_span = split_address if split_address else (clean, span)
        if _is_address(address_value):
            addresses.append(_Candidate(address_value, node.index, address_span, 0.96, 1.0, True))
    ranked_addresses = _rank(layout, role, addresses, require_anchor=True)
    chosen: list[_Ranked] = []
    name_node = _node(layout, best_name.candidate.node_index)
    selected_anchor = best_name.anchor
    for item in ranked_addresses:
        if item.score < 0.58 or not item.anchor or not selected_anchor or item.anchor.node_index != selected_anchor.node_index:
            continue
        address_node = _node(layout, item.candidate.node_index)
        coherent = address_node.row == name_node.row or address_node.column == name_node.column or address_node.block == name_node.block
        if item.candidate.node_index == name_node.index:
            coherent = True
        if coherent:
            chosen.append(item)
        if len(chosen) >= 3:
            break
    if not chosen:
        return name_evidence, FieldEvidence(None, 0.0, None)
    chosen.sort(key=lambda item: ((_node(layout, item.candidate.node_index).box or (0, 0, 0, 0))[1], (_node(layout, item.candidate.node_index).box or (0, 0, 0, 0))[0]))
    values: list[str] = []
    boxes: list[BBox | None] = []
    for item in chosen:
        if item.candidate.value not in values:
            values.append(item.candidate.value)
        value_node = _node(layout, item.candidate.node_index)
        boxes.append(_span_bbox(value_node.line, item.candidate.span))
    anchor_node = _node(layout, selected_anchor.node_index)
    boxes.append(_span_bbox(anchor_node.line, selected_anchor.span))
    return name_evidence, FieldEvidence(", ".join(values), round(sum(item.confidence for item in chosen) / len(chosen), 3), _union_boxes(boxes))


def extract_fields(lines: list[OcrLine]) -> dict[str, FieldEvidence]:
    """Extract all active statutory fields from the entire OCR geometry graph."""
    layout = _build_layout(lines)
    manufacturer_name, manufacturer_address = _role_evidence(layout, "manufacturer")
    packer_name, packer_address = _role_evidence(layout, "packer")
    importer_name, importer_address = _role_evidence(layout, "importer")
    marketer_name, marketer_address = _role_evidence(layout, "marketer")
    mrp_ranked = _rank(layout, "mrp", _mrp_candidates(layout), require_anchor=True)
    net_ranked = _rank(layout, "net_quantity", _net_candidates(layout), require_anchor=True)
    date_ranked = _rank(layout, "date_of_manufacture", _date_candidates(layout), require_anchor=True)
    common_ranked = _rank(layout, "common_or_generic_name", _common_candidates(layout), require_anchor=True)
    country_ranked = _rank(layout, "country_of_origin", _country_candidates(layout), require_anchor=True)
    selected_net = _evidence(layout, _select_ranked(layout, "net_quantity", net_ranked))
    if selected_net.value is None:
        selected_net = _malformed_same_line_evidence(layout, "net_quantity", net_ranked)
    selected_mrp = _evidence(layout, _select_ranked(layout, "mrp", mrp_ranked))
    if selected_mrp.value is None:
        selected_mrp = _malformed_same_line_evidence(layout, "mrp", mrp_ranked)
    fields: dict[str, FieldEvidence] = {
        "common_or_generic_name": _evidence(layout, common_ranked[0] if common_ranked else None),
        "manufacturer_name": manufacturer_name,
        "manufacturer_address": manufacturer_address,
        "packer_name": packer_name,
        "packer_address": packer_address,
        "importer_name": importer_name,
        "importer_address": importer_address,
        "marketer_name": marketer_name,
        "marketer_address": marketer_address,
        "net_quantity": selected_net,
        "mrp": selected_mrp,
        "date_of_manufacture": _evidence(
            layout, _select_ranked(layout, "date_of_manufacture", date_ranked)
        ),
        "consumer_care_contact": _consumer_evidence(layout),
        "country_of_origin": _evidence(layout, country_ranked[0] if country_ranked else None),
    }
    return {field_name: fields[field_name] for field_name in FIELD_NAMES}


def targeted_ocr_requests(
    lines: list[OcrLine], fields: dict[str, FieldEvidence]
) -> list[TargetedOcrRequest]:
    """Plan bounded retries only where a strong declaration remains unresolved."""

    layout = _build_layout(lines)
    requests: list[TargetedOcrRequest] = []
    for field in ("mrp", "net_quantity", "date_of_manufacture"):
        evidence = fields.get(field, FieldEvidence(None, 0.0, None))
        if evidence.value and evidence.confidence >= 0.84:
            continue
        anchors = [anchor for anchor in _anchors(layout, field) if anchor.quality >= 0.90]
        if not anchors:
            continue
        anchor = max(
            anchors,
            key=lambda item: (
                item.quality,
                _node(layout, item.node_index).line.confidence,
                -item.node_index,
            ),
        )
        anchor_node = _node(layout, anchor.node_index)
        if not anchor_node.box:
            continue
        anchor_box = _span_bbox(anchor_node.line, anchor.span) or anchor_node.box
        centre_x = (anchor_box[0] + anchor_box[2]) / 2
        centre_y = (anchor_box[1] + anchor_box[3]) / 2
        anchor_width = max(1, anchor_box[2] - anchor_box[0])
        anchor_height = max(1, anchor_box[3] - anchor_box[1])
        # Expand around the declaration anchor itself. Dynamic row/block unions
        # can drift across duplicated OCR passes and turn a local retry into an
        # almost-full-panel retry, contaminating one field with another.
        if field == "mrp":
            horizontal_radius = int(
                max(layout.median_height * 18.0, anchor_width * 6.0, 300.0)
            )
        else:
            horizontal_radius = int(
                max(layout.median_height * 14.0, anchor_width * 3.5, 180.0)
            )
        vertical_radius = int(
            max(layout.median_height * 5.5, anchor_height * 4.0, 90.0)
        )
        requests.append(
            TargetedOcrRequest(
                field,
                (
                    max(0, int(centre_x - horizontal_radius)),
                    max(0, int(centre_y - vertical_radius)),
                    int(centre_x + horizontal_radius),
                    int(centre_y + vertical_radius),
                ),
            )
        )
    return requests


def values_only(fields: dict[str, FieldEvidence]) -> dict[str, str | None]:
    return {field_name: fields.get(field_name, FieldEvidence(None, 0.0, None)).value for field_name in FIELD_NAMES}


def format_extracted_fields(
    fields: dict[str, FieldEvidence], source: str = "ocr"
) -> dict[str, dict[str, Any]]:
    """Return the stable API shape; null values always carry zero confidence."""
    formatted: dict[str, dict[str, Any]] = {}
    for field_name in FIELD_NAMES:
        evidence = fields.get(field_name, FieldEvidence(None, 0.0, None))
        value = evidence.value or ""
        formatted[field_name] = {
            "text": value,
            "confidence": round(float(evidence.confidence), 3) if value else 0.0,
            "bounding_box": list(evidence.bounding_box) if evidence.bounding_box else None,
            "source": source,
        }
    return formatted

"""OCR adapter with PaddleOCR-first behavior and a Tesseract fallback."""

import json
import logging
import os
import re
import importlib.util
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import pytesseract
from pytesseract import Output

if os.name == "nt":
    candidate_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for candidate in candidate_paths:
        if os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            break

from image_quality import decode_image
from models import BBox, OcrLine, OcrToken


logger = logging.getLogger("labelguard.ocr")


@dataclass(frozen=True)
class OcrResult:
    lines: list[OcrLine]
    engine: str
    error: str | None = None
    orientation_degrees: int = 0
    original_width: int = 0
    original_height: int = 0

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class OCRService:
    def __init__(self) -> None:
        self.preference = os.environ.get("LABELGUARD_OCR_ENGINE", "auto").lower()
        self.requested_languages = os.environ.get("LABELGUARD_OCR_LANGUAGES", "eng+hin")
        self._paddle_attempted = False
        self._paddle: Any = None
        self._tesseract_languages: list[str] | None = None

    def capabilities(self) -> dict[str, Any]:
        try:
            available = sorted(pytesseract.get_languages(config=""))
            version = str(pytesseract.get_tesseract_version()).splitlines()[0]
            return {
                "available": True,
                "tesseract_available": True,
                "paddleocr_available": importlib.util.find_spec("paddleocr") is not None,
                "engine_preference": self.preference,
                "tesseract_version": version,
                "available_languages": available,
                "active_languages": self._active_tesseract_languages(available),
                "orientation_candidates": [0, 90, 180, 270],
            }
        except Exception as exc:
            return {
                "available": False,
                "tesseract_available": False,
                "paddleocr_available": importlib.util.find_spec("paddleocr") is not None,
                "engine_preference": self.preference,
                "error": str(exc),
                "available_languages": [],
                "active_languages": [],
                "orientation_candidates": [0, 90, 180, 270],
            }

    def _active_tesseract_languages(self, available: list[str] | None = None) -> list[str]:
        if available is None:
            if self._tesseract_languages is None:
                self._tesseract_languages = sorted(pytesseract.get_languages(config=""))
            available = self._tesseract_languages
        requested = [language.strip() for language in self.requested_languages.split("+") if language.strip()]
        active = [language for language in requested if language in available]
        if not active and "eng" in available:
            active = ["eng"]
        return active

    def _tesseract_lang_value(self) -> str | None:
        active = self._active_tesseract_languages()
        return "+".join(active) if active else None

    def extract(self, image_bytes: bytes) -> OcrResult:
        image = decode_image(image_bytes)
        if image is None:
            return OcrResult([], "none", "Image could not be decoded.")
        original_height, original_width = image.shape[:2]
        candidates: list[tuple[tuple[int, int, float], int, list[OcrLine], str, list[str]]] = []

        lines, engine, errors = self._extract_preferred(image)
        candidates.append((self._orientation_score(lines), 0, lines, engine, errors))

        # A clearly readable upright declaration panel avoids three extra OCR passes.
        if candidates[0][0][0] < 3 or candidates[0][0][1] < 40:
            for angle in (90, 180, 270):
                rotated = self.rotate_image(image, angle)
                rotated_lines, rotated_engine, rotated_errors = self._extract_preferred(rotated)
                candidates.append(
                    (
                        self._orientation_score(rotated_lines),
                        angle,
                        rotated_lines,
                        rotated_engine,
                        rotated_errors,
                    )
                )

        _, angle, best_lines, best_engine, best_errors = max(
            candidates, key=lambda candidate: candidate[0]
        )
        return OcrResult(
            lines=best_lines,
            engine=best_engine,
            error="; ".join(dict.fromkeys(best_errors)) or None,
            orientation_degrees=angle,
            original_width=original_width,
            original_height=original_height,
        )

    def _extract_preferred(self, image: np.ndarray) -> tuple[list[OcrLine], str, list[str]]:
        errors: list[str] = []
        if self.preference != "pytesseract":
            try:
                paddle_lines = self._extract_with_paddle(image)
                if paddle_lines:
                    return paddle_lines, "paddleocr", errors
            except Exception as exc:  # Optional native/model dependencies are expected to fail safely.
                errors.append(f"PaddleOCR unavailable: {exc}")
                logger.info("PaddleOCR unavailable; using pytesseract: %s", exc)
        try:
            return self._extract_with_tesseract(image), "pytesseract", errors
        except Exception as exc:
            errors.append(f"pytesseract unavailable: {exc}")
            logger.exception("All OCR engines failed")
            return [], "none", errors

    @staticmethod
    def _orientation_score(lines: list[OcrLine]) -> tuple[int, int, float]:
        """Prefer declaration anchors, then useful text volume, then OCR confidence."""

        text = "\n".join(line.text for line in lines)
        anchors = (
            r"\bmrp\b",
            r"\bnet\s*(?:wt|weight|quantity|qty)\b",
            r"\b(?:manufactured|packed|imported|marketed)\s+by\b",
            r"\b(?:mfd|dom|date\s+of\s+manufacture)\b",
            r"\b(?:consumer|customer)\s+(?:care|complaints?|service)\b",
            r"\b(?:country\s+of\s+origin|made\s+in)\b",
            r"\b(?:common|generic)\s+name\b",
        )
        anchor_hits = sum(bool(re.search(pattern, text, re.I)) for pattern in anchors)
        useful_chars = min(500, sum(character.isalnum() for character in text))
        average_confidence = (
            sum(max(0.0, min(line.confidence, 1.0)) for line in lines) / len(lines)
            if lines
            else 0.0
        )
        return anchor_hits, useful_chars, round(average_confidence, 4)

    @staticmethod
    def rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
        normalized = angle % 360
        if normalized == 0:
            return image
        if normalized == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        if normalized == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        if normalized == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        raise ValueError("Only right-angle rotations are supported.")

    @staticmethod
    def map_bbox_to_original(
        box: BBox | None,
        angle: int,
        original_width: int,
        original_height: int,
    ) -> BBox | None:
        """Map an upright OCR box back to coordinates on the original uploaded image."""

        if box is None:
            return None
        left, top, right, bottom = box
        normalized = angle % 360
        if normalized == 0:
            mapped = (left, top, right, bottom)
        elif normalized == 90:
            mapped = (top, original_height - right, bottom, original_height - left)
        elif normalized == 180:
            mapped = (
                original_width - right,
                original_height - bottom,
                original_width - left,
                original_height - top,
            )
        elif normalized == 270:
            mapped = (original_width - bottom, left, original_width - top, right)
        else:
            raise ValueError("Only right-angle rotations are supported.")
        x1, y1, x2, y2 = mapped
        x1 = max(0, min(int(x1), original_width))
        x2 = max(0, min(int(x2), original_width))
        y1 = max(0, min(int(y1), original_height))
        y2 = max(0, min(int(y2), original_height))
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    @staticmethod
    def map_bbox_from_original(
        box: BBox | None,
        angle: int,
        original_width: int,
        original_height: int,
    ) -> BBox | None:
        """Map an original-image region into the selected upright OCR space."""

        if box is None:
            return None
        left, top, right, bottom = box
        normalized = angle % 360
        if normalized == 0:
            mapped = (left, top, right, bottom)
            upright_width, upright_height = original_width, original_height
        elif normalized == 90:
            mapped = (
                original_height - bottom,
                left,
                original_height - top,
                right,
            )
            upright_width, upright_height = original_height, original_width
        elif normalized == 180:
            mapped = (
                original_width - right,
                original_height - bottom,
                original_width - left,
                original_height - top,
            )
            upright_width, upright_height = original_width, original_height
        elif normalized == 270:
            mapped = (
                top,
                original_width - right,
                bottom,
                original_width - left,
            )
            upright_width, upright_height = original_height, original_width
        else:
            raise ValueError("Only right-angle rotations are supported.")
        x1, y1, x2, y2 = mapped
        x1 = max(0, min(int(x1), upright_width))
        x2 = max(0, min(int(x2), upright_width))
        y1 = max(0, min(int(y1), upright_height))
        y2 = max(0, min(int(y2), upright_height))
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    def _get_paddle(self) -> Any:
        if self._paddle_attempted:
            return self._paddle
        self._paddle_attempted = True
        try:
            import paddle  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("paddlepaddle is not installed") from exc
        from paddleocr import PaddleOCR

        try:
            self._paddle = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            self._paddle = PaddleOCR(lang="en")
        return self._paddle

    def _extract_with_paddle(self, image: np.ndarray) -> list[OcrLine]:
        paddle = self._get_paddle()
        if paddle is None:
            return []

        if hasattr(paddle, "predict"):
            results = paddle.predict(image)
        else:
            results = paddle.ocr(image, cls=True)

        lines: list[OcrLine] = []
        for result in results or []:
            lines.extend(self._parse_paddle_result(result))
        return sorted(
            lines,
            key=lambda line: (
                (line.bounding_box or (0, 0, 0, 0))[1],
                (line.bounding_box or (0, 0, 0, 0))[0],
            ),
        )

    def _parse_paddle_result(self, result: Any) -> list[OcrLine]:
        payload: Any = result
        if hasattr(result, "json"):
            payload = result.json
            if callable(payload):
                payload = payload()
            if isinstance(payload, str):
                payload = json.loads(payload)
        if isinstance(payload, dict) and "res" in payload:
            payload = payload["res"]

        if isinstance(payload, dict):
            texts = payload.get("rec_texts") or payload.get("texts") or []
            scores = payload.get("rec_scores") or payload.get("scores") or []
            polygons = payload.get("rec_polys") or payload.get("dt_polys") or []
            parsed: list[OcrLine] = []
            for index, text in enumerate(texts):
                clean = str(text).strip()
                if not clean:
                    continue
                confidence = self._safe_float(scores[index] if index < len(scores) else 0)
                box = self._polygon_bbox(polygons[index] if index < len(polygons) else None)
                block_id = f"paddle:{index}"
                tokens = self._tokens_from_line(clean, confidence, box, "paddle", block_id)
                parsed.append(
                    OcrLine(
                        text=clean,
                        confidence=confidence,
                        bounding_box=box,
                        tokens=tokens,
                        block_id=block_id,
                        line_id=block_id,
                        source_pass="paddle",
                    )
                )
            return parsed

        # PaddleOCR 2.x compatibility: [[[box], (text, score)], ...]
        lines: list[OcrLine] = []
        if isinstance(payload, list):
            for item_index, item in enumerate(payload):
                if (
                    isinstance(item, (list, tuple))
                    and len(item) == 2
                    and isinstance(item[1], (list, tuple))
                ):
                    text_score = item[1]
                    if len(text_score) >= 2:
                        clean = str(text_score[0]).strip()
                        confidence = self._safe_float(text_score[1])
                        box = self._polygon_bbox(item[0])
                        block_id = f"paddle:{item_index}"
                        tokens = self._tokens_from_line(clean, confidence, box, "paddle", block_id)
                        lines.append(
                            OcrLine(
                                text=clean,
                                confidence=confidence,
                                bounding_box=box,
                                tokens=tokens,
                                block_id=block_id,
                                line_id=block_id,
                                source_pass="paddle",
                            )
                        )
        return [line for line in lines if line.text]

    def _extract_with_tesseract(self, image: np.ndarray) -> list[OcrLine]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        scale = 2 if max(gray.shape) < 2200 else 1
        if scale > 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
        sharpened = cv2.addWeighted(enhanced, 1.35, blurred, -0.35, 0)

        data6 = pytesseract.image_to_data(
            enhanced,
            lang=self._tesseract_lang_value(),
            config="--oem 3 --psm 6",
            output_type=Output.DICT,
        )
        data11 = pytesseract.image_to_data(
            enhanced,
            lang=self._tesseract_lang_value(),
            config="--oem 3 --psm 11",
            output_type=Output.DICT,
        )
        data11_sharp = pytesseract.image_to_data(
            sharpened,
            lang=self._tesseract_lang_value(),
            config="--oem 3 --psm 11",
            output_type=Output.DICT,
        )

        def extract_word_items(data: dict[str, list[Any]]) -> list[dict[str, Any]]:
            word_list: list[dict[str, Any]] = []
            for index, raw_text in enumerate(data.get("text", [])):
                text = str(raw_text).strip()
                if not text:
                    continue
                conf_raw = self._safe_float(data.get("conf", [0])[index])
                if conf_raw < 0:
                    continue
                left = int(data.get("left", [0])[index]) // scale
                top = int(data.get("top", [0])[index]) // scale
                width = int(data.get("width", [0])[index]) // scale
                height = int(data.get("height", [0])[index]) // scale
                word_list.append(
                    {
                        "text": text,
                        "confidence": max(0.0, min(conf_raw / 100.0, 1.0)),
                        "left": left,
                        "top": top,
                        "right": left + width,
                        "bottom": top + height,
                        "height": height,
                        "block": int(data.get("block_num", [0])[index]),
                        "paragraph": int(data.get("par_num", [0])[index]),
                        "line": int(data.get("line_num", [0])[index]),
                    }
                )
            return word_list

        def cluster_words_into_lines(words: list[dict[str, Any]], source_pass: str) -> list[OcrLine]:
            grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
            for w in words:
                grouped.setdefault((w["block"], w["paragraph"], w["line"]), []).append(w)

            clusters: list[list[dict[str, Any]]] = []
            for line_words in grouped.values():
                line_words.sort(key=lambda item: item["left"])
                current_cluster: list[dict[str, Any]] = []
                for w in line_words:
                    if not current_cluster:
                        current_cluster.append(w)
                    else:
                        prev = current_cluster[-1]
                        gap = w["left"] - prev["right"]
                        avg_h = (prev["height"] + w["height"]) / 2.0
                        max_gap = max(35, avg_h * 2.2)
                        if gap > max_gap:
                            clusters.append(current_cluster)
                            current_cluster = [w]
                        else:
                            current_cluster.append(w)
                if current_cluster:
                    clusters.append(current_cluster)

            ocr_lines: list[OcrLine] = []
            for cluster in clusters:
                cluster_text = " ".join(item["text"] for item in cluster).strip()
                if not cluster_text:
                    continue
                cluster_conf = sum(item["confidence"] for item in cluster) / len(cluster)
                bbox = (
                    min(item["left"] for item in cluster),
                    min(item["top"] for item in cluster),
                    max(item["right"] for item in cluster),
                    max(item["bottom"] for item in cluster),
                )
                block_id = f"{source_pass}:{cluster[0]['block']}:{cluster[0]['paragraph']}"
                line_id = f"{block_id}:{cluster[0]['line']}"
                tokens = tuple(
                    OcrToken(
                        text=item["text"],
                        confidence=item["confidence"],
                        bounding_box=(item["left"], item["top"], item["right"], item["bottom"]),
                        block_id=block_id,
                        paragraph_id=block_id,
                        line_id=line_id,
                        source_pass=source_pass,
                    )
                    for item in cluster
                )
                ocr_lines.append(
                    OcrLine(
                        text=cluster_text,
                        confidence=cluster_conf,
                        bounding_box=bbox,
                        tokens=tokens,
                        block_id=block_id,
                        line_id=line_id,
                        source_pass=source_pass,
                    )
                )
            return ocr_lines

        lines6 = cluster_words_into_lines(extract_word_items(data6), "tesseract-psm6")
        lines11 = cluster_words_into_lines(extract_word_items(data11), "tesseract-psm11")
        lines11_sharp = cluster_words_into_lines(
            extract_word_items(data11_sharp), "tesseract-psm11-sharp"
        )

        # Keep both full-image passes, including agreements. Agreement and
        # disagreement are field-confidence evidence, not OCR duplicates to
        # discard before semantic extraction.
        all_lines = [*lines6, *lines11, *lines11_sharp]

        return sorted(
            all_lines,
            key=lambda line: (
                (line.bounding_box or (0, 0, 0, 0))[1],
                (line.bounding_box or (0, 0, 0, 0))[0],
            ),
        )

    def extract_region_targeted(
        self,
        image_bytes: bytes,
        bbox: BBox,
        psm: int = 6,
        orientation_degrees: int = 0,
    ) -> list[OcrLine]:
        """Run a bounded retry in the selected upright coordinate space."""
        image = decode_image(image_bytes)
        if image is None:
            return []
        image = self.rotate_image(image, orientation_degrees)
        h_img, w_img = image.shape[:2]
        l, t, r, b = bbox
        pad_x, pad_y = 30, 30
        crop_l = max(0, l - pad_x)
        crop_t = max(0, t - pad_y)
        crop_r = min(w_img, r + pad_x)
        crop_b = min(h_img, b + pad_y)

        crop = image[crop_t:crop_b, crop_l:crop_r]
        if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
            return []

        scale = 3 if max(crop.shape[:2]) < 1400 else 2
        crop_up = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(crop_up, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        gaussian = cv2.GaussianBlur(clahe, (0, 0), 2.0)
        sharpened = cv2.addWeighted(clahe, 1.8, gaussian, -0.8, 0)
        # Sparse mode benefits from a high-contrast threshold while uniform
        # text blocks retain grayscale detail. Only the requested local crop is
        # retried; these modes are never brute-forced across the whole image.
        if psm == 11:
            _, ocr_image = cv2.threshold(
                clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        else:
            ocr_image = sharpened

        data = pytesseract.image_to_data(
            ocr_image,
            lang=self._tesseract_lang_value(),
            config=f"--oem 3 --psm {psm}",
            output_type=Output.DICT,
        )

        words: list[dict[str, Any]] = []
        for i in range(len(data.get("text", []))):
            t_w = str(data["text"][i]).strip()
            c_w = self._safe_float(data.get("conf", [0])[i])
            if not t_w or c_w < 0:
                continue
            w_left = crop_l + (int(data["left"][i]) // scale)
            w_top = crop_t + (int(data["top"][i]) // scale)
            w_w = int(data["width"][i]) // scale
            w_h = int(data["height"][i]) // scale
            words.append(
                {
                    "text": t_w,
                    "confidence": max(0.0, min(c_w / 100.0, 1.0)),
                    "left": w_left,
                    "top": w_top,
                    "right": w_left + w_w,
                    "bottom": w_top + w_h,
                    "height": w_h,
                    "block": int(data.get("block_num", [0])[i]),
                    "paragraph": int(data.get("par_num", [0])[i]),
                    "line": int(data.get("line_num", [0])[i]),
                }
            )

        grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
        for w in words:
            grouped.setdefault((w["block"], w["paragraph"], w["line"]), []).append(w)

        lines_out: list[list[dict[str, Any]]] = []
        for line_words in grouped.values():
            line_words.sort(key=lambda item: item["left"])
            cluster: list[dict[str, Any]] = []
            for w in line_words:
                if not cluster:
                    cluster.append(w)
                else:
                    prev = cluster[-1]
                    gap = w["left"] - prev["right"]
                    avg_h = (prev["height"] + w["height"]) / 2.0
                    if gap > max(30, avg_h * 2.0):
                        lines_out.append(cluster)
                        cluster = [w]
                    else:
                        cluster.append(w)
            if cluster:
                lines_out.append(cluster)

        res: list[OcrLine] = []
        for cluster in lines_out:
            t_l = " ".join(item["text"] for item in cluster).strip()
            if not t_l:
                continue
            c_l = sum(item["confidence"] for item in cluster) / len(cluster)
            b_l = (
                min(item["left"] for item in cluster),
                min(item["top"] for item in cluster),
                max(item["right"] for item in cluster),
                max(item["bottom"] for item in cluster),
            )
            block_id = f"targeted-psm{psm}:{cluster[0]['block']}:{cluster[0]['paragraph']}"
            line_id = f"{block_id}:{cluster[0]['line']}"
            tokens = tuple(
                OcrToken(
                    text=item["text"],
                    confidence=item["confidence"],
                    bounding_box=(item["left"], item["top"], item["right"], item["bottom"]),
                    block_id=block_id,
                    paragraph_id=block_id,
                    line_id=line_id,
                    source_pass=f"targeted-psm{psm}",
                )
                for item in cluster
            )
            res.append(
                OcrLine(
                    text=t_l,
                    confidence=c_l,
                    bounding_box=b_l,
                    tokens=tokens,
                    block_id=block_id,
                    line_id=line_id,
                    source_pass=f"targeted-psm{psm}",
                )
            )
        return res

    @staticmethod
    def _tokens_from_line(
        text: str,
        confidence: float,
        box: BBox | None,
        source_pass: str,
        block_id: str,
    ) -> tuple[OcrToken, ...]:
        """Create word geometry when an OCR adapter returns only a line polygon."""

        tokens: list[OcrToken] = []
        for match in re.finditer(r"\S+", text):
            token_box = box
            if box and text:
                left, top, right, bottom = box
                width = right - left
                token_box = (
                    left + int(width * match.start() / len(text)),
                    top,
                    left + int(width * match.end() / len(text)),
                    bottom,
                )
            tokens.append(
                OcrToken(
                    text=match.group(0),
                    confidence=confidence,
                    bounding_box=token_box,
                    block_id=block_id,
                    paragraph_id=block_id,
                    line_id=block_id,
                    source_pass=source_pass,
                )
            )
        return tuple(tokens)

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _polygon_bbox(polygon: Any) -> BBox | None:
        if polygon is None:
            return None
        try:
            points = [(int(point[0]), int(point[1])) for point in polygon]
            if not points:
                return None
            xs, ys = zip(*points)
            return (min(xs), min(ys), max(xs), max(ys))
        except (TypeError, ValueError, IndexError):
            return None

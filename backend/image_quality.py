"""Deterministic image validation and quality checks used before OCR."""

from io import BytesIO
from typing import Any
import warnings

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


MIN_PIXEL_AREA = 250_000
MAX_PIXEL_AREA = 40_000_000
BLUR_VARIANCE_FLOOR = 45.0
GLARE_RATIO_CEILING = 0.12
ALLOWED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}


class ImageValidationError(ValueError):
    """Raised when an upload is not a safe, supported raster image."""


def validate_image_payload(image_bytes: bytes) -> dict[str, Any]:
    """Validate the encoded format and dimensions before OpenCV allocates pixels."""

    if not image_bytes:
        raise ImageValidationError("The uploaded image is empty.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as image:
                image_format = str(image.format or "").upper()
                width, height = image.size
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise ImageValidationError(
                        "Unsupported image encoding. Use JPEG, PNG, WebP, BMP, or TIFF."
                    )
                if width <= 0 or height <= 0:
                    raise ImageValidationError("The image has invalid dimensions.")
                if width * height > MAX_PIXEL_AREA:
                    raise ImageValidationError(
                        f"The image exceeds the {MAX_PIXEL_AREA:,}-pixel safety limit."
                    )
                image.verify()
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError("The image dimensions exceed the safety limit.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError("The file could not be decoded as a valid supported image.") from exc

    return {
        "format": image_format,
        "mime_type": ALLOWED_IMAGE_FORMATS[image_format],
        "width": int(width),
        "height": int(height),
        "pixel_area": int(width * height),
    }


def decode_image(image_bytes: bytes) -> np.ndarray | None:
    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def analyze_image_quality(image_bytes: bytes) -> dict[str, Any]:
    try:
        validated = validate_image_payload(image_bytes)
    except ImageValidationError as exc:
        return {
            "status": "unreadable",
            "is_decodable": False,
            "warnings": [str(exc)],
            "guidance_notes": ["Upload a supported raster image captured directly from the label."],
        }
    image = decode_image(image_bytes)
    if image is None:
        return {
            "status": "unreadable",
            "is_decodable": False,
            "warnings": ["The image could not be decoded."],
        }

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    glare_ratio = float(np.mean(gray >= 245))
    dark_pixel_ratio = float(np.mean(gray <= 200))
    resolution_ok = width * height >= MIN_PIXEL_AREA
    blur_ok = blur_score >= BLUR_VARIANCE_FLOOR

    # Compute local contrast metric across standard tiles
    tile_h, tile_w = max(16, height // 16), max(16, width // 16)
    local_stds = []
    for y in range(0, height - tile_h, tile_h):
        for x in range(0, width - tile_w, tile_w):
            tile = gray[y : y + tile_h, x : x + tile_w]
            local_stds.append(float(np.std(tile)))
    local_contrast = float(np.median(local_stds)) if local_stds else float(np.std(gray))
    contrast_ok = local_contrast >= 18.0
    # Bright paper or label stock is not glare when declaration edges retain contrast.
    # Treat highlights as readability risk only when the image is also washed out.
    glare_ok = glare_ratio <= GLARE_RATIO_CEILING or (blur_ok and dark_pixel_ratio >= 0.01)

    warnings: list[str] = []
    guidance_notes: list[str] = []
    if not resolution_ok:
        warnings.append("Image resolution is low for reliable label reading.")
        guidance_notes.append("Capture the statutory declaration panel closer to increase resolution.")
    if not blur_ok:
        warnings.append("Image may be blurred.")
        guidance_notes.append("Hold camera steady under direct lighting to reduce motion blur.")
    if not glare_ok:
        warnings.append("Image contains a large bright or reflective area.")
        guidance_notes.append("Tilt package slightly away from direct flash to avoid glare.")
    if not contrast_ok:
        guidance_notes.append("Low local contrast detected — ensure even lighting across text panels.")

    return {
        "status": "good" if not warnings else "review",
        "is_decodable": True,
        "width": width,
        "height": height,
        "format": validated["format"],
        "mime_type": validated["mime_type"],
        "pixel_area": validated["pixel_area"],
        "blur_score": round(blur_score, 2),
        "glare_ratio": round(glare_ratio, 4),
        "dark_pixel_ratio": round(dark_pixel_ratio, 4),
        "local_contrast": round(local_contrast, 2),
        "resolution_ok": resolution_ok,
        "blur_ok": blur_ok,
        "glare_ok": glare_ok,
        "contrast_ok": contrast_ok,
        "warnings": warnings,
        "guidance_notes": guidance_notes,
    }


def build_gemini_enhanced_variant(
    image_bytes: bytes, quality: dict[str, Any]
) -> bytes | None:
    """Return one conservative contrast/sharpness variant when quality benefits.

    The transform preserves the whole frame and aspect ratio. It is supplied
    beside the original image in one visual request; it never replaces source
    pixels or becomes evidence geometry.
    """

    if quality.get("status") == "good" and quality.get("contrast_ok", True):
        return None
    image = decode_image(image_bytes)
    if image is None:
        return None
    height, width = image.shape[:2]
    scale = min(2.0, max(1.0, 1400.0 / max(height, width)))
    if scale > 1.05:
        image = cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    lightness = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lightness)
    enhanced = cv2.cvtColor(
        cv2.merge((lightness, channel_a, channel_b)), cv2.COLOR_LAB2BGR
    )
    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
    enhanced = cv2.addWeighted(enhanced, 1.35, blurred, -0.35, 0)
    encoded, buffer = cv2.imencode(".png", enhanced)
    return buffer.tobytes() if encoded else None

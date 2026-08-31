"""Evidence image generation for rule findings."""

from typing import Any

import cv2

from image_quality import decode_image


STATUS_COLORS = {
    "PASS": (58, 170, 80),
    "FAIL": (60, 70, 220),
    "UNCERTAIN": (30, 180, 220),
}


def draw_evidence(image_bytes: bytes, findings: list[dict[str, Any]]) -> bytes | None:
    image = decode_image(image_bytes)
    if image is None:
        return None

    for finding in findings:
        box = finding.get("bounding_box")
        if not box or len(box) != 4:
            continue
        x1, y1, x2, y2 = [int(value) for value in box]
        if x2 <= x1 or y2 <= y1:
            continue
        x1 = max(0, min(x1, image.shape[1] - 1))
        y1 = max(0, min(y1, image.shape[0] - 1))
        x2 = max(x1 + 1, min(x2, image.shape[1] - 1))
        y2 = max(y1 + 1, min(y2, image.shape[0] - 1))
        status = str(finding.get("status", "UNCERTAIN"))
        color = STATUS_COLORS.get(status, STATUS_COLORS["UNCERTAIN"])
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
        label = f"{finding.get('rule_id', 'finding')} [{status}]"
        cv2.putText(
            image,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    success, encoded = cv2.imencode(".png", image)
    return encoded.tobytes() if success else None

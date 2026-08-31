"""Generate clearly labelled synthetic package panels for repeatable local demos."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"
FONT = ImageFont.truetype("arial.ttf", 30)
SMALL = ImageFont.truetype("arial.ttf", 20)


def render(filename: str, lines: list[str], *, rotate: int = 0, blur: float = 0) -> None:
    image = Image.new("RGB", (1200, 900), "#fffdf4")
    draw = ImageDraw.Draw(image)
    draw.rectangle((26, 26, 1174, 874), outline="#123d38", width=5)
    draw.rectangle((26, 26, 1174, 105), fill="#123d38")
    draw.text((52, 48), "SYNTHETIC DEMO FIXTURE — NOT A REAL PRODUCT", fill="white", font=SMALL)
    y = 140
    for line in lines:
        draw.text((70, y), line, fill="#101820", font=FONT)
        y += 72
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor="white")
    image.save(SAMPLES / filename, optimize=True)


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    common = [
        "COMMON NAME: Roasted gram snack",
        "MANUFACTURED BY: Example Foods Private Limited",
        "ADDRESS: Plot 12, Industrial Estate, Pune, Maharashtra 411001",
        "NET QUANTITY: 250 g",
        "MFG: 08/2026",
        "CONSUMER CARE: care@example.test  1800 000 1234",
    ]
    render("01-readable-domestic.png", [*common[:4], "MRP: Rs. 95.00 (inclusive of all taxes)", *common[4:]])
    render("02-missing-mrp.png", common)
    render("03-rotated-90.png", [*common[:4], "MRP: Rs. 95.00 (inclusive of all taxes)", *common[4:]], rotate=90)
    render("04-low-quality-blur.png", [*common[:4], "MRP: Rs. 95.00", *common[4:]], blur=6)
    render("05-malformed-mrp.png", [*common[:4], "MRP: ask retailer", *common[4:]])


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "sam.ico"


def _font(size: int):
    candidates = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "seguisb.ttf",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeuib.ttf",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arialbd.ttf",
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def make_icon() -> Path:
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Dark, compact loader-style tile that stays readable at taskbar sizes.
    draw.rounded_rectangle((8, 8, 248, 248), radius=42, fill=(18, 18, 20, 255), outline=(48, 48, 54, 255), width=3)
    draw.rounded_rectangle((8, 8, 248, 21), radius=6, fill=(214, 51, 108, 255))

    font = _font(142)
    text = "S"
    box = draw.textbbox((0, 0), text, font=font, stroke_width=0)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = (size - tw) // 2
    y = (size - th) // 2 - 12

    # Same subtle chromatic offset used by the splash wordmark.
    draw.text((x + 5, y + 4), text, font=font, fill=(255, 0, 64, 220))
    draw.text((x - 4, y - 3), text, font=font, fill=(160, 0, 255, 210))
    draw.text((x, y), text, font=font, fill=(247, 247, 249, 255))

    # Small SAM identifier remains legible in larger Explorer views.
    small = _font(25)
    label = "SAM"
    lb = draw.textbbox((0, 0), label, font=small)
    lw = lb[2] - lb[0]
    draw.text(((size - lw) // 2, 204), label, font=small, fill=(150, 150, 158, 255))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        OUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated {OUT}")
    return OUT


if __name__ == "__main__":
    make_icon()

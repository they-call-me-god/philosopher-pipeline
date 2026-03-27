"""Compose a 1080x1920 B&W philosopher Reel image using Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

REEL_W, REEL_H = 1080, 1920
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (180, 180, 180)
PADDING = 80


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if draw.textlength(test, font=font) <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except (IOError, OSError):
        return ImageFont.load_default()


def compose_reel(
    photo_path: Path,
    quote: str,
    philosopher: str,
    font_path: Path,
    output_path: Path,
) -> Path:
    """Create 1080x1920 B&W Reel image. Returns output_path."""
    canvas = Image.new("RGB", (REEL_W, REEL_H), BG_COLOR)

    # Portrait: greyscale + slight contrast boost, top 52% of canvas
    portrait = Image.open(photo_path).convert("L")
    max_w = REEL_W - PADDING * 2
    max_h = int(REEL_H * 0.52)
    portrait.thumbnail((max_w, max_h), Image.LANCZOS)
    portrait = ImageEnhance.Contrast(portrait).enhance(1.2)
    portrait_rgb = portrait.convert("RGB")

    x_off = (REEL_W - portrait_rgb.width) // 2
    y_off = PADDING
    canvas.paste(portrait_rgb, (x_off, y_off))

    draw = ImageDraw.Draw(canvas)

    # Divider
    div_y = y_off + portrait_rgb.height + 40
    draw.line([(PADDING, div_y), (REEL_W - PADDING, div_y)], fill=ACCENT_COLOR, width=1)

    # Fonts
    quote_font = _load_font(font_path, 42)
    name_font = _load_font(font_path, 34)

    # Quote
    max_text_w = REEL_W - PADDING * 2
    wrapped = _wrap_text(draw, f'"{quote}"', quote_font, max_text_w)
    draw.multiline_text(
        (PADDING, div_y + 50),
        wrapped,
        font=quote_font,
        fill=TEXT_COLOR,
        spacing=14,
    )

    # Philosopher name — bottom right
    name_text = f"— {philosopher.upper()}"
    name_w = draw.textlength(name_text, font=name_font)
    draw.text(
        (REEL_W - PADDING - name_w, REEL_H - PADDING - 50),
        name_text,
        font=name_font,
        fill=ACCENT_COLOR,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(output_path), "JPEG", quality=95)
    return output_path

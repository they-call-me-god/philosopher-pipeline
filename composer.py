"""Compose a 1080x1920 B&W philosopher Reel image using Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

REEL_W, REEL_H = 1080, 1920
TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (200, 200, 200)
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
    """Create 1080x1920 B&W Reel — portrait fills background, text overlaid."""
    # --- Background: portrait scaled to fill entire canvas ---
    portrait = Image.open(photo_path).convert("L")  # greyscale
    portrait = ImageEnhance.Contrast(portrait).enhance(1.15)

    # Scale to cover full 1080x1920 (crop to fill, not letterbox)
    src_ratio = portrait.width / portrait.height
    dst_ratio = REEL_W / REEL_H
    if src_ratio > dst_ratio:
        # wider than canvas — scale by height
        new_h = REEL_H
        new_w = int(REEL_H * src_ratio)
    else:
        new_w = REEL_W
        new_h = int(REEL_W / src_ratio)
    portrait = portrait.resize((new_w, new_h), Image.LANCZOS)

    # Center-crop
    x_off = (new_w - REEL_W) // 2
    y_off = (new_h - REEL_H) // 2
    portrait = portrait.crop((x_off, y_off, x_off + REEL_W, y_off + REEL_H))

    # Darken so text reads clearly
    portrait = ImageEnhance.Brightness(portrait).enhance(0.45)
    canvas = portrait.convert("RGB")

    # --- Dark gradient overlay at bottom for text readability ---
    overlay = Image.new("RGBA", (REEL_W, REEL_H), (0, 0, 0, 0))
    gradient = ImageDraw.Draw(overlay)
    gradient_start = int(REEL_H * 0.42)
    for y in range(gradient_start, REEL_H):
        alpha = int(200 * (y - gradient_start) / (REEL_H - gradient_start))
        gradient.line([(0, y), (REEL_W, y)], fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(canvas)

    # --- Fonts ---
    quote_font = _load_font(font_path, 52)
    name_font = _load_font(font_path, 36)

    # --- Quote — centered, lower third ---
    max_text_w = REEL_W - PADDING * 2
    wrapped = _wrap_text(draw, f'\u201c{quote}\u201d', quote_font, max_text_w)
    lines = wrapped.split("\n")

    # Measure total block height
    line_h = quote_font.size + 18
    block_h = len(lines) * line_h
    name_h = name_font.size + 20
    total_h = block_h + name_h + 30

    # Start quote at ~60% down
    text_start_y = int(REEL_H * 0.60)

    draw.multiline_text(
        (REEL_W // 2, text_start_y),
        wrapped,
        font=quote_font,
        fill=TEXT_COLOR,
        spacing=18,
        align="center",
        anchor="ma",
    )

    # --- Philosopher name below quote ---
    name_text = f"\u2014 {philosopher.upper()}"
    name_y = text_start_y + block_h + 28
    draw.text(
        (REEL_W // 2, name_y),
        name_text,
        font=name_font,
        fill=ACCENT_COLOR,
        anchor="ma",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(output_path), "JPEG", quality=95)
    return output_path

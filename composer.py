from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import ffmpeg


REEL_WIDTH = 1080
REEL_HEIGHT = 1920
TEXT_MAX_WIDTH_RATIO = 0.80
FONT_SIZE_START = 72
FONT_SIZE_MIN = 36
FONT_SIZE_STEP = 4


def compose_image(
    photo_path: str,
    quote: str,
    philosopher: str,
    output_path: str,
    font_path: str,
) -> None:
    """Compose a B&W 1080x1920 Instagram Reel image with centered quote overlay."""
    img = Image.open(photo_path).convert("L")  # grayscale
    img = _fit_to_reel(img)
    img = img.convert("RGB")

    draw = ImageDraw.Draw(img)
    full_text = f'"{quote}"\n— {philosopher}'
    max_px_width = int(REEL_WIDTH * TEXT_MAX_WIDTH_RATIO)

    font_size = FONT_SIZE_START
    font = None
    wrapped = None

    while font_size >= FONT_SIZE_MIN:
        font = ImageFont.truetype(font_path, font_size)
        wrapped = _wrap_text(full_text, font, draw, max_px_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        text_w = bbox[2] - bbox[0]
        if text_w <= max_px_width:
            break
        font_size -= FONT_SIZE_STEP
    else:
        font = ImageFont.truetype(font_path, FONT_SIZE_MIN)
        wrapped = _wrap_text(full_text, font, draw, max_px_width)
        wrapped = _truncate_text(wrapped, font, draw, max_px_width)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_h = bbox[3] - bbox[1]

    x = REEL_WIDTH // 2
    y = REEL_HEIGHT // 2

    # Shadow
    draw.multiline_text((x + 2, y + 2), wrapped, font=font, fill=(0, 0, 0),
                         align="center", anchor="mm")
    # White text
    draw.multiline_text((x, y), wrapped, font=font, fill=(255, 255, 255),
                         align="center", anchor="mm")

    img.save(output_path, "JPEG", quality=95)


def compose_reel(
    image_path: str,
    audio_path: str,
    output_path: str,
    duration: int = 30,
) -> None:
    """Merge static image + audio into a 30s H.264/AAC MP4 Reel."""
    video = ffmpeg.input(image_path, loop=1, framerate=30, t=duration)
    audio = ffmpeg.input(audio_path, t=duration)

    (
        ffmpeg
        .output(
            video, audio, output_path,
            vcodec="libx264", crf=23, pix_fmt="yuv420p",
            acodec="aac", audio_bitrate="128k",
            movflags="+faststart",
        )
        .overwrite_output()
        .run(quiet=True)
    )


def _fit_to_reel(img: Image.Image) -> Image.Image:
    """Resize and letterbox to 1080x1920 with black bars."""
    target_ratio = REEL_WIDTH / REEL_HEIGHT
    w, h = img.size
    img_ratio = w / h

    if img_ratio > target_ratio:
        new_h = REEL_HEIGHT
        new_w = int(w * REEL_HEIGHT / h)
    else:
        new_w = REEL_WIDTH
        new_h = int(h * REEL_WIDTH / w)

    img = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("L", (REEL_WIDTH, REEL_HEIGHT), 0)
    offset_x = (REEL_WIDTH - new_w) // 2
    offset_y = (REEL_HEIGHT - new_h) // 2
    canvas.paste(img, (offset_x, offset_y))
    return canvas


def _wrap_text(text: str, font: ImageFont.FreeTypeFont,
               draw: ImageDraw.ImageDraw, max_width: int) -> str:
    """Word-wrap text to fit within max_width pixels."""
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        current = []
        for word in words:
            test_line = " ".join(current + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
    return "\n".join(lines)


def _truncate_text(text: str, font: ImageFont.FreeTypeFont,
                   draw: ImageDraw.ImageDraw, max_width: int) -> str:
    """Truncate text with ellipsis to fit max_width."""
    for i in range(len(text), 0, -1):
        candidate = text[:i] + "..."
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return candidate
    return "..."

"""Image and slideshow composition for philosopher reels.

- compose_frame(): one image + quote + translucent watermark -> 1080x1920 JPG.
- compose_slideshow(): N composed frames + audio -> fast-cut MP4 reel.
- compose_image()/compose_reel(): backward-compat shims for legacy callers.

Tuned for IG Reels algorithm:
- 0.30 s/frame -> energetic but readable
- 8 s reel -> short enough that viewers loop 3-4 times before scrolling
- Seamless loop: last frame matches first frame so the loop boundary is invisible
- Quote uses serif (Playfair); attribution uses lighter sans-serif (Inter) when available
"""
import logging
import tempfile
from io import BytesIO
from pathlib import Path

import ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger(__name__)

REEL_WIDTH = 1080
REEL_HEIGHT = 1920
TEXT_MAX_WIDTH_RATIO = 0.76

# Quote (serif) sizing — smaller, more readable
QUOTE_FONT_START = 54
QUOTE_FONT_MIN = 26
QUOTE_FONT_STEP = 3

# Attribution (philosopher name) sizing — about 60% of fitted quote size
NAME_FONT_RATIO = 0.62
NAME_FONT_MIN = 22

WATERMARK_TEXT = "@deepahhthinking"
WATERMARK_OPACITY = 130
WATERMARK_FONT_SIZE = 30

# Reel pacing
DEFAULT_FRAME_DURATION = 0.30
DEFAULT_REEL_DURATION = 8
SEAMLESS_LOOP = True


def _load_font(font_path, size):
    """Load TTF; fall back to PIL default on failure."""
    try:
        return ImageFont.truetype(str(font_path), size)
    except (IOError, OSError):
        return ImageFont.load_default()


def _resolve_name_font(font_path):
    """Prefer a sans-serif (Inter) for the attribution; fall back to the quote font."""
    p = Path(font_path)
    candidates = [
        p.parent / "Inter-Medium.ttf",
        p.parent / "Inter-Regular.ttf",
        p.parent / "Inter.ttf",
        p,
    ]
    for c in candidates:
        if c.exists():
            return c
    return p


def compose_frame(
    image_path,
    quote,
    philosopher,
    output_path,
    font_path,
    watermark_text=WATERMARK_TEXT,
):
    """Render one slideshow frame: full-color image + quote + watermark."""
    p = Path(image_path)
    if not p.exists() or p.stat().st_size == 0:
        raise FileNotFoundError("Image missing or empty: " + str(image_path))

    src = Image.open(BytesIO(p.read_bytes())).convert("RGB")
    base = _fit_to_reel_color(src)

    name_font_path = _resolve_name_font(font_path)

    quote_text = '“' + quote + '”'
    name_text = "— " + philosopher.upper()

    max_px_width = int(REEL_WIDTH * TEXT_MAX_WIDTH_RATIO)
    max_px_height = int(REEL_HEIGHT * 0.50)

    measure_draw = ImageDraw.Draw(base)

    # Auto-fit the quote
    quote_size = QUOTE_FONT_START
    quote_font = _load_font(font_path, quote_size)
    wrapped = _wrap_text(quote_text, quote_font, measure_draw, max_px_width)

    while quote_size > QUOTE_FONT_MIN:
        quote_font = _load_font(font_path, quote_size)
        wrapped = _wrap_text(quote_text, quote_font, measure_draw, max_px_width)
        bbox = measure_draw.multiline_textbbox((0, 0), wrapped, font=quote_font, spacing=10)
        if (bbox[2] - bbox[0]) <= max_px_width and (bbox[3] - bbox[1]) <= max_px_height:
            break
        quote_size -= QUOTE_FONT_STEP
    else:
        quote_font = _load_font(font_path, QUOTE_FONT_MIN)
        wrapped = _wrap_text(quote_text, quote_font, measure_draw, max_px_width)
        wrapped = _truncate_text(wrapped, quote_font, measure_draw, max_px_width)

    quote_bbox = measure_draw.multiline_textbbox((0, 0), wrapped, font=quote_font, spacing=10)
    quote_w = quote_bbox[2] - quote_bbox[0]
    quote_h = quote_bbox[3] - quote_bbox[1]

    name_size = max(NAME_FONT_MIN, int(quote_size * NAME_FONT_RATIO))
    name_font = _load_font(name_font_path, name_size)
    name_bbox = measure_draw.textbbox((0, 0), name_text, font=name_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]

    gap = max(18, int(quote_size * 0.45))
    total_h = quote_h + gap + name_h

    cx = REEL_WIDTH // 2
    cy = REEL_HEIGHT // 2
    quote_top = cy - total_h // 2
    name_top = quote_top + quote_h + gap

    # Translucent band behind text
    band_pad_x = 60
    band_pad_y = 48
    band_left = max(0, cx - max(quote_w, name_w) // 2 - band_pad_x)
    band_right = min(REEL_WIDTH, cx + max(quote_w, name_w) // 2 + band_pad_x)
    band_top = max(0, quote_top - band_pad_y)
    band_bot = min(REEL_HEIGHT, name_top + name_h + band_pad_y)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle((band_left, band_top, band_right, band_bot), fill=(0, 0, 0, 140))

    # Quote (serif) — drop shadow + white
    odraw.multiline_text(
        (cx + 2, quote_top + 2), wrapped, font=quote_font, fill=(0, 0, 0, 220),
        align="center", anchor="ma", spacing=10,
    )
    odraw.multiline_text(
        (cx, quote_top), wrapped, font=quote_font, fill=(255, 255, 255, 255),
        align="center", anchor="ma", spacing=10,
    )

    # Attribution (sans-serif, lighter)
    odraw.text(
        (cx + 1, name_top + 1), name_text, font=name_font, fill=(0, 0, 0, 200),
        anchor="ma",
    )
    odraw.text(
        (cx, name_top), name_text, font=name_font, fill=(220, 220, 220, 245),
        anchor="ma",
    )

    # Watermark
    wfont = _load_font(font_path, WATERMARK_FONT_SIZE)
    wbbox = odraw.textbbox((0, 0), watermark_text, font=wfont)
    wtw = wbbox[2] - wbbox[0]
    wth = wbbox[3] - wbbox[1]
    wx = (REEL_WIDTH - wtw) // 2
    wy = REEL_HEIGHT - wth - 90
    odraw.text((wx + 1, wy + 1), watermark_text, font=wfont, fill=(0, 0, 0, WATERMARK_OPACITY))
    odraw.text((wx, wy), watermark_text, font=wfont, fill=(255, 255, 255, WATERMARK_OPACITY))

    final = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    final.save(output_path, "JPEG", quality=92)


def compose_slideshow(
    image_paths,
    quote,
    philosopher,
    audio_path,
    output_path,
    font_path,
    frame_duration=DEFAULT_FRAME_DURATION,
    reel_duration=DEFAULT_REEL_DURATION,
    seamless_loop=SEAMLESS_LOOP,
):
    """Render N image frames and concat them into a fast-cut reel with audio."""
    if not image_paths:
        raise ValueError("compose_slideshow requires at least one image")

    needed = max(1, int(round(reel_duration / frame_duration)))
    chosen = []
    while len(chosen) < needed:
        chosen.extend(image_paths)
    chosen = chosen[:needed]

    workdir = Path(tempfile.mkdtemp(prefix="reel-frames-"))
    try:
        frame_files = []
        for i, image in enumerate(chosen):
            frame_out = workdir / ("frame-" + str(i).zfill(4) + ".jpg")
            try:
                compose_frame(image, quote, philosopher, str(frame_out), font_path)
            except Exception as e:
                log.warning("frame %d failed (%s) - skipping that image", i, e)
                continue
            frame_files.append(frame_out)

        if not frame_files:
            raise RuntimeError("No frames composed - all images failed")

        log.info("Composed %d/%d frames from %d unique images",
                 len(frame_files), needed, len(image_paths))

        concat_path = workdir / "concat.txt"
        lines = []
        APOS = chr(39)
        for f in frame_files:
            lines.append("file " + APOS + f.as_posix() + APOS)
            lines.append("duration " + str(frame_duration))
        loop_target = frame_files[0] if seamless_loop and len(frame_files) > 1 else frame_files[-1]
        lines.append("file " + APOS + loop_target.as_posix() + APOS)
        concat_path.write_text("\n".join(lines), encoding="utf-8")

        try:
            video = ffmpeg.input(str(concat_path), format="concat", safe=0)
            audio = ffmpeg.input(audio_path, t=reel_duration)
            (
                ffmpeg
                .output(
                    video, audio, output_path,
                    vcodec="libx264", crf=23, pix_fmt="yuv420p",
                    acodec="aac", audio_bitrate="128k",
                    movflags="+faststart",
                    r=30,
                    t=reel_duration,
                )
                .overwrite_output()
                .run(quiet=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            raise RuntimeError("ffmpeg slideshow failed: " + e.stderr.decode()[-300:])
    finally:
        try:
            for f in workdir.iterdir():
                f.unlink()
            workdir.rmdir()
        except Exception:
            pass


def _fit_to_reel_color(img):
    """Fit image into 1080x1920 with a blurred enlarged copy as background."""
    target_ratio = REEL_WIDTH / REEL_HEIGHT
    w, h = img.size
    img_ratio = w / h

    if img_ratio > target_ratio:
        new_w_fg = REEL_WIDTH
        new_h_fg = max(1, int(REEL_WIDTH / img_ratio))
    else:
        new_h_fg = REEL_HEIGHT
        new_w_fg = max(1, int(REEL_HEIGHT * img_ratio))
    fg = img.resize((new_w_fg, new_h_fg), Image.LANCZOS)

    if img_ratio > target_ratio:
        bg_h = REEL_HEIGHT
        bg_w = max(REEL_WIDTH, int(bg_h * img_ratio))
    else:
        bg_w = REEL_WIDTH
        bg_h = max(REEL_WIDTH, int(bg_w / img_ratio))
    bg = img.resize((bg_w, bg_h), Image.LANCZOS)
    bg_x = (bg_w - REEL_WIDTH) // 2
    bg_y = (bg_h - REEL_HEIGHT) // 2
    bg = bg.crop((bg_x, bg_y, bg_x + REEL_WIDTH, bg_y + REEL_HEIGHT))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
    dim = Image.new("RGB", bg.size, (0, 0, 0))
    bg = Image.blend(bg, dim, 0.30)

    fg_x = (REEL_WIDTH - fg.width) // 2
    fg_y = (REEL_HEIGHT - fg.height) // 2
    bg.paste(fg, (fg_x, fg_y))
    return bg


def _wrap_text(text, font, draw, max_width):
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


def _truncate_text(text, font, draw, max_width):
    for i in range(len(text), 0, -1):
        candidate = text[:i] + "..."
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return candidate
    return "..."


def compose_image(photo_path, quote, philosopher, output_path, font_path):
    """Legacy entry point, color frame with watermark."""
    compose_frame(photo_path, quote, philosopher, output_path, font_path)


def compose_reel(image_path, audio_path, output_path, duration=30):
    """Legacy single-image static reel kept for backward compatibility."""
    video = ffmpeg.input(image_path, loop=1, framerate=30, t=duration)
    audio = ffmpeg.input(audio_path, t=duration)
    try:
        (
            ffmpeg
            .output(
                video, audio, output_path,
                vcodec="libx264", crf=23, pix_fmt="yuv420p",
                acodec="aac", audio_bitrate="128k",
                movflags="+faststart",
            )
            .overwrite_output()
            .run(quiet=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        raise RuntimeError("ffmpeg failed: " + e.stderr.decode()[-300:])

"""Image and slideshow composition for philosopher reels.

- compose_frame(): one image + quote + translucent watermark -> 1080x1920 JPG.
- compose_slideshow(): N composed frames + audio -> fast-cut MP4 reel (uniform timing).
- compose_slideshow_beat_synced(): cuts land on song beats, xfade transitions,
  optional Ken Burns zoom. The "edited reel without CapCut" path.
- compose_image()/compose_reel(): backward-compat shims for legacy callers.

Tuned for IG Reels algorithm:
- 0.30 s/frame -> energetic but readable
- 8 s reel -> short enough that viewers loop 3-4 times before scrolling
- Seamless loop: last frame matches first frame so the loop boundary is invisible
- Quote uses serif (Playfair); attribution uses lighter sans-serif (Inter) when available
"""
import logging
import subprocess
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


# ─── CapCut-style hard-cut reel ──────────────────────────────────────────────
# Hard cuts (no slide/wipe — those read as PowerPoint), in-clip 1.0 -> 1.30
# zoom punch alternating directions, unified color grade across every clip,
# and ONE persistent text overlay PNG riding on top of the whole 7s timeline
# (text is no longer rebaked into every JPG). Images shuffled, no back-to-back
# repeats. Gothic font for the quote when available, fallback otherwise.

MIN_SEGMENT_SECONDS = 0.20
MAX_SEGMENT_SECONDS = 0.55
MIN_CUTS_PER_REEL = 16

DEFAULT_COLOR_GRADE = "vintage"
COLOR_GRADES = {
    # Subtle desaturation + warm shadows + slight contrast bump
    "vintage": "eq=saturation=0.62:contrast=1.10:gamma=0.95,curves=preset=vintage",
    # Old-paper sepia tone, strong unification across paintings
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    # Desaturated B/W high contrast
    "noir": "eq=saturation=0:contrast=1.20:gamma=0.95",
    # Cool-blue hazy film
    "cool": "eq=saturation=0.65:gamma_b=1.08:gamma_r=0.94",
    # Warm sun-faded film
    "warm": "eq=saturation=0.72:gamma_r=1.06:gamma_b=0.92",
    "off": "",
}


def detect_hits(audio_path, max_duration=8.0):
    """Return (hit_times, tempo_bpm) combining beats + onset transients.

    Onset detection fires on every drum hit, snare, vocal entry — far more
    cut points than beat tracking alone, so slow songs still cut frequently.
    """
    try:
        import librosa
    except ImportError:
        log.warning("librosa not installed — falling back to fixed 120 BPM grid")
        return _fixed_grid_beats(max_duration, 120.0), 120.0

    try:
        import numpy as np
        y, sr = librosa.load(str(audio_path), sr=None, duration=max_duration + 1.0)

        tempo, beat_times = librosa.beat.beat_track(y=y, sr=sr, units="time")
        beats = np.atleast_1d(beat_times).ravel().tolist()

        onset_times = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=False)
        onsets = np.atleast_1d(onset_times).ravel().tolist()

        # Union, dedupe within 0.10s, clip to window
        all_hits = sorted(set(round(float(t), 3) for t in (list(beats) + list(onsets))))
        hits = []
        for t in all_hits:
            if 0.0 < t < max_duration and (not hits or t - hits[-1] >= 0.10):
                hits.append(t)

        tempo_arr = np.atleast_1d(tempo).ravel()
        tempo_val = float(tempo_arr[0]) if tempo_arr.size > 0 else 120.0
    except Exception as e:
        log.warning("hit detection failed (%s) — falling back to fixed grid", e)
        return _fixed_grid_beats(max_duration, 120.0), 120.0

    if not hits or hits[0] > 0.05:
        hits.insert(0, 0.0)
    if not hits or hits[-1] < max_duration - 0.05:
        hits.append(float(max_duration))

    return hits, tempo_val


def _fixed_grid_beats(duration, bpm):
    """Generate evenly-spaced 'beat' times when librosa isn't available."""
    period = 60.0 / bpm
    t = 0.0
    out = [0.0]
    while t + period < duration:
        t += period
        out.append(round(t, 4))
    if out[-1] < duration - 0.05:
        out.append(float(duration))
    return out


def _segments_from_hits(hit_times, target_duration, min_cuts=MIN_CUTS_PER_REEL):
    """Convert hit times into segment durations and force minimum cut density.

    If fewer than min_cuts segments emerge from the audio analysis, the
    longest segments get split in half repeatedly until min_cuts is met.
    Net effect: even ballads get 16+ cuts in a 7s reel.
    """
    raw = [hit_times[i + 1] - hit_times[i] for i in range(len(hit_times) - 1)]
    cleaned = []
    for s in raw:
        if s < MIN_SEGMENT_SECONDS:
            if cleaned:
                cleaned[-1] += s
            else:
                cleaned.append(s)
        elif s > MAX_SEGMENT_SECONDS:
            n_splits = int(s / MAX_SEGMENT_SECONDS) + 1
            piece = s / n_splits
            cleaned.extend([piece] * n_splits)
        else:
            cleaned.append(s)

    if not cleaned:
        per = target_duration / max(min_cuts, 1)
        return [per] * min_cuts

    # Force minimum cut count by halving the largest segment until we hit min_cuts
    safety = 0
    while len(cleaned) < min_cuts and safety < 200:
        max_idx = cleaned.index(max(cleaned))
        biggest = cleaned.pop(max_idx)
        cleaned.insert(max_idx, biggest / 2.0)
        cleaned.insert(max_idx, biggest / 2.0)
        safety += 1

    total = sum(cleaned)
    if total <= 0:
        per = target_duration / max(min_cuts, 1)
        return [per] * min_cuts
    scale = target_duration / total
    return [s * scale for s in cleaned]


def _select_images_for_cuts(image_paths, n_cuts, seamless_loop=True):
    """Shuffle pool and pick n_cuts images with no back-to-back repeats.

    If seamless_loop=True, the last image equals the first so the IG
    auto-replay boundary is invisible.
    """
    import random
    if not image_paths:
        return []
    if len(image_paths) == 1:
        return [image_paths[0]] * n_cuts

    pool_template = list(image_paths)
    random.shuffle(pool_template)
    pool = list(pool_template)
    out = []
    last = None
    while len(out) < n_cuts:
        if not pool:
            pool = list(pool_template)
        # Avoid back-to-back: if the next pick equals last, swap in a different one
        pick = pool.pop()
        if pick == last and pool:
            alt = pool.pop()
            pool.insert(0, pick)
            pick = alt
        out.append(pick)
        last = pick

    if seamless_loop and n_cuts > 1:
        out[-1] = out[0]
    return out


def _resolve_overlay_font(overlay_font_path, fallback_font_path):
    """Pick the gothic font if it exists, else the fallback (Playfair)."""
    if overlay_font_path:
        try:
            ImageFont.truetype(str(overlay_font_path), 12)
            return overlay_font_path
        except (IOError, OSError):
            pass
    return fallback_font_path


def _render_quote_overlay(quote, philosopher, output_path, gothic_font_path, watermark_font_path):
    """Render the persistent transparent 1080x1920 text overlay.

    One PNG drawn once and overlaid onto the whole video timeline — text never
    rebakes per frame, never jitters across cuts. Smaller fonts than the old
    per-frame version, gothic typeface for the quote+name, plain font for the
    watermark.
    """
    img = Image.new("RGBA", (REEL_WIDTH, REEL_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Smaller text than baked-frame version — gothic reads heavier per pixel.
    quote_size_start = 38
    quote_size_min = 18
    quote_size_step = 2
    name_size_ratio = 0.55
    name_size_min = 16
    line_spacing = 8

    quote_text = '"' + quote + '"'
    name_text = "- " + philosopher.upper()

    max_px_width = int(REEL_WIDTH * 0.72)
    max_px_height = int(REEL_HEIGHT * 0.40)

    quote_size = quote_size_start
    quote_font = _load_font(gothic_font_path, quote_size)
    wrapped = _wrap_text(quote_text, quote_font, draw, max_px_width)
    while quote_size > quote_size_min:
        quote_font = _load_font(gothic_font_path, quote_size)
        wrapped = _wrap_text(quote_text, quote_font, draw, max_px_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=quote_font, spacing=line_spacing)
        if (bbox[2] - bbox[0]) <= max_px_width and (bbox[3] - bbox[1]) <= max_px_height:
            break
        quote_size -= quote_size_step
    else:
        quote_font = _load_font(gothic_font_path, quote_size_min)
        wrapped = _wrap_text(quote_text, quote_font, draw, max_px_width)
        wrapped = _truncate_text(wrapped, quote_font, draw, max_px_width)

    quote_bbox = draw.multiline_textbbox((0, 0), wrapped, font=quote_font, spacing=line_spacing)
    quote_w = quote_bbox[2] - quote_bbox[0]
    quote_h = quote_bbox[3] - quote_bbox[1]

    name_size = max(name_size_min, int(quote_size * name_size_ratio))
    name_font = _load_font(gothic_font_path, name_size)
    name_bbox = draw.textbbox((0, 0), name_text, font=name_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]

    gap = max(12, int(quote_size * 0.40))
    total_h = quote_h + gap + name_h
    cx = REEL_WIDTH // 2
    cy = REEL_HEIGHT // 2
    quote_top = cy - total_h // 2
    name_top = quote_top + quote_h + gap

    # Slim band behind text for legibility against any image
    band_pad_x = 36
    band_pad_y = 24
    band_left = max(0, cx - max(quote_w, name_w) // 2 - band_pad_x)
    band_right = min(REEL_WIDTH, cx + max(quote_w, name_w) // 2 + band_pad_x)
    band_top = max(0, quote_top - band_pad_y)
    band_bot = min(REEL_HEIGHT, name_top + name_h + band_pad_y)
    draw.rectangle((band_left, band_top, band_right, band_bot), fill=(0, 0, 0, 110))

    # Quote (gothic) — soft drop shadow + white
    draw.multiline_text(
        (cx + 1, quote_top + 1), wrapped, font=quote_font, fill=(0, 0, 0, 200),
        align="center", anchor="ma", spacing=line_spacing,
    )
    draw.multiline_text(
        (cx, quote_top), wrapped, font=quote_font, fill=(255, 255, 255, 255),
        align="center", anchor="ma", spacing=line_spacing,
    )

    # Attribution (same gothic, smaller, dimmer)
    draw.text((cx + 1, name_top + 1), name_text, font=name_font, fill=(0, 0, 0, 200), anchor="ma")
    draw.text((cx, name_top), name_text, font=name_font, fill=(220, 220, 220, 240), anchor="ma")

    # Watermark — plain font (gothic blackletter is unreadable at small sizes)
    wm = "@deepahhthinking"
    wm_size = 22
    wm_font = _load_font(watermark_font_path, wm_size)
    wbbox = draw.textbbox((0, 0), wm, font=wm_font)
    wx = (REEL_WIDTH - (wbbox[2] - wbbox[0])) // 2
    wy = REEL_HEIGHT - (wbbox[3] - wbbox[1]) - 80
    draw.text((wx + 1, wy + 1), wm, font=wm_font, fill=(0, 0, 0, 130))
    draw.text((wx, wy), wm, font=wm_font, fill=(255, 255, 255, 130))

    img.save(output_path, "PNG")


_PAN_MODES = [
    # (x_expr, y_expr) for zoompan. Each is "center +/- offset" of the
    # original frame, so the visible window slides while it zooms.
    ("iw/2-(iw/zoom/2)",                       "ih/2-(ih/zoom/2)"),       # 0 center
    ("iw/2-(iw/zoom/2)+(iw-iw/zoom)/2*on/d",   "ih/2-(ih/zoom/2)"),       # 1 pan right
    ("iw/2-(iw/zoom/2)-(iw-iw/zoom)/2*on/d",   "ih/2-(ih/zoom/2)"),       # 2 pan left
    ("iw/2-(iw/zoom/2)",                       "ih/2-(ih/zoom/2)+(ih-ih/zoom)/2*on/d"),  # 3 pan down
    ("iw/2-(iw/zoom/2)",                       "ih/2-(ih/zoom/2)-(ih-ih/zoom)/2*on/d"),  # 4 pan up
    ("iw/2-(iw/zoom/2)+(iw-iw/zoom)/3*on/d",   "ih/2-(ih/zoom/2)-(ih-ih/zoom)/3*on/d"),  # 5 diag NE
    ("iw/2-(iw/zoom/2)-(iw-iw/zoom)/3*on/d",   "ih/2-(ih/zoom/2)+(ih-ih/zoom)/3*on/d"),  # 6 diag SW
]


def _capcut_clip_filter(idx, length_sec, color_grade_filter, flash=False):
    """Per-clip ffmpeg filter chain, CapCut-style.

    Outputs every clip as 1080x1920 30fps yuv420p so the concat filter
    accepts them. Each clip gets:
      - 1.00 -> 1.45 punch zoom alternating in/out by clip index
      - Random parallax pan direction (7-way) so motion is never repetitive
      - Optional one-frame white flash on the first frame (drops on bass hits)
      - Per-clip subtle exposure variance, sells the "edited" feel
      - Unified color grade applied AFTER all motion so cuts read as one reel
    """
    d_frames = max(1, int(length_sec * 30))
    # Bigger zoom range than v3 (1.30 -> 1.45) so even a 0.20s clip has visible motion
    if idx % 2 == 0:
        z_expr = "min(zoom+0.0055,1.45)"
    else:
        z_expr = "if(eq(on,0),1.45,max(zoom-0.0055,1.00))"

    # Deterministic pan-mode pick so retries are stable, but every clip is different
    pan_x, pan_y = _PAN_MODES[(idx * 3 + 1) % len(_PAN_MODES)]

    chain = [
        "scale=2160:3840:force_original_aspect_ratio=increase",
        "crop=2160:3840",
        ("zoompan=z='" + z_expr + "'"
         + ":x='" + pan_x + "':y='" + pan_y + "'"
         + ":d=" + str(d_frames) + ":s=1080x1920:fps=30"),
    ]
    # Per-clip exposure jitter for that hand-cut feel: +/- 4% brightness, +/- 5% saturation
    bright_jitter = ((idx * 37) % 9 - 4) / 100.0
    sat_jitter = 1.0 + ((idx * 53) % 11 - 5) / 100.0
    chain.append("eq=brightness=%.3f:saturation=%.3f" % (bright_jitter, sat_jitter))
    if color_grade_filter:
        chain.append(color_grade_filter)
    if flash:
        # White flash on first 2 frames of the clip via brightness ramp.
        # 'lte(t,0.067)' fires for the first 2 frames at 30fps.
        chain.append("eq=brightness='if(lte(t,0.067),0.55,0)'")
    chain.append("setsar=1")
    chain.append("format=yuv420p")
    return "[" + str(idx) + ":v]" + ",".join(chain) + "[v" + str(idx) + "]"


def compose_slideshow_beat_synced(
    image_paths,
    quote,
    philosopher,
    audio_path,
    output_path,
    font_path,
    reel_duration=7.0,
    min_cuts=MIN_CUTS_PER_REEL,
    seamless_loop=True,
    color_grade=DEFAULT_COLOR_GRADE,
    overlay_font_path=None,
):
    """CapCut-style hard-cut reel.

    - Cuts on detected beats+onsets, force min_cuts segments in the window
    - Each clip: 1.0 -> 1.30 alternating zoom punch + unified color grade
    - HARD CUTS via concat filter (no slide/wipe — those read as PowerPoint)
    - ONE persistent text overlay PNG sits on top of the entire timeline
    - Gothic overlay font (UnifrakturMaguntia) when available, else Playfair
    """
    if not image_paths:
        raise ValueError("compose_slideshow_beat_synced requires at least one image")

    hits, tempo = detect_hits(audio_path, max_duration=reel_duration)
    segments = _segments_from_hits(hits, reel_duration, min_cuts=min_cuts)
    n_segments = len(segments)

    chosen_images = _select_images_for_cuts(image_paths, n_segments, seamless_loop=seamless_loop)
    unique_count = len(set(chosen_images))

    grade_filter = COLOR_GRADES.get(color_grade, COLOR_GRADES[DEFAULT_COLOR_GRADE])
    overlay_font = _resolve_overlay_font(overlay_font_path, font_path)

    log.info(
        "capcut reel v3: tempo=%.0f BPM, %d hard cuts, %d unique images, grade=%s, gothic=%s, durations=%s",
        tempo, n_segments, unique_count, color_grade,
        bool(overlay_font_path) and str(overlay_font) == str(overlay_font_path),
        ["%.2f" % s for s in segments],
    )

    workdir = Path(tempfile.mkdtemp(prefix="reel-cc3-"))
    try:
        # 1. Pre-render the persistent text overlay (gothic font, smaller text, watermark)
        overlay_png = workdir / "quote_overlay.png"
        _render_quote_overlay(quote, philosopher, str(overlay_png), overlay_font, font_path)

        # 2. ffmpeg: per-clip scale+zoom+grade, concat them, overlay text, mux audio
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stats"]
        for i, src in enumerate(chosen_images):
            cmd += ["-loop", "1", "-t", "%.4f" % segments[i], "-i", str(src)]
        cmd += ["-i", str(overlay_png)]
        overlay_idx = len(chosen_images)
        cmd += ["-i", str(audio_path)]
        audio_idx = len(chosen_images) + 1

        # Flash punches: every 4th cut + the first and last segment. These
        # land where the eye expects a "drop" so the reel reads as edited.
        flash_indices = set([0, len(chosen_images) - 1])
        flash_indices.update(range(3, len(chosen_images), 4))

        parts = []
        for i in range(len(chosen_images)):
            parts.append(_capcut_clip_filter(
                i, segments[i], grade_filter, flash=(i in flash_indices)
            ))
        chain_inputs = "".join("[v%d]" % i for i in range(len(chosen_images)))
        parts.append(chain_inputs + "concat=n=" + str(len(chosen_images)) + ":v=1:a=0[vcat]")
        # Cinematic finishing chain on the full timeline:
        #   vignette  -> darken edges, sells filmic feel
        #   noise     -> subtle film grain (4 alpha, temporal so it moves)
        #   unsharp   -> micro-sharpening, makes paintings feel HD
        parts.append(
            "[vcat]"
            "vignette=PI/5,"
            "noise=alls=6:allf=t,"
            "unsharp=3:3:0.4:3:3:0.0"
            "[vfin]"
        )
        parts.append("[vfin][" + str(overlay_idx) + ":v]overlay=0:0:format=auto[vout]")

        cmd += [
            "-filter_complex", ";".join(parts),
            "-map", "[vout]",
            "-map", "%d:a" % audio_idx,
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-r", "30",
            "-t", "%.4f" % reel_duration,
            "-shortest",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            tail = (result.stderr or "")[-700:]
            raise RuntimeError("ffmpeg capcut compose failed: " + tail)
    finally:
        try:
            for f in workdir.iterdir():
                f.unlink()
            workdir.rmdir()
        except Exception:
            pass


# Back-compat aliases so older callers (and earlier function names) still work.
detect_beats = detect_hits
_segments_from_beats = _segments_from_hits

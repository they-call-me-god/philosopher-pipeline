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


# ─── CapCut-style fast-cut slideshow ─────────────────────────────────────────
# Force at least 16 cuts in 7s regardless of song tempo. Detect beats AND
# onset transients (drum hits, vocals) for finer rhythmic granularity, then
# rotate through hard slide/zoom/wipe transitions (no fades). Each clip gets
# a punchy zoom (1.0 -> 1.22) so motion never stops. Images shuffled with
# no back-to-back repeats so the same painting never sits next to itself.

# Punchy transitions only — no fade/fadeblack/fadewhite which wash out cuts.
# These mimic the rotating transitions in CapCut's viral templates.
TRANSITIONS_PUNCHY = [
    "slideleft", "slideright", "slideup", "slidedown",
    "zoomin", "smoothleft", "smoothright",
    "wipeleft", "wiperight", "circleopen",
]
# Soft pool kept for callers that explicitly want a calm look.
TRANSITIONS_SOFT = ["fade", "dissolve", "smoothleft", "wiperight"]

MIN_SEGMENT_SECONDS = 0.20   # tighter cuts than this read as noise
MAX_SEGMENT_SECONDS = 0.55   # any gap longer than this gets split
MIN_CUTS_PER_REEL = 16       # CapCut feel: 16 cuts in a 7s reel, even on slow songs


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


def compose_slideshow_beat_synced(
    image_paths,
    quote,
    philosopher,
    audio_path,
    output_path,
    font_path,
    reel_duration=7.0,
    transition="auto",
    transition_duration=0.10,
    ken_burns=True,
    seamless_loop=True,
    min_cuts=MIN_CUTS_PER_REEL,
):
    """CapCut-style fast-cut reel: hits-synced cuts, rotating slide/zoom/wipe
    transitions, punchy zoom on every clip, shuffled images with no repeats.

    Default transition='auto' rotates through TRANSITIONS_PUNCHY so every
    cut looks different. Set transition='slideleft' (or any single name) to
    force a specific look.
    """
    if not image_paths:
        raise ValueError("compose_slideshow_beat_synced requires at least one image")

    hits, tempo = detect_hits(audio_path, max_duration=reel_duration)
    segments = _segments_from_hits(hits, reel_duration, min_cuts=min_cuts)
    n_segments = len(segments)

    chosen_images = _select_images_for_cuts(image_paths, n_segments, seamless_loop=seamless_loop)
    unique_count = len(set(chosen_images))

    log.info(
        "capcut reel: tempo=%.0f BPM, %d cuts, %d unique images, transition=%s, durations=%s",
        tempo, n_segments, unique_count, transition,
        ["%.2f" % s for s in segments],
    )

    workdir = Path(tempfile.mkdtemp(prefix="reel-capcut-"))
    try:
        frame_paths = []
        for i, src_image in enumerate(chosen_images):
            out = workdir / ("frame-" + str(i).zfill(4) + ".jpg")
            try:
                compose_frame(src_image, quote, philosopher, str(out), font_path)
                frame_paths.append(out)
            except Exception as e:
                log.warning("frame %d failed (%s) - reusing previous", i, e)
                if frame_paths:
                    frame_paths.append(frame_paths[-1])

        if not frame_paths:
            raise RuntimeError("No frames composed - all images failed")

        D = float(transition_duration)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stats"]

        for i, fp in enumerate(frame_paths):
            length = segments[i] + D
            cmd += ["-loop", "1", "-t", "%.4f" % length, "-i", str(fp)]
        cmd += ["-i", str(audio_path)]
        audio_idx = len(frame_paths)

        parts = []
        for i in range(len(frame_paths)):
            parts.append(_clip_filter(i, segments[i] + D, ken_burns=ken_burns))

        if len(frame_paths) == 1:
            parts.append("[v0]copy[vout]")
        else:
            cumulative = 0.0
            prev_label = "[v0]"
            for i in range(1, len(frame_paths)):
                cumulative += segments[i - 1]
                offset = max(0.0, cumulative - D)
                if transition == "auto":
                    trans = TRANSITIONS_PUNCHY[(i - 1) % len(TRANSITIONS_PUNCHY)]
                else:
                    trans = transition
                last = i == len(frame_paths) - 1
                out_label = "[vout]" if last else "[x%d]" % i
                parts.append(
                    "%s[v%d]xfade=transition=%s:duration=%.4f:offset=%.4f%s"
                    % (prev_label, i, trans, D, offset, out_label)
                )
                prev_label = out_label

        filter_complex = ";".join(parts)

        cmd += [
            "-filter_complex", filter_complex,
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
            tail = (result.stderr or "")[-500:]
            raise RuntimeError("ffmpeg capcut compose failed: " + tail)
    finally:
        try:
            for f in workdir.iterdir():
                f.unlink()
            workdir.rmdir()
        except Exception:
            pass


# Backwards-compat alias for old callers using detect_beats / _segments_from_beats names.
detect_beats = detect_hits
_segments_from_beats = _segments_from_hits


def _clip_filter(idx, length_sec, ken_burns):
    """Per-clip filter chain: scale, punchy zoom, normalize for xfade.

    xfade requires every input to share resolution, fps, pixel format, timebase.
    The zoom is bigger and faster than the old Ken Burns (1.0 -> 1.22 vs 1.0 -> 1.10)
    so each clip has visible motion even at 0.4s — that's the CapCut punch.
    """
    base = "[%d:v]" % idx
    if ken_burns:
        d_frames = max(1, int(length_sec * 30))
        # Alternate punchy zoom direction per clip for visual rhythm.
        if idx % 2 == 0:
            z_expr = "min(zoom+0.0030,1.22)"   # punchy zoom in
        else:
            z_expr = "if(eq(on,0),1.22,max(zoom-0.0030,1.00))"  # punchy zoom out
        return (
            base
            + "scale=2160:3840:force_original_aspect_ratio=increase,"
            + "crop=2160:3840,"
            + "zoompan=z='" + z_expr + "':"
            + "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            + "d=" + str(d_frames) + ":s=1080x1920:fps=30,"
            + "setsar=1,format=yuv420p[v" + str(idx) + "]"
        )
    return (
        base
        + "scale=1080:1920:force_original_aspect_ratio=increase,"
        + "crop=1080:1920,setsar=1,fps=30,format=yuv420p[v" + str(idx) + "]"
    )

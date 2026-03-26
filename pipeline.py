#!/usr/bin/env python3
"""
Philosopher Instagram Pipeline
Usage: python pipeline.py

Reads philosophers.md and songs.md from the Vault root,
generates a B&W quote reel for each philosopher,
and schedules them for Instagram upload at optimal times.
"""
import hashlib
import logging
import os
import sys
import time
from pathlib import Path

# Load .env file from the pipeline directory if present
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from state import StateManager
from input_parser import parse_philosophers, parse_songs
from fetcher import fetch_quote, match_song, fetch_photo
from composer import compose_image, compose_reel
from scheduler import schedule_uploads
from uploader import upload_reel

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
VAULT_DIR = BASE_DIR.parent

_local_philosophers = BASE_DIR / "philosophers.md"
PHILOSOPHERS_FILE = _local_philosophers if _local_philosophers.exists() else VAULT_DIR / "philosophers.md"

_local_songs = BASE_DIR / "songs.md"
SONGS_FILE = _local_songs if _local_songs.exists() else VAULT_DIR / "songs.md"
STATE_FILE = BASE_DIR / "state.json"
OUTPUT_DIR = BASE_DIR / "output"
CACHE_PHOTOS = BASE_DIR / "cache" / "photos"
CACHE_AUDIO = BASE_DIR / "cache" / "audio"
FONT_PATH = BASE_DIR / "fonts" / "PlayfairDisplay-Regular.ttf"

RUN_ID = time.strftime("%Y-%m-%dT%H%M%S")


def main(upload_now: bool = False, single: bool = False, generate_only: bool = False) -> None:
    # ── Pre-flight ────────────────────────────────────────────────────────────
    for d in [OUTPUT_DIR, CACHE_PHOTOS, CACHE_AUDIO]:
        d.mkdir(parents=True, exist_ok=True)

    if not FONT_PATH.exists():
        sys.exit(
            f"[error] Font not found: {FONT_PATH}\n"
            f"Run: curl -L <playfair-url> -o {FONT_PATH}"
        )

    # ── Parse inputs ──────────────────────────────────────────────────────────
    philosophers = parse_philosophers(PHILOSOPHERS_FILE)
    songs = parse_songs(SONGS_FILE)

    state = StateManager(STATE_FILE)
    state.load()

    blacklisted = set(state.get_blacklisted_songs())
    available_songs = [s for s in songs if s["url"] not in blacklisted]

    if len(available_songs) < len(philosophers):
        sys.exit(
            f"[error] Need at least {len(philosophers)} songs, "
            f"but only {len(available_songs)} available after excluding "
            f"{len(blacklisted)} blacklisted URLs.\n"
            f"Add more entries to {SONGS_FILE}."
        )

    log.info("Run ID: %s", RUN_ID)
    log.info("Processing %d philosophers...", len(philosophers))

    # ── Process each philosopher ──────────────────────────────────────────────
    generated: list[dict] = []
    used_songs_this_run: list[str] = []

    if single:
        philosophers = sorted(philosophers, key=lambda p: state.get_philosopher(p)["post_count"])[:1]
        log.info("Running in --single mode. Selected %s", philosophers[0])

    for philosopher in philosophers:
        log.info("── %s ──", philosopher)
        phil_state = state.get_philosopher(philosopher)

        # 1. Fetch quote
        log.info("  Fetching quote...")
        try:
            quote_result = fetch_quote(philosopher, phil_state["used_quotes"])
        except Exception as e:
            log.warning("  Quote fetch failed for %s: %s — skipping.", philosopher, e)
            continue
        quote = quote_result["quote"]
        reframed = quote_result["reframed"]
        log.info("  Quote: %s...", quote[:60])

        # 2. Match song
        log.info("  Matching song...")
        try:
            song_url = match_song(
                philosopher, quote,
                songs=available_songs,
                used_in_run=used_songs_this_run,
                used_for_philosopher=phil_state["used_songs"],
            )
        except Exception as e:
            log.warning("  Song match failed for %s: %s — skipping.", philosopher, e)
            continue
        used_songs_this_run.append(song_url)
        log.info("  Song: %s", song_url)

        # 3. Fetch photo
        log.info("  Fetching photo...")
        try:
            photo_path = fetch_photo(philosopher, phil_state["used_photos"], CACHE_PHOTOS)
        except Exception as e:
            log.warning("  Photo fetch failed for %s: %s — skipping.", philosopher, e)
            continue
        if not photo_path:
            log.warning("  No photo found for %s — skipping.", philosopher)
            continue
        photo_filename = Path(photo_path).name
        log.info("  Photo: %s", photo_filename)

        # 4. Compose image
        log.info("  Composing image...")
        slug = _philosopher_slug(philosopher)
        img_path = str(OUTPUT_DIR / f"{slug}-{RUN_ID}.jpg")
        try:
            compose_image(photo_path, quote, philosopher, img_path, str(FONT_PATH))
        except Exception as e:
            log.warning("  Image composition failed for %s: %s — skipping.", philosopher, e)
            continue
        log.info("  Image: %s", img_path)

        # 5. Download audio
        log.info("  Downloading audio...")
        audio_path = _download_audio(song_url, CACHE_AUDIO, state)
        if not audio_path:
            log.warning("  Audio download failed for %s — skipping.", philosopher)
            continue
        log.info("  Audio: %s", audio_path)

        # 6. Compose reel
        log.info("  Composing reel...")
        mp4_path = str(OUTPUT_DIR / f"{slug}-{RUN_ID}.mp4")
        try:
            compose_reel(img_path, audio_path, mp4_path)
        except Exception as e:
            log.warning("  Reel composition failed for %s: %s — skipping.", philosopher, e)
            continue

        # Verify output
        if not Path(mp4_path).exists() or Path(mp4_path).stat().st_size == 0:
            log.warning("  Reel file missing or empty for %s — skipping.", philosopher)
            continue

        # 7. Update state — only after confirmed success
        state.update_philosopher(philosopher, quote, song_url, photo_filename, reframed)
        log.info("  State updated.")

        slug_tag = slug.replace("-", "")[:20]
        caption = (
            f'"{quote}"\n\n'
            f"— {philosopher}\n\n"
            f"#philosophy #quotes #wisdom #deepthoughts #philosophyquotes "
            f"#mindset #existentialism #stoicism #motivation #{slug_tag} "
            f"#thinkers #lifequotes #intellectuals #classicquotes #deepquotes"
        )
        jpg_path = str(Path(mp4_path).with_suffix(".jpg"))
        generated.append({
            "philosopher": philosopher,
            "mp4_path": mp4_path,
            "jpg_path": jpg_path,
            "caption": caption,
        })
        log.info("  Reel ready: %s", mp4_path)

    # ── Schedule & Upload ─────────────────────────────────────────────────────
    if not generated:
        log.warning("No reels generated. Exiting.")
        return

    if generate_only:
        log.info("--generate-only: %d reel(s) saved to output/, skipping upload.", len(generated))
        for reel in generated:
            log.info("  Ready: %s", reel["mp4_path"])
    elif upload_now:
        log.info("--now flag set: uploading %d reels immediately...", len(generated))
        for reel in generated:
            log.info("  Uploading %s...", reel["philosopher"])
            try:
                upload_reel(reel["mp4_path"], reel["caption"], reel.get("jpg_path"))
                log.info("  ✓ Uploaded %s", reel["philosopher"])
            except Exception as e:
                log.error("  ✗ Upload failed for %s: %s", reel["philosopher"], e)
    else:
        log.info("Scheduling %d reels...", len(generated))
        schedule_uploads(generated, upload_reel)


def _philosopher_slug(name: str) -> str:
    """Convert philosopher name to URL-safe slug."""
    slug = name.lower()
    replacements = {
        "ø": "o", "ü": "u", "ä": "a", "ö": "o",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "ï": "i", "î": "i", "ô": "o", "û": "u",
        "ç": "c", "ñ": "n", " ": "-",
    }
    for char, rep in replacements.items():
        slug = slug.replace(char, rep)
    return "".join(c for c in slug if c.isalnum() or c == "-")


def _download_audio(song_url: str, cache_dir: Path, state: StateManager) -> str | None:
    """Download audio via yt-dlp. Returns local .m4a path or None on failure."""
    import re
    import subprocess

    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", song_url)
    video_id = match.group(1) if match else hashlib.md5(song_url.encode()).hexdigest()[:11]
    cached = cache_dir / f"{video_id}.m4a"

    if cached.exists() and cached.stat().st_size > 0:
        return str(cached)

    cmd = [
        "yt-dlp",
        "--format", "bestaudio",
        "--extract-audio",
        "--audio-format", "m4a",
        "--output", str(cache_dir / f"{video_id}.%(ext)s"),
    ]
    cookies_file = os.environ.get("YOUTUBE_COOKIES_FILE")
    if cookies_file and Path(cookies_file).exists():
        cmd += ["--cookies", cookies_file]
    cmd.append(song_url)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log.error("yt-dlp error for %s: %s", song_url, result.stderr[-300:])
        state.blacklist_song(song_url)
        return None

    if cached.exists() and cached.stat().st_size > 0:
        return str(cached)

    log.error("Audio file not found after yt-dlp for %s", song_url)
    return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Philosopher Instagram Pipeline")
    parser.add_argument("--now", action="store_true", help="Upload immediately instead of scheduling")
    parser.add_argument("--single", action="store_true", help="Process only the philosopher with the fewest posts")
    parser.add_argument("--generate-only", action="store_true", help="Generate reel but do not upload or schedule (saves to output/)")
    args = parser.parse_args()
    main(upload_now=args.now, single=args.single, generate_only=args.generate_only)

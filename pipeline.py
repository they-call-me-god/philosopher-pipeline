#!/usr/bin/env python3
"""
Philosopher Instagram Pipeline
Usage: python pipeline.py

Reads philosophers.md and songs.md, fetches a mix of Renaissance paintings
and writer portraits, and composes a fast-cut slideshow Reel for each
philosopher with a translucent @deepahhthinking watermark.
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
from fetcher import (
    fetch_quote, match_song, fetch_photo,
    fetch_paintings, fetch_portraits, get_bio,
)
from composer import compose_image, compose_reel, compose_frame, compose_slideshow
from scheduler import schedule_uploads
from uploader import upload_reel

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent
VAULT_DIR = BASE_DIR.parent

_local_philosophers = BASE_DIR / "philosophers.md"
PHILOSOPHERS_FILE = _local_philosophers if _local_philosophers.exists() else VAULT_DIR / "philosophers.md"

_local_songs = BASE_DIR / "songs.md"
SONGS_FILE = _local_songs if _local_songs.exists() else VAULT_DIR / "songs.md"
STATE_FILE = BASE_DIR / "state.json"
OUTPUT_DIR = BASE_DIR / "output"
CACHE_PHOTOS = BASE_DIR / "cache" / "photos"
CACHE_PAINTINGS = BASE_DIR / "cache" / "paintings"
CACHE_AUDIO = BASE_DIR / "cache" / "audio"
FONT_PATH = BASE_DIR / "fonts" / "PlayfairDisplay-Regular.ttf"

# Slideshow mix: 14 paintings + 10 writer portraits = 24 frames at 1.25s = 30s reel
NUM_PAINTINGS = 14
NUM_PORTRAITS = 10

RUN_ID = time.strftime("%Y-%m-%dT%H%M%S")


def _interleave(a, b):
    """Interleave two lists alternately, appending the longer tail at the end."""
    out = []
    i = 0
    while i < max(len(a), len(b)):
        if i < len(a):
            out.append(a[i])
        if i < len(b):
            out.append(b[i])
        i += 1
    return out


def main(upload_now=True, single=False, generate_only=False):
    for d in [OUTPUT_DIR, CACHE_PHOTOS, CACHE_PAINTINGS, CACHE_AUDIO]:
        d.mkdir(parents=True, exist_ok=True)

    if not FONT_PATH.exists():
        sys.exit(
            "[error] Font not found: " + str(FONT_PATH) + "\n"
            "Run: curl -L <playfair-url> -o " + str(FONT_PATH)
        )

    philosophers = parse_philosophers(PHILOSOPHERS_FILE)
    songs = parse_songs(SONGS_FILE)

    state = StateManager(STATE_FILE)
    state.load()

    blacklisted = set(state.get_blacklisted_songs())
    available_songs = [s for s in songs if s["url"] not in blacklisted]

    if not available_songs:
        sys.exit(
            "[error] No songs available after excluding " + str(len(blacklisted)) +
            " blacklisted URLs.\nAdd entries to " + str(SONGS_FILE)
        )
    if len(available_songs) < len(philosophers):
        log.warning(
            "Only %d songs for %d philosophers, songs will be reused across philosophers.",
            len(available_songs), len(philosophers),
        )

    log.info("Run ID: %s", RUN_ID)
    log.info("Processing %d philosophers...", len(philosophers))

    generated = []
    used_songs_this_run = []

    if single:
        philosophers = sorted(philosophers, key=lambda p: state.get_philosopher(p)["post_count"])[:1]
        log.info("Running in --single mode. Selected %s", philosophers[0])

    for philosopher in philosophers:
        log.info("== %s ==", philosopher)
        phil_state = state.get_philosopher(philosopher)

        # 1. Quote
        log.info("  Fetching quote...")
        try:
            quote_result = fetch_quote(philosopher, phil_state["used_quotes"])
        except Exception as e:
            log.warning("  Quote fetch failed for %s: %s, skipping.", philosopher, e)
            continue
        quote = quote_result["quote"]
        reframed = quote_result["reframed"]
        log.info("  Quote: %s...", quote[:60])

        # 2. Song match
        log.info("  Matching song...")
        try:
            song_url = match_song(
                philosopher, quote,
                songs=available_songs,
                used_in_run=used_songs_this_run,
                used_for_philosopher=phil_state["used_songs"],
            )
        except Exception as e:
            log.warning("  Song match failed for %s: %s, skipping.", philosopher, e)
            continue
        used_songs_this_run.append(song_url)
        log.info("  Song: %s", song_url)

        # 3. Fetch images (paintings + writer portraits)
        log.info("  Fetching %d Renaissance paintings + %d portraits of %s...",
                 NUM_PAINTINGS, NUM_PORTRAITS, philosopher)
        try:
            paintings = fetch_paintings(NUM_PAINTINGS, phil_state["used_photos"], CACHE_PAINTINGS)
        except Exception as e:
            log.warning("  Painting fetch error: %s", e)
            paintings = []
        try:
            portraits = fetch_portraits(philosopher, NUM_PORTRAITS, phil_state["used_photos"], CACHE_PHOTOS)
        except Exception as e:
            log.warning("  Portrait fetch error: %s", e)
            portraits = []

        if not paintings and not portraits:
            log.warning("  No images for %s, skipping.", philosopher)
            continue

        frames = _interleave(paintings, portraits)
        log.info("  Got %d frames (%d paintings + %d portraits)",
                 len(frames), len(paintings), len(portraits))

        # 4. Audio
        log.info("  Downloading audio...")
        audio_path = _download_audio(song_url, CACHE_AUDIO, state)
        if not audio_path:
            log.warning("  Audio download failed for %s, skipping.", philosopher)
            continue
        log.info("  Audio: %s", audio_path)

        # 5. Compose slideshow + cover thumbnail
        slug = _philosopher_slug(philosopher)
        mp4_path = str(OUTPUT_DIR / (slug + "-" + RUN_ID + ".mp4"))
        cover_jpg = str(OUTPUT_DIR / (slug + "-" + RUN_ID + ".jpg"))

        log.info("  Composing slideshow reel...")
        try:
            compose_slideshow(
                frames, quote, philosopher,
                audio_path, mp4_path, str(FONT_PATH),
            )
        except Exception as e:
            log.warning("  Slideshow composition failed for %s: %s, skipping.", philosopher, e)
            continue

        try:
            compose_frame(frames[0], quote, philosopher, cover_jpg, str(FONT_PATH))
        except Exception as e:
            log.warning("  Cover thumbnail failed for %s: %s (using mp4 only)", philosopher, e)
            cover_jpg = None

        if not Path(mp4_path).exists() or Path(mp4_path).stat().st_size == 0:
            log.warning("  Reel file missing or empty for %s, skipping.", philosopher)
            continue

        # 6. State update (record all painting + portrait filenames used)
        all_filenames = [Path(p).name for p in (paintings + portraits)]
        state.update_philosopher(philosopher, quote, song_url, all_filenames, reframed)
        log.info("  State updated.")

        # 7. Caption with author bio
        bio = get_bio(philosopher)
        slug_tag = slug.replace("-", "")[:20]
        caption_parts = ['"' + quote + '"', "- " + philosopher]
        if bio:
            caption_parts.append(bio)
        caption_parts.append(
            "#philosophy #quotes #wisdom #renaissance #art #deepthoughts "
            "#philosophyquotes #mindset #existentialism #stoicism #motivation "
            "#" + slug_tag + " #thinkers #lifequotes #intellectuals "
            "#classicquotes #deepquotes #renaissanceart #classicalart"
        )
        caption = "\n\n".join(caption_parts)

        generated.append({
            "philosopher": philosopher,
            "mp4_path": mp4_path,
            "jpg_path": cover_jpg,
            "caption": caption,
        })
        log.info("  Reel ready: %s", mp4_path)

    if not generated:
        log.warning("No reels generated. Exiting.")
        return

    if generate_only:
        log.info("--generate-only: %d reel(s) saved to output/, skipping upload.", len(generated))
        for reel in generated:
            log.info("  Ready: %s", reel["mp4_path"])
    elif upload_now:
        log.info("Uploading %d reels immediately...", len(generated))
        for reel in generated:
            log.info("  Uploading %s...", reel["philosopher"])
            try:
                upload_reel(reel["mp4_path"], reel["caption"], reel.get("jpg_path"))
                log.info("  Uploaded %s", reel["philosopher"])
            except Exception as e:
                log.error("  Upload failed for %s: %s", reel["philosopher"], e)
    else:
        log.info("Scheduling %d reels...", len(generated))
        schedule_uploads(generated, upload_reel)


def _philosopher_slug(name: str) -> str:
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


def _download_audio(song_url, cache_dir, state):
    import re
    import subprocess

    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", song_url)
    video_id = match.group(1) if match else hashlib.md5(song_url.encode()).hexdigest()[:11]
    cached = cache_dir / (video_id + ".m4a")

    if cached.exists() and cached.stat().st_size > 0:
        return str(cached)

    cmd = [
        "yt-dlp",
        "--format", "bestaudio",
        "--extract-audio",
        "--audio-format", "m4a",
        "--output", str(cache_dir / (video_id + ".%(ext)s")),
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
    parser.add_argument("--schedule", action="store_true", help="Schedule uploads at optimal times instead of uploading immediately")
    parser.add_argument("--single", action="store_true", help="Process only the philosopher with the fewest posts")
    parser.add_argument("--generate-only", action="store_true", help="Generate reel but do not upload (saves to output/)")
    args = parser.parse_args()
    main(upload_now=not args.schedule, single=args.single, generate_only=args.generate_only)

"""
Philosopher Pipeline — automated Instagram Reel factory.

Flow per philosopher:
  Claude quote → Wikimedia portrait → Claude song match →
  Pillow B&W image → yt-dlp audio → FFmpeg 30s MP4 → instagrapi upload

Usage:
  python pipeline.py            # run all philosophers
  python pipeline.py --single   # run least-posted philosopher only
"""
import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from input_parser import parse_philosophers, parse_songs
from state import State
from fetcher import fetch_quote, fetch_portrait, match_song
from composer import compose_reel
from uploader import upload_reel

load_dotenv()

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "run_log.txt", encoding="utf-8"),
    ],
)
# Fix Windows console encoding
import sys
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
log = logging.getLogger(__name__)


def _find_peak_offset(audio_path: Path, clip_len: int = 30, step: int = 5) -> int:
    """Return the start second of the loudest 30s window using ffmpeg volumedetect."""
    # Get total duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True,
    )
    try:
        total = float(probe.stdout.strip())
    except ValueError:
        return 0

    # Skip first 15s (intros) and last 30s (outros)
    search_start = 15
    search_end = max(search_start + clip_len, int(total) - clip_len - 15)
    if search_end <= search_start:
        return search_start

    best_offset, best_vol = search_start, -999.0
    for start in range(search_start, search_end, step):
        r = subprocess.run(
            ["ffmpeg", "-ss", str(start), "-t", str(clip_len),
             "-i", str(audio_path),
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        for line in r.stderr.splitlines():
            if "mean_volume" in line:
                try:
                    vol = float(line.split(":")[-1].strip().replace(" dB", ""))
                    if vol > best_vol:
                        best_vol, best_offset = vol, start
                except ValueError:
                    pass
    log.info("Peak audio window: %ds (%.1f dB mean)", best_offset, best_vol)
    return best_offset


def download_audio(song_url: str, output_dir: Path, filename: str) -> Path:
    """Download full audio from YouTube via yt-dlp (cached)."""
    output_path = output_dir / f"{filename}.m4a"
    if output_path.exists():
        log.info("Audio cache hit: %s", filename)
        return output_path
    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "m4a",
        "-o", str(output_path),
        "--no-playlist",
        song_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[-300:]}")
    return output_path


def create_video(image_path: Path, audio_path: Path, output_path: Path, duration: int = 30) -> Path:
    """Combine still image + best 30s of audio into an MP4 via FFmpeg."""
    start = _find_peak_offset(audio_path, clip_len=duration)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-ss", str(start), "-t", str(duration), "-i", str(audio_path),
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        "-vf", f"scale={1080}:{1920}",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-300:]}")
    return output_path


def run_pipeline(single: bool = False) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    CACHE_PHOTOS.mkdir(parents=True, exist_ok=True)
    CACHE_AUDIO.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("[error] GROQ_API_KEY not set. Add it to .env")

    client = Groq(api_key=api_key)
    state = State(STATE_FILE)

    philosophers = parse_philosophers(PHILOSOPHERS_FILE)
    songs = parse_songs(SONGS_FILE)

    blacklisted = set(state.get_blacklisted_songs())
    available_songs = [s for s in songs if s["url"] not in blacklisted]

    if len(available_songs) < len(philosophers):
        log.warning(
            "[warn] Need at least %d songs, only %d available after excluding %d blacklisted.",
            len(philosophers), len(available_songs), len(blacklisted),
        )

    log.info("Processing %d philosophers...", len(philosophers))

    if single:
        philosophers = sorted(philosophers, key=lambda p: state.get_philosopher(p)["post_count"])[:1]
        log.info("Running in --single mode. Selected %s", philosophers[0])

    used_songs_this_run: list[str] = []

    # Collect all quotes ever used across every philosopher to prevent duplicates
    all_used_quotes: list[str] = []
    for p in philosophers:
        all_used_quotes.extend(state.get_philosopher(p)["used_quotes"])

    for philosopher in philosophers:
        phil_state = state.get_philosopher(philosopher)
        try:
            log.info("--- %s ---", philosopher)

            quote = fetch_quote(
                philosopher=philosopher,
                used_quotes=all_used_quotes,
                client=client,
            )
            log.info("Quote: %s", quote[:100])

            portrait_path, photo_id = fetch_portrait(
                philosopher=philosopher,
                used_photos=phil_state["used_photos"],
                cache_dir=CACHE_PHOTOS,
            )

            song = match_song(
                philosopher=philosopher,
                quote=quote,
                available_songs=available_songs,
                used_in_run=used_songs_this_run,
                used_for_philosopher=phil_state["used_songs"],
                client=client,
            )
            log.info("Song: %s", song["label"][:80])

            safe_name = philosopher.lower().replace(" ", "_")
            image_path = compose_reel(
                photo_path=portrait_path,
                quote=quote,
                philosopher=philosopher,
                font_path=FONT_PATH,
                output_path=OUTPUT_DIR / f"{safe_name}_reel.jpg",
            )

            audio_path = download_audio(
                song_url=song["url"],
                output_dir=CACHE_AUDIO,
                filename=safe_name,
            )

            video_path = create_video(
                image_path=image_path,
                audio_path=audio_path,
                output_path=OUTPUT_DIR / f"{safe_name}_reel.mp4",
            )

            upload_reel(
                video_path=video_path,
                caption=(
                    f'"{quote}"\n— {philosopher}\n\n'
                    f'#philosophy #quotes #wisdom #aesthetic #deepthoughts '
                    f'#philosophyquotes #quotestoliveby #mindset #intellectuals '
                    f'#ancient #stoic #stoicism #existentialism #deepquotes '
                    f'#motivationalquotes #inspiration #philosophyoflife '
                    f'#wordsofwisdom #quoteoftheday #thinkers #intellectualbeauty '
                    f'#darkacademia #booktok #aesthetic #poetryofinstagram'
                ),
            )

            all_used_quotes.append(quote)
            state.mark_posted(
                philosopher=philosopher,
                quote=quote,
                song_url=song["url"],
                photo_id=photo_id,
            )
            used_songs_this_run.append(song["url"])
            log.info("✓ Posted for %s", philosopher)

        except Exception as exc:
            log.error("[FAILED] %s: %s", philosopher, exc, exc_info=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Philosopher Instagram Reel Pipeline")
    parser.add_argument("--single", action="store_true", help="Only process the least-posted philosopher")
    args = parser.parse_args()
    run_pipeline(single=args.single)


if __name__ == "__main__":
    main()

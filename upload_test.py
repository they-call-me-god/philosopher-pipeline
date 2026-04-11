#!/usr/bin/env python3
"""
Quick test uploader — uploads the 2 most recent generated reels immediately.
Run: python upload_test.py
"""
import json
import os
from pathlib import Path

# Load .env
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from uploader import upload_reel

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
STATE_FILE = BASE_DIR / "state.json"

# ── Load state for captions ───────────────────────────────────────────────────
state = json.loads(STATE_FILE.read_text())

def slug_to_name(slug: str) -> str:
    """Best-effort reverse of the slug: 'marcus-aurelius' → 'Marcus Aurelius'"""
    return " ".join(w.capitalize() for w in slug.split("-"))

def get_caption(philosopher: str, quote: str) -> str:
    slug_tag = philosopher.lower().replace(" ", "").replace("-", "")[:20]
    return (
        f'"{quote}"\n\n'
        f"— {philosopher}\n\n"
        f"#philosophy #quotes #wisdom #deepthoughts #philosophyquotes "
        f"#mindset #existentialism #stoicism #motivation ##{slug_tag} "
        f"#thinkers #lifequotes #intellectuals #classicquotes #deepquotes"
    )

# ── Pick 2 most recent MP4s ───────────────────────────────────────────────────
all_mp4s = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
targets = all_mp4s[:2]

print(f"Uploading {len(targets)} reels...\n")

for mp4 in targets:
    # e.g. "marcus-aurelius-2026-03-18T223235"
    stem_parts = mp4.stem.rsplit("-", 3)  # split off the timestamp
    slug = "-".join(stem_parts[:-1]) if len(stem_parts) > 1 else mp4.stem
    philosopher = slug_to_name(slug)

    # Get last used quote from state
    phil_state = state.get(philosopher, {})
    used_quotes = phil_state.get("used_quotes", [])
    quote = used_quotes[-1] if used_quotes else f"The unexamined life is not worth living."

    caption = get_caption(philosopher, quote)
    jpg = mp4.with_suffix(".jpg")
    thumbnail = str(jpg) if jpg.exists() else None

    print(f"  > {philosopher}")
    print(f"    Quote: {quote[:70]}...")
    print(f"    File:  {mp4.name}")
    try:
        upload_reel(str(mp4), caption, thumbnail)
        print(f"    OK UPLOADED\n")
    except Exception as e:
        print(f"    FAILED: {e}\n")

print("Done.")

"""Parse philosophers.md and songs.md input files."""
import sys
from pathlib import Path


def parse_philosophers(path: Path) -> list[str]:
    if not path.exists():
        sys.exit(f"[error] philosophers.md not found at: {path}")
    philosophers = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.lstrip("- ").strip()
        if name:
            philosophers.append(name)
    return philosophers


def parse_songs(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"[error] songs.md not found at: {path}")
    songs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("- http"):
            continue
        line = line.lstrip("- ").strip()
        # Format: <url>  # <label>
        if "  #" in line:
            url, label = line.split("  #", 1)
        elif " # " in line:
            url, label = line.split(" # ", 1)
        else:
            continue
        songs.append({"url": url.strip(), "label": label.strip()})
    return songs

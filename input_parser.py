import sys
from pathlib import Path


def parse_philosophers(path: Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        sys.exit(f"[error] philosophers.md not found at: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    names = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            name = line[2:].strip()
            if name and name not in seen:
                names.append(name)
                seen.add(name)
    if not names:
        sys.exit(f"[error] philosophers.md is empty or has no valid entries: {path}")
    return names


def parse_songs(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        sys.exit(f"[error] songs.md not found at: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    songs = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            content = line[2:].strip()
            # Skip placeholder lines
            if content.startswith("#") or "paste link here" in content:
                continue
            if "#" in content:
                url_part, label_part = content.split("#", 1)
                url = url_part.strip()
                label = label_part.strip()
            else:
                url = content.strip()
                label = ""
            if url.startswith("http"):
                songs.append({"url": url, "label": label})
    return songs

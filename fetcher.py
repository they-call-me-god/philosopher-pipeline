"""Fetch quotes via Claude, portraits via Wikimedia, match songs via Claude."""
import hashlib
import logging
import re
from pathlib import Path

import anthropic
import requests

log = logging.getLogger(__name__)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
MODEL = "claude-haiku-4-5-20251001"


def fetch_quote(philosopher: str, used_quotes: list[str], client: anthropic.Anthropic) -> str:
    """Generate an authentic-sounding quote in the philosopher's style."""
    used_block = "\n".join(f"- {q}" for q in used_quotes) if used_quotes else "(none)"
    prompt = (
        f"Generate a single powerful, authentic-sounding philosophical quote "
        f"in the style of {philosopher}. It should feel like something they actually "
        f"wrote — concise, profound, characteristic.\n"
        f"Do NOT use these already-used quotes:\n{used_block}\n"
        f"Reply with ONLY the quote text, no quotation marks, no attribution."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip().strip('"').strip("'")


def fetch_portrait(philosopher: str, used_photos: list[str], cache_dir: Path) -> tuple[Path, str]:
    """Fetch a portrait from Wikimedia Commons. Returns (local_path, photo_id)."""
    for query in [f"File:{philosopher} portrait", philosopher]:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "gsrlimit": "20",
        }
        resp = requests.get(WIKIMEDIA_API, params=params, timeout=15)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {}).values()

        for page in pages:
            info = page.get("imageinfo", [{}])[0]
            url = info.get("url", "")
            mime = info.get("mime", "")
            if mime not in ("image/jpeg", "image/png") or not url:
                continue
            photo_id = hashlib.md5(url.encode()).hexdigest()[:16]
            if photo_id in used_photos:
                continue
            local_path = cache_dir / f"{photo_id}.jpg"
            if not local_path.exists():
                img_resp = requests.get(url, timeout=30)
                img_resp.raise_for_status()
                local_path.write_bytes(img_resp.content)
                log.info("Downloaded portrait %s for %s", photo_id, philosopher)
            return local_path, photo_id

    raise RuntimeError(f"No unused portrait found for {philosopher}")


def match_song(
    philosopher: str,
    quote: str,
    available_songs: list[dict],
    used_in_run: list[str],
    used_for_philosopher: list[str],
    client: anthropic.Anthropic,
) -> dict:
    """Use Claude to pick the best-vibe song for this philosopher + quote."""
    candidates = [
        s for s in available_songs
        if s["url"] not in used_in_run and s["url"] not in used_for_philosopher
    ]
    if not candidates:
        candidates = [s for s in available_songs if s["url"] not in used_in_run]
    if not candidates:
        candidates = list(available_songs)

    song_list = "\n".join(f"{i + 1}. {s['label']}" for i, s in enumerate(candidates))
    prompt = (
        f"Philosopher: {philosopher}\n"
        f'Quote: "{quote}"\n\n'
        f"Pick the song number (1–{len(candidates)}) whose emotional and aesthetic vibe "
        f"best matches this philosopher and quote:\n{song_list}\n\n"
        f"Reply with ONLY the number."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    try:
        idx = int(re.search(r"\d+", raw).group()) - 1
        idx = max(0, min(idx, len(candidates) - 1))
    except (AttributeError, ValueError):
        idx = 0
    return candidates[idx]

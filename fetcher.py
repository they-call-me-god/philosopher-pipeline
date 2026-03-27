"""Fetch quotes via Groq, portraits via Wikimedia, match songs via Groq."""
import hashlib
import logging
import os
import re
from pathlib import Path

import requests
from groq import Groq

log = logging.getLogger(__name__)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_HEADERS = {"User-Agent": "philosopher-pipeline/1.0 (contact: github.com/they-call-me-god)"}
MODEL = "llama-3.3-70b-versatile"


def _client() -> Groq:
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def fetch_quote(philosopher: str, used_quotes: list[str], client: Groq) -> str:
    """Generate an authentic-sounding quote in the philosopher's style."""
    used_block = "\n".join(f"- {q}" for q in used_quotes) if used_quotes else "(none)"
    prompt = (
        f"Write a quote in the style of {philosopher} that hits like these examples:\n"
        f'- "Common sense is not so common." (Voltaire)\n'
        f'- "There is infinite hope, but not for us." (Kafka)\n\n'
        f"Rules:\n"
        f"- Under 12 words\n"
        f"- One sentence, no comma lists\n"
        f"- Must have a twist, reversal, or paradox at the end\n"
        f"- Sounds like {philosopher} — their actual themes and vocabulary\n"
        f"- No clichés, no filler words like 'truly' or 'deeply'\n"
        f"Do NOT use these already-used quotes:\n{used_block}\n"
        f"Reply with ONLY the quote. Nothing else."
    )
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip().strip('"').strip("'")


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
        resp = requests.get(WIKIMEDIA_API, params=params, headers=WIKIMEDIA_HEADERS, timeout=15)
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
                img_resp = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=30)
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
    client: Groq,
) -> dict:
    """Use Groq to pick the best-vibe song for this philosopher + quote."""
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
        f"Pick the song number (1-{len(candidates)}) whose emotional and aesthetic vibe "
        f"best matches this philosopher and quote:\n{song_list}\n\n"
        f"Reply with ONLY the number."
    )
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()
    try:
        idx = int(re.search(r"\d+", raw).group()) - 1
        idx = max(0, min(idx, len(candidates) - 1))
    except (AttributeError, ValueError):
        idx = 0
    return candidates[idx]

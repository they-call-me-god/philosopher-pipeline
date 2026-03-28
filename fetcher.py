"""Fetch quotes via Groq, portraits via Wikimedia, match songs via Groq."""
import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from groq import Groq

_CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}

log = logging.getLogger(__name__)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_HEADERS = {"User-Agent": "philosopher-pipeline/1.0 (contact: github.com/they-call-me-god)"}
MODEL = "llama-3.3-70b-versatile"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def _client() -> Groq:
    return Groq(api_key=os.environ["GROQ_API_KEY"])


# ── Quote ──────────────────────────────────────────────────────────────────────

def fetch_quote(philosopher: str, used_quotes: list[str], client: Groq) -> str:
    """Generate a short paradoxical quote in the philosopher's style."""
    used_block = "\n".join(f"- {q}" for q in used_quotes) if used_quotes else "(none)"
    cfg = _load_config()
    style_hint = cfg.get("quote_style_hint", "")
    extra = f"\nAdditional style guidance from performance data:\n{style_hint}\n" if style_hint else ""
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
        f"{extra}"
        f"Do NOT use these already-used quotes:\n{used_block}\n"
        f"Reply with ONLY the quote. Nothing else."
    )
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip().strip('"').strip("'")


# ── Portrait ───────────────────────────────────────────────────────────────────

def _last_name(philosopher: str) -> str:
    return philosopher.strip().split()[-1].lower()


def _verify_portrait(image_path: Path, philosopher: str, client: Groq) -> bool:
    """Use Groq vision to confirm image is a human portrait, not text/map/object."""
    try:
        img_b64 = base64.b64encode(image_path.read_bytes()).decode()
        response = client.chat.completions.create(
            model=VISION_MODEL,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Does this image show a clear human face or portrait of a person? "
                            f"It should NOT be a book, manuscript, map, painting of text, statue, "
                            f"or building. Answer only YES or NO."
                        ),
                    },
                ],
            }],
        )
        answer = response.choices[0].message.content.strip().upper()
        ok = answer.startswith("YES")
        if not ok:
            log.warning("Portrait rejected by vision check (%s): %s", philosopher, answer)
        return ok
    except Exception as exc:
        log.warning("Vision check failed (%s), accepting portrait anyway: %s", philosopher, exc)
        return True  # don't block on API errors


def fetch_portrait(
    philosopher: str,
    used_photos: list[str],
    cache_dir: Path,
    client: Groq | None = None,
) -> tuple[Path, str]:
    """Fetch a portrait from Wikimedia Commons. Returns (local_path, photo_id)."""
    last = _last_name(philosopher)
    queries = [
        f"File:{philosopher}",
        f"{philosopher} portrait",
        philosopher,
    ]
    bad_keywords = (
        "manuscrit", "manuscript", "lettre", "letter", "signature",
        "autograph", "handwriting", "book", "page", "text", "writing",
        "map", "diagram", "chart", "tableau", "table", "schema",
        "gravure", "engraving", "statue", "bust", "plaque", "monument",
        "house", "birth", "home", "building", "church", "tomb", "grave",
    )
    for query in queries:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "gsrlimit": "30",
        }
        resp = requests.get(WIKIMEDIA_API, params=params, headers=WIKIMEDIA_HEADERS, timeout=15)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {}).values()

        for page in pages:
            title = page.get("title", "").lower()
            if last not in title:
                continue
            if any(kw in title for kw in bad_keywords):
                continue
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
                for attempt in range(3):
                    img_resp = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=30)
                    if img_resp.status_code == 429:
                        wait = 5 * (attempt + 1)
                        log.warning("Wikimedia 429 — waiting %ds", wait)
                        time.sleep(wait)
                        continue
                    img_resp.raise_for_status()
                    break
                else:
                    log.warning("Skipping portrait %s — rate limited", photo_id)
                    continue
                local_path.write_bytes(img_resp.content)
                log.info("Downloaded portrait %s for %s", photo_id, philosopher)
            # Vision check — skip if it's not actually a face
            if client and not _verify_portrait(local_path, philosopher, client):
                used_photos = list(used_photos) + [photo_id]  # skip this one
                continue
            return local_path, photo_id

    raise RuntimeError(f"No unused portrait found for {philosopher}")


# ── Song ───────────────────────────────────────────────────────────────────────

BANNED_SONG_TITLES = {
    "metamorphosis", "snowfall",
}


def get_song_real_title(url: str) -> str:
    """Fetch the actual YouTube video title via yt-dlp without downloading."""
    try:
        r = subprocess.run(
            ["yt-dlp", "--no-playlist", "--print", "title", url],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.strip().lower() if r.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        log.warning("Timed out fetching title for %s — skipping title check", url)
        return ""


def match_song(
    philosopher: str,
    quote: str,
    available_songs: list[dict],
    used_in_run: list[str],
    used_for_philosopher: list[str],
    client: Groq,
    state=None,
) -> dict:
    """Use Groq to pick the best-vibe song; auto-blacklists any with banned titles."""
    candidates = [
        s for s in available_songs
        if s["url"] not in used_in_run and s["url"] not in used_for_philosopher
    ]
    if not candidates:
        candidates = [s for s in available_songs if s["url"] not in used_in_run]
    if not candidates:
        candidates = list(available_songs)

    # Try up to len(candidates) times — skip any that fail the title check
    tried: set[str] = set()
    while True:
        remaining = [s for s in candidates if s["url"] not in tried]
        if not remaining:
            raise RuntimeError(f"No valid songs left for {philosopher} after title checks")

        song_list = "\n".join(f"{i + 1}. {s['label']}" for i, s in enumerate(remaining))
        prompt = (
            f"Philosopher: {philosopher}\n"
            f'Quote: "{quote}"\n\n'
            f"Pick the song number (1-{len(remaining)}) whose emotional and aesthetic vibe "
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
            idx = max(0, min(idx, len(remaining) - 1))
        except (AttributeError, ValueError):
            idx = 0

        song = remaining[idx]

        # Verify the real title doesn't contain banned words
        real_title = get_song_real_title(song["url"])
        log.info("Song real title: '%s'", real_title)
        if any(banned in real_title for banned in BANNED_SONG_TITLES):
            log.warning("Auto-blacklisting '%s' (%s) — banned title match", real_title, song["url"])
            if state:
                state.blacklist_song(song["url"])
            tried.add(song["url"])
            continue

        return song

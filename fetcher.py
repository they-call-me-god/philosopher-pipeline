import ctypes
import hashlib
import logging
import sys
import time
import requests
from pathlib import Path

_FILE_ATTRIBUTE_OFFLINE = 0x1000
_FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
_IS_WINDOWS = sys.platform == "win32"


def _is_cloud_only(path: Path) -> bool:
    """Return True if the file is an OneDrive cloud-only placeholder (not locally synced).
    Always returns False on non-Windows platforms."""
    if not _IS_WINDOWS:
        return False
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == -1:
        return True
    return bool(attrs & (_FILE_ATTRIBUTE_OFFLINE | _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS))


log = logging.getLogger(__name__)


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "PhilosopherPipeline/1.0 (instagram-content-bot; python-requests)"}

# Hardcoded quotes per philosopher (cycles across runs, no API needed)
PHILOSOPHER_QUOTES = {
    "albert camus": [
        "In the midst of winter, I found there was, within me, an invincible summer.",
        "You will never be happy if you continue to search for what happiness consists of.",
        "Don't walk in front of me — I may not follow. Don't walk behind me — I may not lead. Walk beside me — just be my friend.",
        "The only way to deal with an unfree world is to become so absolutely free that your very existence is an act of rebellion.",
        "I rebel; therefore I exist.",
        "Man is the only creature who refuses to be what he is.",
        "In the depth of winter, I finally learned that within me there lay an invincible summer.",
    ],
    "fyodor dostoevsky": [
        "Pain and suffering are always inevitable for a large intelligence and a deep heart.",
        "The mystery of human existence lies not in just staying alive, but in finding something to live for.",
        "To love someone means to see them as God intended them.",
        "Beauty will save the world.",
        "If you want to be respected by others, the great thing is to respect yourself.",
        "Above all, don't lie to yourself. The man who lies to himself and listens to his own lie comes to a point where he cannot distinguish the truth.",
    ],
    "franz kafka": [
        "There is infinite hope, but not for us.",
        "A book must be the axe for the frozen sea within us.",
        "I am a cage, in search of a bird.",
        "In the struggle between yourself and the world, second the world.",
        "Start with what is right rather than what is acceptable.",
        "Don't bend; don't water it down; don't try to make it logical; don't edit your own soul according to the fashion.",
    ],
    "voltaire": [
        "Common sense is not so common.",
        "Judge a man by his questions rather than his answers.",
        "The art of medicine consists in amusing the patient while nature cures the disease.",
        "Think for yourself and let others enjoy the privilege of doing so too.",
        "It is dangerous to be right in matters on which the established authorities are wrong.",
        "God is a comedian playing to an audience that is too afraid to laugh.",
    ],
    "friedrich nietzsche": [
        "He who has a why to live can bear almost any how.",
        "Without music, life would be a mistake.",
        "That which does not kill us, makes us stronger.",
        "In individuals, insanity is rare; but in groups, parties, nations and epochs, it is the rule.",
        "To live is to suffer; to survive is to find some meaning in the suffering.",
        "One must still have chaos in oneself to be able to give birth to a dancing star.",
    ],
    "simone de beauvoir": [
        "One is not born, but rather becomes, a woman.",
        "Change your life today. Don't gamble on the future, act now, without delay.",
        "I am awfully greedy; I want everything from life.",
        "One's life has value so long as one attributes value to the life of others.",
        "The most mediocre of males feels himself a demigod as compared with women.",
        "Representation of the world, like the world itself, is the work of men; they describe it from their own point of view.",
    ],
    "søren kierkegaard": [
        "Life can only be understood backwards; but it must be lived forwards.",
        "The most common form of despair is not being who you are.",
        "Once you label me you negate me.",
        "Anxiety is the dizziness of freedom.",
        "People demand freedom of speech as a compensation for the freedom of thought which they seldom use.",
        "Face the facts of being what you are, for that is what changes what you are.",
    ],
    "arthur schopenhauer": [
        "Talent hits a target no one else can hit; genius hits a target no one else can see.",
        "A man can do what he wants, but not want what he wants.",
        "Compassion is the basis of morality.",
        "The person who writes for fools is always sure of a large audience.",
        "It is difficult to find happiness within oneself, but it is impossible to find it anywhere else.",
        "We forfeit three-fourths of ourselves in order to be like other people.",
    ],
    "marcus aurelius": [
        "You have power over your mind, not outside events. Realize this, and you will find strength.",
        "The impediment to action advances action. What stands in the way becomes the way.",
        "Very little is needed to make a happy life; it is all within yourself, in your way of thinking.",
        "Waste no more time arguing about what a good man should be. Be one.",
        "The best revenge is to be unlike him who performed the injustice.",
        "Accept the things to which fate binds you, and love the people with whom fate brings you together.",
    ],
    "immanuel kant": [
        "Act only according to that maxim whereby you can at the same time will that it should become a universal law.",
        "Two things fill the mind with ever new and increasing admiration and awe: the starry heavens above me and the moral law within me.",
        "Happiness is not an ideal of reason, but of imagination.",
        "Science is organized knowledge. Wisdom is organized life.",
        "Out of the crooked timber of humanity, no straight thing was ever made.",
        "Seek not the favor of the multitude; it is seldom got by honest and lawful means.",
    ],
    "jean-paul sartre": [
        "Existence precedes essence.",
        "Hell is other people.",
        "Man is condemned to be free; because once thrown into the world, he is responsible for everything he does.",
        "Words are loaded pistols.",
        "Life has no meaning the moment you lose the illusion of being eternal.",
        "Everything has been figured out, except how to live.",
    ],
    "blaise pascal": [
        "The heart has its reasons which reason knows nothing of.",
        "Man's greatness lies in his power of thought.",
        "All of humanity's problems stem from man's inability to sit quietly in a room alone.",
        "We are generally the better persuaded by the reasons we discover ourselves than by those given to us by others.",
        "There is a God-shaped vacuum in the heart of each man which cannot be satisfied by any created thing.",
        "Kind words do not cost much. Yet they accomplish much.",
    ],
}

# Vibe keywords per philosopher — used for song matching without AI
PHILOSOPHER_VIBES = {
    "albert camus":         ["existential", "melancholic", "absurd", "rebellion", "dark", "atmospheric"],
    "fyodor dostoevsky":    ["dark", "heavy", "suffering", "crushing", "slowed", "sorrowful", "aggressive"],
    "franz kafka":          ["anxious", "eerie", "surreal", "ominous", "haunting", "cold"],
    "voltaire":             ["ironic", "cynical", "dominant", "punchy", "absurd", "wit"],
    "friedrich nietzsche":  ["dominant", "aggressive", "powerful", "intense", "dark", "relentless"],
    "simone de beauvoir":   ["atmospheric", "ethereal", "cinematic", "melancholic", "drift"],
    "søren kierkegaard":    ["melancholic", "contemplative", "sorrowful", "nostalgic", "ethereal"],
    "arthur schopenhauer":  ["crushing", "heavy", "sorrowful", "dark", "slowed", "pessimistic"],
    "marcus aurelius":      ["dominant", "stoic", "resolute", "mechanical", "cold", "powerful"],
    "immanuel kant":        ["cold", "mechanical", "precise", "cinematic", "atmospheric"],
    "jean-paul sartre":     ["dark", "eerie", "existential", "nocturnal", "hypnotic"],
    "blaise pascal":        ["ethereal", "nostalgic", "contemplative", "spiritual", "cinematic"],
}


def fetch_quote(philosopher: str, used_quotes: list[str]) -> dict:
    """
    Returns {"quote": str, "reframed": bool}
    Uses hardcoded curated quotes — no API key required.
    """
    all_quotes = PHILOSOPHER_QUOTES.get(philosopher.lower(), [])
    used_set = set(used_quotes)
    fresh = [q for q in all_quotes if q not in used_set]

    if fresh:
        return {"quote": fresh[0], "reframed": False}
    # All used — cycle back to start
    if all_quotes:
        return {"quote": all_quotes[0], "reframed": True}
    return {"quote": "The unexamined life is not worth living.", "reframed": True}


def match_song(
    philosopher: str,
    quote: str,
    songs: list[dict],
    used_in_run: list[str],
    used_for_philosopher: list[str],
) -> str:
    """Returns the YouTube URL of the best vibe match using keyword overlap."""
    last_3_used = set(used_for_philosopher[-3:])
    run_used = set(used_in_run)

    available = [s for s in songs
                 if s["url"] not in run_used and s["url"] not in last_3_used]
    if not available:
        available = [s for s in songs if s["url"] not in run_used]
    if not available:
        available = songs

    # Score each song by keyword overlap with philosopher's known vibes
    vibes = PHILOSOPHER_VIBES.get(philosopher.lower(), [])

    def score(song: dict) -> int:
        label_words = song["label"].lower().split()
        return sum(1 for v in vibes if any(v in w for w in label_words))

    ranked = sorted(available, key=score, reverse=True)
    return ranked[0]["url"]


def fetch_photo(philosopher: str, used_photos: list[str], cache_dir: Path) -> str | None:
    """Downloads a Wikimedia portrait. Returns local file path or None.

    Falls back to any already-cached photo for this philosopher if Wikimedia
    rate-limits us (429) or no fresh photo is available.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    slug = philosopher.lower().replace(" ", "-")

    try:
        search_params = {
            "action": "query", "list": "search", "format": "json",
            "srnamespace": "6",
            "srsearch": f"{philosopher} portrait",
            "srlimit": "20",
        }
        time.sleep(1)  # be polite to Wikimedia
        resp = requests.get(WIKIMEDIA_API, params=search_params, timeout=30, headers=HEADERS)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])

        for item in results:
            title = item["title"]
            if not any(title.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                continue
            if any(skip in title.lower() for skip in [
                "svg", "flag", "coat", "seal", "map",
                "collage", "comparison", "composite", "group",
                "versus", "_vs_", "bust", "statue", "memorial",
                "caricature", "cartoon", "drawing", "illustration",
            ]):
                continue

            info_params = {
                "action": "query", "titles": title, "prop": "imageinfo",
                "iiprop": "url|size", "format": "json",
            }
            time.sleep(0.5)
            info_resp = requests.get(WIKIMEDIA_API, params=info_params, timeout=30, headers=HEADERS)
            info_resp.raise_for_status()
            pages = info_resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                infos = page.get("imageinfo", [])
                if not infos:
                    continue
                info = infos[0]
                url = info["url"]
                w, h = info.get("width", 0), info.get("height", 0)

                if w < 600 or h < 600:
                    continue
                if w > h:
                    continue

                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f"{slug}-{url_hash}.jpg"

                if filename in used_photos:
                    continue

                cached = cache_dir / filename
                if not cached.exists() or cached.stat().st_size == 0:
                    time.sleep(0.5)
                    img_resp = requests.get(url, timeout=30, headers=HEADERS)
                    img_resp.raise_for_status()
                    cached.write_bytes(img_resp.content)

                if _is_cloud_only(cached):
                    log.warning("Skipping cloud-only cached photo: %s", filename)
                    continue

                return str(cached)

    except Exception as e:
        log.warning("Wikimedia fetch failed for %s: %s — using cache fallback.", philosopher, e)

    # Fallback: reuse any cached photo for this philosopher (prefer unused ones)
    cached_photos = sorted(cache_dir.glob(f"{slug}-*.jpg"))
    for p in cached_photos:
        if p.name not in used_photos and p.stat().st_size > 0 and not _is_cloud_only(p):
            return str(p)
    # Last resort: any cached photo even if used before
    for p in cached_photos:
        if p.stat().st_size > 0 and not _is_cloud_only(p):
            return str(p)

    return None

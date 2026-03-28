"""
Self-optimization loop for the philosopher pipeline.

Fetches Instagram metrics for every posted reel, analyzes performance with Groq,
and rewrites config.json with actionable improvements to quotes, songs, and hashtags.

Usage:
    python optimizer.py          # analyze all posts, update config.json
    python optimizer.py --dry    # print analysis without writing config
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
CONFIG_FILE = BASE_DIR / "config.json"
PERF_FILE = BASE_DIR / "performance.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

MODEL = "llama-3.3-70b-versatile"
MIN_POSTS_REQUIRED = 3  # don't optimize until we have enough data


def fetch_metrics(posts: list[dict]) -> list[dict]:
    """Fetch play_count, like_count, comment_count from Instagram for each post."""
    from instagrapi import Client

    username = os.environ.get("INSTAGRAM_USERNAME", "")
    password = os.environ.get("INSTAGRAM_PASSWORD", "")
    session_file = BASE_DIR / "session.json"

    cl = Client()
    try:
        if session_file.exists():
            cl.load_settings(session_file)
        cl.login(username, password)
        cl.dump_settings(session_file)
    except Exception as exc:
        log.error("Instagram login failed: %s", exc)
        return []

    enriched = []
    for post in posts:
        media_id = post.get("media_id", "")
        if not media_id:
            enriched.append({**post, "views": 0, "likes": 0, "comments": 0, "score": 0})
            continue
        try:
            info = cl.media_info(media_id)
            views = getattr(info, "play_count", 0) or getattr(info, "view_count", 0) or 0
            likes = getattr(info, "like_count", 0) or 0
            comments = getattr(info, "comment_count", 0) or 0
            score = views * 1 + likes * 10 + comments * 30
            enriched.append({**post, "views": views, "likes": likes, "comments": comments, "score": score})
            log.info("%s — views=%d likes=%d comments=%d score=%d",
                     post["philosopher"], views, likes, comments, score)
        except Exception as exc:
            log.warning("Could not fetch metrics for %s (%s): %s", post["philosopher"], media_id, exc)
            enriched.append({**post, "views": 0, "likes": 0, "comments": 0, "score": 0})

    return enriched


def analyze(enriched: list[dict], client: Groq) -> dict:
    """Use Groq to analyze performance data and produce config improvements."""
    # Sort by score
    ranked = sorted(enriched, key=lambda p: p["score"], reverse=True)
    top = ranked[:max(3, len(ranked) // 3)]
    bottom = ranked[-max(3, len(ranked) // 3):]

    summary_lines = []
    for p in ranked:
        summary_lines.append(
            f"- {p['philosopher']}: \"{p['quote']}\" | song: {p['song_label'][:50]} "
            f"| views={p['views']} likes={p['likes']} comments={p['comments']} score={p['score']}"
        )
    summary = "\n".join(summary_lines)

    prompt = f"""You are analyzing Instagram Reel performance for a philosophical quotes account.

Here are all posts ranked by engagement score (views×1 + likes×10 + comments×30):

{summary}

Top performers:
{chr(10).join(f"- {p['philosopher']}: \"{p['quote']}\" | {p['song_label'][:50]}" for p in top)}

Bottom performers:
{chr(10).join(f"- {p['philosopher']}: \"{p['quote']}\" | {p['song_label'][:50]}" for p in bottom)}

Based on this data, answer in JSON with exactly these fields:
{{
  "quote_style_hint": "<1-2 sentences of style guidance to improve future quotes based on what worked>",
  "top_vibes": ["<vibe keyword that appears in high-performing songs>"],
  "avoid_vibes": ["<vibe keyword from low-performing songs>"],
  "optimization_notes": "<brief plain English summary of what you found>"
}}

Reply with ONLY the JSON. No explanation outside the JSON."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()

    # Extract JSON block
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"Groq returned non-JSON: {raw}")
    return json.loads(m.group())


def run(dry: bool = False) -> None:
    if not STATE_FILE.exists():
        sys.exit("No state.json found — run the pipeline first.")

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    posts = state.get("posts", [])

    if len(posts) < MIN_POSTS_REQUIRED:
        log.info("Only %d posts recorded — need at least %d to optimize. Skipping.",
                 len(posts), MIN_POSTS_REQUIRED)
        return

    log.info("Fetching metrics for %d posts...", len(posts))
    enriched = fetch_metrics(posts)

    # Save raw performance data
    PERF_FILE.write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Saved metrics to performance.json")

    posts_with_data = [p for p in enriched if p.get("views", 0) + p.get("likes", 0) > 0]
    if len(posts_with_data) < MIN_POSTS_REQUIRED:
        log.info("Not enough posts with real metrics yet (%d/%d). Skipping config update.",
                 len(posts_with_data), MIN_POSTS_REQUIRED)
        return

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("[error] GROQ_API_KEY not set")
    client = Groq(api_key=api_key)

    log.info("Analyzing performance with Groq...")
    try:
        improvements = analyze(posts_with_data, client)
    except Exception as exc:
        log.error("Analysis failed: %s", exc)
        return

    improvements["last_optimized"] = datetime.now(timezone.utc).isoformat()
    log.info("Optimization notes: %s", improvements.get("optimization_notes", ""))

    if dry:
        print("\n--- DRY RUN — config.json would be updated to: ---")
        print(json.dumps(improvements, indent=2))
        return

    CONFIG_FILE.write_text(
        json.dumps(improvements, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("config.json updated. Pipeline will use new style guidance on next run.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize pipeline based on Instagram metrics")
    parser.add_argument("--dry", action="store_true", help="Print analysis without writing config")
    args = parser.parse_args()
    run(dry=args.dry)


if __name__ == "__main__":
    main()

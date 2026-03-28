"""State management — persists used quotes/songs/photos per philosopher to state.json."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"philosophers": {}, "global_blacklisted_songs": [], "posts": []}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get_philosopher(self, name: str) -> dict:
        if name not in self.data["philosophers"]:
            self.data["philosophers"][name] = {
                "post_count": 0,
                "used_quotes": [],
                "used_songs": [],
                "used_photos": [],
            }
        return self.data["philosophers"][name]

    def get_blacklisted_songs(self) -> list[str]:
        return self.data.get("global_blacklisted_songs", [])

    def blacklist_song(self, url: str) -> None:
        if url not in self.data["global_blacklisted_songs"]:
            self.data["global_blacklisted_songs"].append(url)
            self.save()
            log.info("Auto-blacklisted song: %s", url)

    def mark_posted(
        self,
        philosopher: str,
        quote: str,
        song_url: str,
        photo_id: str,
        media_id: str = "",
        song_label: str = "",
    ) -> None:
        phil = self.get_philosopher(philosopher)
        phil["post_count"] += 1
        if quote not in phil["used_quotes"]:
            phil["used_quotes"].append(quote)
        if song_url not in phil["used_songs"]:
            phil["used_songs"].append(song_url)
        if photo_id not in phil["used_photos"]:
            phil["used_photos"].append(photo_id)
        if song_url not in self.data["global_blacklisted_songs"]:
            self.data["global_blacklisted_songs"].append(song_url)
        # Store full post record for performance tracking
        if "posts" not in self.data:
            self.data["posts"] = []
        self.data["posts"].append({
            "philosopher": philosopher,
            "quote": quote,
            "song_url": song_url,
            "song_label": song_label,
            "photo_id": photo_id,
            "media_id": str(media_id),
            "posted_at": datetime.now(timezone.utc).isoformat(),
        })
        self.save()

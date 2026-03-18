import copy
import json
import shutil
import logging
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)


def _default_entry() -> dict:
    return {
        "used_quotes": [],
        "used_songs": [],
        "used_photos": [],
        "reframed": False,
        "post_count": 0,
        "last_generated": None,
    }


class StateManager:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict | None = None

    def load(self) -> dict:
        if not self.path.exists():
            self._data = {}
            return self._data
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            bak = self.path.with_name(f"state.json.bak.{ts}")
            shutil.copy(self.path, bak)
            log.warning("Corrupt state.json — backed up to %s, starting fresh.", bak)
            self._data = {}
        return self._data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        self._data = data

    def _ensure_loaded(self) -> dict:
        if self._data is None:
            self.load()
        return self._data

    def get_philosopher(self, name: str) -> dict:
        """Returns a deep copy of the philosopher entry (safe to read, not to mutate)."""
        data = self._ensure_loaded()
        if name not in data:
            data[name] = _default_entry()
        return copy.deepcopy(data[name])

    def update_philosopher(
        self, name: str, quote: str, song_url: str, photo_filename: str, reframed: bool = False
    ) -> None:
        data = self._ensure_loaded()
        if name not in data:
            data[name] = _default_entry()
        entry = data[name]
        entry["used_quotes"].append(quote)
        entry["used_songs"].append(song_url)
        entry["used_photos"].append(photo_filename)
        entry["post_count"] += 1
        entry["reframed"] = reframed
        entry["last_generated"] = date.today().isoformat()
        self.save(data)

    def blacklist_song(self, url: str) -> None:
        data = self._ensure_loaded()
        data.setdefault("_blacklisted_songs", [])
        if url not in data["_blacklisted_songs"]:
            data["_blacklisted_songs"].append(url)
        self.save(data)

    def get_blacklisted_songs(self) -> list[str]:
        return self._ensure_loaded().get("_blacklisted_songs", [])

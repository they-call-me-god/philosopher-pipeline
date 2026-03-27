"""Upload Reels to Instagram via instagrapi."""
import logging
import os
from pathlib import Path

from instagrapi import Client

log = logging.getLogger(__name__)

_client: Client | None = None
SESSION_FILE = Path(__file__).parent / "session.json"


def _get_client() -> Client:
    global _client
    if _client is not None:
        return _client

    username = os.environ["INSTAGRAM_USERNAME"]
    password = os.environ["INSTAGRAM_PASSWORD"]
    cl = Client()

    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            log.info("Logged in via saved session")
        except Exception:
            log.warning("Saved session invalid — re-logging in fresh")
            cl = Client()
            cl.login(username, password)
    else:
        cl.login(username, password)
        log.info("Fresh login successful")

    cl.dump_settings(SESSION_FILE)
    _client = cl
    return cl


def upload_reel(video_path: Path, caption: str) -> str:
    """Upload video as Instagram Reel. Returns media pk."""
    cl = _get_client()
    media = cl.clip_upload(video_path, caption=caption)
    log.info("Uploaded reel: %s", media.pk)
    return media.pk

"""
tests/test_uploader.py — Unit tests for uploader.py (instagrapi mocked).

All instagrapi.Client interactions are mocked so no real network call is made.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on sys.path so `import uploader` resolves correctly
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_uploader_singleton():
    """Force uploader to rebuild its Client singleton on next call."""
    import uploader
    uploader._client = None


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_singleton():
    """Each test starts with a fresh singleton and clean env."""
    _reset_uploader_singleton()
    yield
    _reset_uploader_singleton()


@pytest.fixture()
def credentials(monkeypatch):
    """Inject fake credentials via environment variables."""
    monkeypatch.setenv("INSTAGRAM_USERNAME", "test_user")
    monkeypatch.setenv("INSTAGRAM_PASSWORD", "test_pass")


@pytest.fixture()
def no_credentials(monkeypatch):
    """Ensure credential env vars are absent."""
    monkeypatch.delenv("INSTAGRAM_USERNAME", raising=False)
    monkeypatch.delenv("INSTAGRAM_PASSWORD", raising=False)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_upload_reel_calls_clip_upload(tmp_path, credentials):
    """clip_upload is called with a Path object and the correct caption."""
    mp4 = tmp_path / "reel.mp4"
    mp4.write_bytes(b"\x00" * 8)  # placeholder content

    mock_client = MagicMock()

    with patch("instagrapi.Client", return_value=mock_client):
        # Prevent session file side-effects
        mock_client.dump_settings = MagicMock()
        mock_client.load_settings = MagicMock()
        mock_client.login = MagicMock()

        import uploader
        result = uploader.upload_reel(str(mp4), "Test caption #philosophy")

    mock_client.clip_upload.assert_called_once_with(
        Path(str(mp4)), caption="Test caption #philosophy", thumbnail=None
    )


def test_upload_reel_missing_credentials_raises(no_credentials):
    """ValueError is raised when credentials are not set."""
    import uploader
    # Also make sure no .env file supplies creds for this test
    with patch.object(uploader, "_load_dotenv", lambda: None):
        with pytest.raises(ValueError, match="INSTAGRAM_USERNAME"):
            uploader.upload_reel("/fake/path/reel.mp4", "caption")


def test_upload_reel_returns_true_on_success(tmp_path, credentials):
    """upload_reel returns True when clip_upload completes without error."""
    mp4 = tmp_path / "reel.mp4"
    mp4.write_bytes(b"\x00" * 8)

    mock_client = MagicMock()

    with patch("instagrapi.Client", return_value=mock_client):
        mock_client.dump_settings = MagicMock()
        mock_client.load_settings = MagicMock()
        mock_client.login = MagicMock()

        import uploader
        result = uploader.upload_reel(str(mp4), "caption")

    assert result is True


def test_session_loaded_on_init(tmp_path, credentials, monkeypatch):
    """If a session file exists, load_settings() is called during init."""
    import uploader

    # Point pipeline dir to tmp_path so session file is found there
    monkeypatch.setattr(uploader, "_PIPELINE_DIR", tmp_path)

    # Create a fake session file
    session_file = tmp_path / "test_user.session"
    session_file.write_text("{}")

    mock_client = MagicMock()

    with patch("instagrapi.Client", return_value=mock_client):
        mock_client.dump_settings = MagicMock()
        mock_client.login = MagicMock()

        uploader._get_client()

    mock_client.load_settings.assert_called_once_with(session_file)


def test_session_saved_after_login(tmp_path, credentials, monkeypatch):
    """After a successful login, dump_settings() is called to cache the session."""
    import uploader

    monkeypatch.setattr(uploader, "_PIPELINE_DIR", tmp_path)
    # No session file → fresh login path
    session_file = tmp_path / "test_user.session"
    assert not session_file.exists()

    mock_client = MagicMock()

    with patch("instagrapi.Client", return_value=mock_client):
        mock_client.login = MagicMock()
        mock_client.load_settings = MagicMock()

        uploader._get_client()

    mock_client.dump_settings.assert_called_once_with(session_file)

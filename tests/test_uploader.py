from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


def _make_mock_client(media_pk="12345"):
    cl = MagicMock()
    cl.load_settings.side_effect = Exception("no session")
    cl.clip_upload.return_value = MagicMock(pk=media_pk)
    return cl


def test_upload_reel_calls_clip_upload():
    with patch("uploader.Client") as MockClient:
        MockClient.return_value = _make_mock_client()
        with patch.dict("os.environ", {"INSTAGRAM_USERNAME": "u", "INSTAGRAM_PASSWORD": "p"}):
            import uploader; uploader._client = None
            uploader.upload_reel(Path("x.mp4"), "caption")
        assert MockClient.return_value.clip_upload.called


def test_upload_reel_returns_pk():
    with patch("uploader.Client") as MockClient:
        MockClient.return_value = _make_mock_client("99999")
        with patch.dict("os.environ", {"INSTAGRAM_USERNAME": "u", "INSTAGRAM_PASSWORD": "p"}):
            import uploader; uploader._client = None
            result = uploader.upload_reel(Path("x.mp4"), "caption")
        assert result == "99999"


def test_upload_reel_passes_caption():
    with patch("uploader.Client") as MockClient:
        MockClient.return_value = _make_mock_client()
        with patch.dict("os.environ", {"INSTAGRAM_USERNAME": "u", "INSTAGRAM_PASSWORD": "p"}):
            import uploader; uploader._client = None
            uploader.upload_reel(Path("x.mp4"), "my caption")
        call_args = MockClient.return_value.clip_upload.call_args
        assert "my caption" in str(call_args)

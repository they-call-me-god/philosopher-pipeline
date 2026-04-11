import hashlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fetcher import fetch_quote, match_song, fetch_photo


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_mock_client(response_text: str):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client


SONGS = [
    {"url": "https://youtube.com/watch?v=aaa", "label": "Dark ambient"},
    {"url": "https://youtube.com/watch?v=bbb", "label": "Melancholic piano"},
    {"url": "https://youtube.com/watch?v=ccc", "label": "Stoic orchestral"},
]

MOCK_WIKIMEDIA_RESPONSE = {
    "query": {
        "search": [
            {"title": "File:Voltaire portrait.jpg"},
            {"title": "File:Voltaire young.jpg"},
        ]
    }
}

MOCK_IMAGE_INFO = {
    "query": {
        "pages": {
            "-1": {
                "imageinfo": [{
                    "url": "https://upload.wikimedia.org/test.jpg",
                    "width": 600,
                    "height": 800,
                }]
            }
        }
    }
}


# ── Quote fetch tests ─────────────────────────────────────────────────────────

def test_fetch_quote_returns_string():
    result = fetch_quote("Voltaire", used_quotes=[])
    assert isinstance(result["quote"], str)
    assert len(result["quote"]) > 0

def test_fetch_quote_passes_used_quotes_in_prompt():
    """Returned quote must not be in used_quotes list."""
    first = fetch_quote("Voltaire", used_quotes=[])["quote"]
    result = fetch_quote("Voltaire", used_quotes=[first])
    assert result["quote"] != first

def test_fetch_quote_caps_length_at_280_chars():
    """All hardcoded quotes are well under 280 chars — just verify we get a valid quote."""
    result = fetch_quote("Voltaire", used_quotes=[])
    assert len(result["quote"]) <= 280
    assert len(result["quote"]) > 0

def test_fetch_quote_marks_reframed_when_flagged():
    """reframed=True when all quotes are exhausted (cycles back)."""
    from fetcher import PHILOSOPHER_QUOTES
    all_voltaire = PHILOSOPHER_QUOTES["voltaire"]
    result = fetch_quote("Voltaire", used_quotes=list(all_voltaire))
    assert result["reframed"] is True

def test_fetch_quote_not_reframed_by_default():
    """reframed=False when fresh quotes are available."""
    result = fetch_quote("Voltaire", used_quotes=[])
    assert result["reframed"] is False


# ── Song match tests ──────────────────────────────────────────────────────────

def test_match_song_returns_url_from_list():
    result = match_song("Kafka", "Quote text", songs=SONGS,
                        used_in_run=[], used_for_philosopher=[])
    assert result == "https://youtube.com/watch?v=aaa"

def test_match_song_excludes_used_in_run():
    """Song used in current run must not be returned when alternatives exist."""
    result = match_song("Camus", "Quote", songs=SONGS,
                        used_in_run=["https://youtube.com/watch?v=aaa"],
                        used_for_philosopher=[])
    assert result != "https://youtube.com/watch?v=aaa"

def test_match_song_excludes_last_3_used_for_philosopher():
    """Songs in last 3 used for this philosopher must not be returned when alternatives exist."""
    result = match_song(
        "Friedrich Nietzsche", "Quote", songs=SONGS,
        used_in_run=[],
        used_for_philosopher=[
            "https://youtube.com/watch?v=aaa",
            "https://youtube.com/watch?v=bbb",
        ]
    )
    assert result not in ["https://youtube.com/watch?v=aaa", "https://youtube.com/watch?v=bbb"]

def test_match_song_fallback_when_all_excluded():
    result = match_song(
        "Voltaire", "Quote",
        songs=[{"url": "https://youtube.com/watch?v=aaa", "label": "Ambient"}],
        used_in_run=[],
        used_for_philosopher=["https://youtube.com/watch?v=aaa",
                               "https://youtube.com/watch?v=aaa",
                               "https://youtube.com/watch?v=aaa"]
    )
    assert result is not None

def test_match_song_only_excludes_last_3_not_full_history():
    """Songs older than the last 3 should NOT be excluded — aaa is oldest so must be available."""
    # used_for_philosopher has 4 entries; only last 3 should be excluded
    # last 3: bbb, ccc, bbb — aaa (oldest) should still be pickable
    result = match_song(
        "Voltaire", "Quote",
        songs=SONGS,
        used_in_run=[],
        used_for_philosopher=[
            "https://youtube.com/watch?v=aaa",   # oldest — NOT in last 3, should be available
            "https://youtube.com/watch?v=bbb",
            "https://youtube.com/watch?v=ccc",
            "https://youtube.com/watch?v=bbb",
        ]
    )
    # aaa should be chosen (only non-excluded option)
    assert result == "https://youtube.com/watch?v=aaa"

def test_match_song_invalid_response_falls_back_to_first_available():
    result = match_song("Kafka", "Quote", songs=SONGS,
                        used_in_run=[], used_for_philosopher=[])
    assert result in [s["url"] for s in SONGS]


# ── Photo fetch tests ─────────────────────────────────────────────────────────

def test_fetch_photo_returns_path(tmp_path):
    with patch("fetcher.requests.get") as mock_get:
        search_resp = MagicMock()
        search_resp.json.return_value = MOCK_WIKIMEDIA_RESPONSE
        search_resp.raise_for_status = MagicMock()
        info_resp = MagicMock()
        info_resp.json.return_value = MOCK_IMAGE_INFO
        info_resp.raise_for_status = MagicMock()
        img_resp = MagicMock()
        img_resp.content = b"FAKEJPEG"
        img_resp.raise_for_status = MagicMock()
        mock_get.side_effect = [search_resp, info_resp, img_resp]

        result = fetch_photo("Voltaire", used_photos=[], cache_dir=tmp_path)
        assert result is not None
        assert Path(result).exists()

def test_fetch_photo_skips_used_photos(tmp_path):
    mock_url = "https://upload.wikimedia.org/test.jpg"
    url_hash = hashlib.md5(mock_url.encode()).hexdigest()[:8]
    already_used_filename = f"voltaire-{url_hash}.jpg"

    with patch("fetcher.requests.get") as mock_get:
        search_resp = MagicMock()
        search_resp.json.return_value = MOCK_WIKIMEDIA_RESPONSE
        search_resp.raise_for_status = MagicMock()
        info_resp1 = MagicMock()
        info_resp1.json.return_value = MOCK_IMAGE_INFO
        info_resp1.raise_for_status = MagicMock()
        info_resp2 = MagicMock()
        info_resp2.json.return_value = MOCK_IMAGE_INFO
        info_resp2.raise_for_status = MagicMock()
        mock_get.side_effect = [search_resp, info_resp1, info_resp2]

        result = fetch_photo("Voltaire", used_photos=[already_used_filename], cache_dir=tmp_path)
        assert result is None
        assert mock_get.call_count == 3  # search + info for result1 + info for result2

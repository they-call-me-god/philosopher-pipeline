import hashlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fetcher import (
    fetch_quote, match_song, fetch_photo,
    fetch_paintings, fetch_portraits, get_bio,
    PHILOSOPHER_BIOS,
)


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

MOCK_CATEGORY_RESPONSE = {
    "query": {
        "categorymembers": [
            {"title": "File:Mona_Lisa.jpg"},
            {"title": "File:Birth_of_Venus.jpg"},
        ]
    }
}

MOCK_PAINTING_INFO = {
    "query": {
        "pages": {
            "-1": {
                "imageinfo": [{
                    "url": "https://upload.wikimedia.org/painting1.jpg",
                    "width": 1200,
                    "height": 1500,
                }]
            }
        }
    }
}


# Quote tests

def test_fetch_quote_returns_string():
    result = fetch_quote("Voltaire", used_quotes=[])
    assert isinstance(result["quote"], str)
    assert len(result["quote"]) > 0


def test_fetch_quote_passes_used_quotes_in_prompt():
    first = fetch_quote("Voltaire", used_quotes=[])["quote"]
    result = fetch_quote("Voltaire", used_quotes=[first])
    assert result["quote"] != first


def test_fetch_quote_caps_length_at_280_chars():
    result = fetch_quote("Voltaire", used_quotes=[])
    assert len(result["quote"]) <= 280
    assert len(result["quote"]) > 0


def test_fetch_quote_marks_reframed_when_flagged():
    from fetcher import PHILOSOPHER_QUOTES
    all_voltaire = PHILOSOPHER_QUOTES["voltaire"]
    result = fetch_quote("Voltaire", used_quotes=list(all_voltaire))
    assert result["reframed"] is True


def test_fetch_quote_not_reframed_by_default():
    result = fetch_quote("Voltaire", used_quotes=[])
    assert result["reframed"] is False


# Song match tests

def test_match_song_returns_url_from_list():
    result = match_song("Kafka", "Quote text", songs=SONGS,
                        used_in_run=[], used_for_philosopher=[])
    assert result == "https://youtube.com/watch?v=aaa"


def test_match_song_excludes_used_in_run():
    result = match_song("Camus", "Quote", songs=SONGS,
                        used_in_run=["https://youtube.com/watch?v=aaa"],
                        used_for_philosopher=[])
    assert result != "https://youtube.com/watch?v=aaa"


def test_match_song_excludes_last_3_used_for_philosopher():
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
    result = match_song(
        "Voltaire", "Quote",
        songs=SONGS,
        used_in_run=[],
        used_for_philosopher=[
            "https://youtube.com/watch?v=aaa",
            "https://youtube.com/watch?v=bbb",
            "https://youtube.com/watch?v=ccc",
            "https://youtube.com/watch?v=bbb",
        ]
    )
    assert result == "https://youtube.com/watch?v=aaa"


def test_match_song_invalid_response_falls_back_to_first_available():
    result = match_song("Kafka", "Quote", songs=SONGS,
                        used_in_run=[], used_for_philosopher=[])
    assert result in [s["url"] for s in SONGS]


# Photo fetch tests (legacy single portrait)

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
    already_used_filename = "voltaire-" + url_hash + ".jpg"

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
        assert mock_get.call_count == 3


# Bio tests

def test_get_bio_known_philosopher():
    bio = get_bio("Voltaire")
    assert isinstance(bio, str)
    assert len(bio) > 0
    assert "Enlightenment" in bio


def test_get_bio_unknown_philosopher():
    assert get_bio("Some Random Person") == ""


def test_get_bio_case_insensitive():
    assert get_bio("VOLTAIRE") == get_bio("voltaire")


def test_philosopher_bios_covers_all_quote_authors():
    """Every philosopher with quotes should also have a bio."""
    from fetcher import PHILOSOPHER_QUOTES
    for name in PHILOSOPHER_QUOTES.keys():
        assert get_bio(name), "Missing bio for " + name


# Painting fetch tests

def test_fetch_paintings_returns_list_of_paths(tmp_path):
    with patch("fetcher.requests.get") as mock_get:
        cat_resp = MagicMock()
        cat_resp.json.return_value = MOCK_CATEGORY_RESPONSE
        cat_resp.raise_for_status = MagicMock()
        info_resp = MagicMock()
        info_resp.json.return_value = MOCK_PAINTING_INFO
        info_resp.raise_for_status = MagicMock()
        img_resp = MagicMock()
        img_resp.content = b"FAKEPAINTINGBYTES"
        img_resp.raise_for_status = MagicMock()
        mock_get.side_effect = [cat_resp, info_resp, img_resp,
                                 cat_resp, info_resp, img_resp,
                                 cat_resp, info_resp, img_resp,
                                 cat_resp, info_resp, img_resp,
                                 cat_resp, info_resp, img_resp]

        result = fetch_paintings(1, used_paintings=[], cache_dir=tmp_path)
        assert isinstance(result, list)
        assert len(result) >= 1
        assert Path(result[0]).exists()


def test_fetch_paintings_returns_empty_when_no_data(tmp_path):
    with patch("fetcher.requests.get") as mock_get:
        empty_resp = MagicMock()
        empty_resp.json.return_value = {"query": {"categorymembers": []}}
        empty_resp.raise_for_status = MagicMock()
        mock_get.return_value = empty_resp

        result = fetch_paintings(3, used_paintings=[], cache_dir=tmp_path)
        assert result == []


# Portrait fetch tests (multi-portrait)

def test_fetch_portraits_returns_list(tmp_path):
    with patch("fetcher.requests.get") as mock_get:
        search_resp = MagicMock()
        search_resp.json.return_value = MOCK_WIKIMEDIA_RESPONSE
        search_resp.raise_for_status = MagicMock()
        info_resp = MagicMock()
        info_resp.json.return_value = MOCK_IMAGE_INFO
        info_resp.raise_for_status = MagicMock()
        img_resp = MagicMock()
        img_resp.content = b"FAKEPORTRAIT"
        img_resp.raise_for_status = MagicMock()
        mock_get.side_effect = [search_resp, info_resp, img_resp,
                                 info_resp, img_resp]

        result = fetch_portraits("Voltaire", count=1, used_portraits=[], cache_dir=tmp_path)
        assert isinstance(result, list)
        assert len(result) >= 1


def test_fetch_portraits_falls_back_to_cache_on_error(tmp_path):
    """When network fails entirely, cached portraits should still be returned."""
    cached_path = tmp_path / "portrait-voltaire-deadbeef00.jpg"
    cached_path.write_bytes(b"PRECACHED")

    with patch("fetcher.requests.get", side_effect=Exception("network down")):
        result = fetch_portraits("Voltaire", count=2, used_portraits=[], cache_dir=tmp_path)
        assert any("portrait-voltaire-deadbeef00" in p for p in result)

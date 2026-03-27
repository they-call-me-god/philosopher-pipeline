from unittest.mock import MagicMock
import pytest
from fetcher import fetch_quote, match_song


def mock_client(text: str) -> MagicMock:
    cl = MagicMock()
    cl.messages.create.return_value = MagicMock(content=[MagicMock(text=text)])
    return cl


SONGS = [
    {"url": "http://s1", "label": "Dream pop, slow burn"},
    {"url": "http://s2", "label": "Dark ambient, cinematic"},
    {"url": "http://s3", "label": "Lofi, contemplative"},
]


def test_fetch_quote_returns_string():
    result = fetch_quote("Nietzsche", [], mock_client("The will to power."))
    assert isinstance(result, str) and len(result) > 0


def test_fetch_quote_strips_surrounding_quotes():
    result = fetch_quote("Camus", [], mock_client('"The absurd is everything."'))
    assert not result.startswith('"')


def test_fetch_quote_includes_used_in_prompt():
    cl = mock_client("New quote.")
    fetch_quote("Nietzsche", ["old quote here"], cl)
    prompt = cl.messages.create.call_args[1]["messages"][0]["content"]
    assert "old quote here" in prompt


def test_fetch_quote_uses_philosopher_in_prompt():
    cl = mock_client("A quote.")
    fetch_quote("Schopenhauer", [], cl)
    prompt = cl.messages.create.call_args[1]["messages"][0]["content"]
    assert "Schopenhauer" in prompt


def test_match_song_returns_dict():
    result = match_song("Nietzsche", "q", SONGS, [], [], mock_client("2"))
    assert "url" in result and "label" in result


def test_match_song_picks_correct_index():
    result = match_song("Nietzsche", "q", SONGS, [], [], mock_client("2"))
    assert result["url"] == "http://s2"


def test_match_song_excludes_used_in_run():
    result = match_song("Nietzsche", "q", SONGS, ["http://s1"], [], mock_client("1"))
    assert result["url"] != "http://s1"


def test_match_song_excludes_used_for_philosopher():
    result = match_song("Nietzsche", "q", SONGS, [], ["http://s1", "http://s2"], mock_client("1"))
    assert result["url"] == "http://s3"


def test_match_song_falls_back_when_all_run_used():
    result = match_song("Nietzsche", "q", [SONGS[0]], [SONGS[0]["url"]], [], mock_client("1"))
    assert result["url"] == SONGS[0]["url"]


def test_match_song_invalid_response_uses_first():
    result = match_song("Nietzsche", "q", SONGS, [], [], mock_client("not a number"))
    assert result in SONGS

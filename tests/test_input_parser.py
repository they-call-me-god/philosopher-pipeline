import pytest
from pathlib import Path
from input_parser import parse_philosophers, parse_songs

@pytest.fixture
def write_file(tmp_path):
    def _write(name, content):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p
    return _write

def test_parse_philosophers_basic(write_file):
    p = write_file("philosophers.md", "- Voltaire\n- Kafka\n")
    result = parse_philosophers(p)
    assert result == ["Voltaire", "Kafka"]

def test_parse_philosophers_deduplicates(write_file):
    p = write_file("philosophers.md", "- Voltaire\n- Voltaire\n- Kafka\n")
    result = parse_philosophers(p)
    assert result == ["Voltaire", "Kafka"]

def test_parse_philosophers_ignores_comments(write_file):
    p = write_file("philosophers.md", "# Heading\n- Voltaire\n- Kafka\n")
    result = parse_philosophers(p)
    assert result == ["Voltaire", "Kafka"]

def test_parse_philosophers_missing_file():
    with pytest.raises(SystemExit):
        parse_philosophers(Path("/nonexistent/philosophers.md"))

def test_parse_philosophers_empty_file(write_file):
    p = write_file("philosophers.md", "")
    with pytest.raises(SystemExit):
        parse_philosophers(p)

def test_parse_songs_basic(write_file):
    p = write_file("songs.md", "- https://youtube.com/watch?v=abc  # Dark ambient\n")
    result = parse_songs(p)
    assert result == [{"url": "https://youtube.com/watch?v=abc", "label": "Dark ambient"}]

def test_parse_songs_skips_placeholder_lines(write_file):
    p = write_file("songs.md", "- # paste link here  # vibe\n- https://youtube.com/watch?v=abc  # real\n")
    result = parse_songs(p)
    assert len(result) == 1
    assert result[0]["url"] == "https://youtube.com/watch?v=abc"

def test_parse_songs_missing_file():
    with pytest.raises(SystemExit):
        parse_songs(Path("/nonexistent/songs.md"))

def test_parse_songs_label_stripped(write_file):
    p = write_file("songs.md", "- https://youtube.com/watch?v=abc  #  Melancholic piano  \n")
    result = parse_songs(p)
    assert result[0]["label"] == "Melancholic piano"

def test_parse_songs_url_without_label(write_file):
    p = write_file("songs.md", "- https://youtube.com/watch?v=abc\n")
    result = parse_songs(p)
    assert len(result) == 1
    assert result[0]["url"] == "https://youtube.com/watch?v=abc"
    assert result[0]["label"] == ""

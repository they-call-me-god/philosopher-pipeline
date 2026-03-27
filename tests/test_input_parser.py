import pytest
from input_parser import parse_philosophers, parse_songs


@pytest.fixture
def phil_file(tmp_path):
    f = tmp_path / "philosophers.md"
    f.write_text("- Nietzsche\n- Camus\n- Dostoevsky\n")
    return f


@pytest.fixture
def songs_file(tmp_path):
    f = tmp_path / "songs.md"
    f.write_text(
        "- https://youtube.com/watch?v=abc  # Dream pop, slow burn\n"
        "- https://youtube.com/watch?v=def  # Dark ambient, cinematic\n"
    )
    return f


def test_parse_philosophers_returns_list(phil_file):
    assert isinstance(parse_philosophers(phil_file), list)


def test_parse_philosophers_count(phil_file):
    assert len(parse_philosophers(phil_file)) == 3


def test_parse_philosophers_contains_names(phil_file):
    result = parse_philosophers(phil_file)
    assert "Nietzsche" in result and "Camus" in result


def test_parse_philosophers_missing_exits(tmp_path):
    with pytest.raises(SystemExit):
        parse_philosophers(tmp_path / "missing.md")


def test_parse_philosophers_ignores_empty_lines(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("- Nietzsche\n\n- Camus\n\n")
    assert len(parse_philosophers(f)) == 2


def test_parse_songs_returns_dicts(songs_file):
    result = parse_songs(songs_file)
    assert all("url" in s and "label" in s for s in result)


def test_parse_songs_count(songs_file):
    assert len(parse_songs(songs_file)) == 2


def test_parse_songs_url(songs_file):
    assert parse_songs(songs_file)[0]["url"] == "https://youtube.com/watch?v=abc"


def test_parse_songs_label(songs_file):
    assert parse_songs(songs_file)[0]["label"] == "Dream pop, slow burn"


def test_parse_songs_missing_exits(tmp_path):
    with pytest.raises(SystemExit):
        parse_songs(tmp_path / "missing.md")


def test_parse_songs_ignores_non_url_lines(tmp_path):
    f = tmp_path / "s.md"
    f.write_text("# Header\n\n- https://youtube.com/watch?v=abc  # Vibe\n## Section\n")
    assert len(parse_songs(f)) == 1

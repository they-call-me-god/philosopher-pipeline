import pytest
from state import State


@pytest.fixture
def s(tmp_path):
    return State(tmp_path / "state.json")


def test_initial_blacklist_empty(s):
    assert s.get_blacklisted_songs() == []


def test_get_philosopher_creates_entry(s):
    p = s.get_philosopher("Nietzsche")
    assert p["post_count"] == 0
    assert p["used_quotes"] == []
    assert p["used_songs"] == []
    assert p["used_photos"] == []


def test_get_philosopher_idempotent(s):
    s.get_philosopher("Camus")
    s.get_philosopher("Camus")
    assert len(s.data["philosophers"]) == 1


def test_mark_posted_increments_count(s):
    s.mark_posted("Nietzsche", "q", "http://s1", "p1")
    assert s.get_philosopher("Nietzsche")["post_count"] == 1


def test_mark_posted_tracks_quote(s):
    s.mark_posted("Nietzsche", "the will to power", "http://s1", "p1")
    assert "the will to power" in s.get_philosopher("Nietzsche")["used_quotes"]


def test_mark_posted_tracks_song_per_philosopher(s):
    s.mark_posted("Nietzsche", "q", "http://s1", "p1")
    assert "http://s1" in s.get_philosopher("Nietzsche")["used_songs"]


def test_mark_posted_tracks_photo(s):
    s.mark_posted("Nietzsche", "q", "http://s1", "photo_abc")
    assert "photo_abc" in s.get_philosopher("Nietzsche")["used_photos"]


def test_mark_posted_adds_to_global_blacklist(s):
    s.mark_posted("Nietzsche", "q", "http://s1", "p1")
    assert "http://s1" in s.get_blacklisted_songs()


def test_blacklist_no_duplicates(s):
    s.mark_posted("Nietzsche", "q1", "http://s1", "p1")
    s.mark_posted("Nietzsche", "q2", "http://s1", "p2")
    assert s.get_blacklisted_songs().count("http://s1") == 1


def test_state_persists_to_disk(tmp_path):
    s1 = State(tmp_path / "state.json")
    s1.mark_posted("Camus", "q", "http://s", "p")
    s2 = State(tmp_path / "state.json")
    assert s2.get_philosopher("Camus")["post_count"] == 1


def test_multiple_philosophers_independent(s):
    s.mark_posted("Nietzsche", "q1", "http://s1", "p1")
    s.mark_posted("Camus", "q2", "http://s2", "p2")
    assert s.get_philosopher("Nietzsche")["post_count"] == 1
    assert s.get_philosopher("Camus")["post_count"] == 1
    assert len(s.get_blacklisted_songs()) == 2

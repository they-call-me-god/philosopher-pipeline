import json
import pytest
from datetime import date
from pathlib import Path
from state import StateManager

@pytest.fixture
def tmp_state(tmp_path):
    return StateManager(tmp_path / "state.json")

def test_load_empty_when_no_file(tmp_state):
    data = tmp_state.load()
    assert data == {}

def test_save_and_load_roundtrip(tmp_state):
    tmp_state.save({"Voltaire": {"used_quotes": ["q1"]}})
    data = tmp_state.load()
    assert data["Voltaire"]["used_quotes"] == ["q1"]

def test_atomic_write_uses_tmp_file(tmp_state, tmp_path):
    tmp_state.save({"key": "value"})
    assert not (tmp_path / "state.json.tmp").exists()
    assert (tmp_path / "state.json").exists()

def test_corrupt_json_returns_empty_and_backs_up(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text("{ invalid json }")
    sm = StateManager(state_path)
    data = sm.load()
    assert data == {}
    bak_files = list(tmp_path.glob("state.json.bak.*"))
    assert len(bak_files) == 1

def test_get_philosopher_defaults(tmp_state):
    entry = tmp_state.get_philosopher("Kafka")
    assert entry["used_quotes"] == []
    assert entry["used_songs"] == []
    assert entry["used_photos"] == []
    assert entry["post_count"] == 0
    assert entry["reframed"] is False

def test_update_philosopher_after_success(tmp_state):
    tmp_state.update_philosopher(
        "Kafka",
        quote="The meaning of life is that it stops.",
        song_url="https://youtube.com/watch?v=abc",
        photo_filename="kafka-001.jpg"
    )
    data = tmp_state.load()
    entry = data["Kafka"]
    assert entry["used_quotes"] == ["The meaning of life is that it stops."]
    assert entry["used_songs"] == ["https://youtube.com/watch?v=abc"]
    assert entry["used_photos"] == ["kafka-001.jpg"]
    assert entry["post_count"] == 1

def test_blacklist_song(tmp_state):
    tmp_state.blacklist_song("https://youtube.com/watch?v=broken")
    data = tmp_state.load()
    assert "https://youtube.com/watch?v=broken" in data["_blacklisted_songs"]

def test_get_blacklisted_songs_empty_by_default(tmp_state):
    assert tmp_state.get_blacklisted_songs() == []

def test_update_philosopher_sets_last_generated(tmp_state):
    tmp_state.update_philosopher("Kafka", "q", "url", "photo.jpg")
    data = tmp_state.load()
    assert data["Kafka"]["last_generated"] == date.today().isoformat()

def test_blacklist_song_idempotent(tmp_state):
    tmp_state.blacklist_song("https://youtube.com/watch?v=x")
    tmp_state.blacklist_song("https://youtube.com/watch?v=x")
    data = tmp_state.load()
    assert data["_blacklisted_songs"].count("https://youtube.com/watch?v=x") == 1

def test_update_philosopher_reframed_flag(tmp_state):
    tmp_state.update_philosopher("Nietzsche", "q", "url", "photo.jpg", reframed=True)
    data = tmp_state.load()
    assert data["Nietzsche"]["reframed"] is True

def test_get_philosopher_returns_copy(tmp_state):
    tmp_state._ensure_loaded()  # init _data
    entry = tmp_state.get_philosopher("Voltaire")
    entry["used_quotes"].append("mutated")
    # Load fresh — the mutation should NOT be visible in state
    fresh = tmp_state.get_philosopher("Voltaire")
    assert "mutated" not in fresh["used_quotes"]

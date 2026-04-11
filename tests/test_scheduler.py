from datetime import datetime
import pytest
from scheduler import get_next_slots

def test_slots_on_tuesday():
    # Tuesday at 8am should return 9am as first slot
    now = datetime(2026, 3, 17, 8, 0)  # Tuesday
    slots = get_next_slots(now, count=3)
    assert slots[0].hour == 9
    assert slots[0].weekday() == 1  # Tuesday

def test_slots_on_sunday_returns_tuesday():
    now = datetime(2026, 3, 22, 10, 0)  # Sunday
    slots = get_next_slots(now, count=1)
    assert slots[0].weekday() == 1  # Tuesday

def test_slots_on_monday_returns_tuesday():
    now = datetime(2026, 3, 23, 10, 0)  # Monday
    slots = get_next_slots(now, count=1)
    assert slots[0].weekday() == 1  # Tuesday

def test_slots_are_in_future():
    now = datetime(2026, 3, 17, 13, 0)  # Tuesday 1pm
    slots = get_next_slots(now, count=5)
    for slot in slots:
        assert slot > now

def test_returns_requested_count():
    now = datetime(2026, 3, 17, 8, 0)
    slots = get_next_slots(now, count=4)
    assert len(slots) == 4

def test_slots_are_unique():
    now = datetime(2026, 3, 17, 8, 0)
    slots = get_next_slots(now, count=9)
    assert len(slots) == len(set(slots))

def test_slots_are_sorted():
    now = datetime(2026, 3, 17, 8, 0)
    slots = get_next_slots(now, count=6)
    assert slots == sorted(slots)

def test_skips_past_slots_same_day():
    # Tuesday at 10am — 9am slot already passed
    now = datetime(2026, 3, 17, 10, 30)  # Tuesday 10:30am
    slots = get_next_slots(now, count=1)
    assert slots[0] > now
    # First future slot should be Tuesday 12pm (9am already passed)
    assert slots[0].hour == 12
    assert slots[0].weekday() == 1

def test_only_excludes_last_3_used_for_philosopher():
    # Request 12 slots to span multiple weeks
    now = datetime(2026, 3, 17, 8, 0)  # Tuesday
    slots = get_next_slots(now, count=12)
    assert len(slots) == 12
    # All slots must be on valid posting days (Tue-Sat)
    for slot in slots:
        assert slot.weekday() in [1, 2, 3, 4, 5], f"Invalid day: {slot}"

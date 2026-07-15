"""An unreadable image must not bill a vision call every sync, forever."""
from __future__ import annotations

from doing2done.pipeline import MAX_VISION_RETRIES
from doing2done.state import State


def test_counter_starts_at_zero(tmp_path):
    st = State(str(tmp_path / "s.db"))
    assert st.vision_failures("n1") == 0


def test_counter_increments_per_note(tmp_path):
    st = State(str(tmp_path / "s.db"))
    assert st.bump_vision_failure("n1") == 1
    assert st.bump_vision_failure("n1") == 2
    assert st.bump_vision_failure("n2") == 1, "counters must not bleed between notes"
    assert st.vision_failures("n1") == 2


def test_success_clears_the_counter(tmp_path):
    """A blip must not push a note toward the cap forever."""
    st = State(str(tmp_path / "s.db"))
    st.bump_vision_failure("n1")
    st.bump_vision_failure("n1")
    st.clear_vision_failure("n1")
    assert st.vision_failures("n1") == 0


def test_clearing_an_unknown_note_is_harmless(tmp_path):
    State(str(tmp_path / "s.db")).clear_vision_failure("never-seen")


def test_cap_is_bounded_and_small():
    """The cap is the whole point: unbounded retry is an open-ended bill."""
    assert 1 <= MAX_VISION_RETRIES <= 5

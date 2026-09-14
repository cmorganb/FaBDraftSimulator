"""Tests for the JSONL event log writer/reader (WP-04)."""

from __future__ import annotations

from pathlib import Path

from fabdraft_core.contracts import DraftEvent
from fabdraft_core.logs.jsonl import append_event, append_events, iter_events, read_events


def _event(event_id: int, type_: str = "SESSION_CREATED") -> DraftEvent:
    return DraftEvent(
        event_id=event_id,
        session_id="s1",
        ts_sim_ms=event_id * 10,
        ts_wall="2026-09-14T00:00:00Z",  # type: ignore[arg-type]
        type=type_,  # type: ignore[arg-type]
        round=1,
        pick_number=2,
        seat=3,
        payload={"picked_uid": "fixture-card-red", "nested": {"a": 1}},
    )


def test_append_then_read_round_trips_events_exactly(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    events = [_event(1), _event(2, "SEED_SET"), _event(3, "PICK_MADE")]
    for e in events:
        append_event(path, e)

    read_back = read_events(path)
    assert read_back == events


def test_append_is_additive_across_multiple_calls(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_event(path, _event(1))
    append_event(path, _event(2))
    assert len(read_events(path)) == 2

    append_event(path, _event(3))
    assert len(read_events(path)) == 3
    assert [e.event_id for e in read_events(path)] == [1, 2, 3]


def test_append_events_writes_multiple_in_one_call(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_events(path, [_event(1), _event(2), _event(3)])
    assert [e.event_id for e in read_events(path)] == [1, 2, 3]


def test_one_json_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_events(path, [_event(1), _event(2)])
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("{") and lines[0].endswith("}")


def test_iter_events_is_lazy_and_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_events(path, [_event(1), _event(2)])
    with path.open("a") as f:
        f.write("\n")  # a stray blank line must not break parsing

    events = list(iter_events(path))
    assert [e.event_id for e in events] == [1, 2]


def test_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "session-abc" / "events.jsonl"
    append_event(path, _event(1))
    assert path.exists()
    assert read_events(path) == [_event(1)]

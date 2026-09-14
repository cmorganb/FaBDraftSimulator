"""Append-only JSONL writer/reader for DraftEvent (plan section 5.5, 7).

Events are already schema-validated by construction: callers pass a
`DraftEvent` pydantic model (generated from contracts/draft_event.schema.json
in WP-03), so there is nothing further to validate here - `model_dump_json`
cannot produce a non-conformant line.

This module performs real filesystem I/O and is therefore the kind of thing
plan section 4.1 item 2 calls an "injected port": callers (CLI/API, not the
pure engine internals) decide when and where to persist events.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from fabdraft_core.contracts import DraftEvent


def append_event(path: Path, event: DraftEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json(by_alias=True))
        f.write("\n")


def append_events(path: Path, events: Iterable[DraftEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(event.model_dump_json(by_alias=True))
            f.write("\n")


def iter_events(path: Path) -> Iterator[DraftEvent]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield DraftEvent.model_validate_json(line)


def read_events(path: Path) -> list[DraftEvent]:
    return list(iter_events(path))

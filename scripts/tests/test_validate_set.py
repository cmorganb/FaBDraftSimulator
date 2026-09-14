"""Tests for the scripts/validate_set.py CLI gate (WP-02)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fabdraft_core.contracts import SetSnapshot
from scripts.validate_set import main, validate

REPO_ROOT = Path(__file__).resolve().parents[2]


def _minimal_card(uid: str, rarity: str, *, data_complete: bool = True) -> dict:
    return {
        "uid": uid,
        "set_code": "MOCK",
        "card_number": uid.upper(),
        "name": uid,
        "pitch": 1,
        "rarity": rarity,
        "types": ["Action"],
        "classes": [],
        "talents": [],
        "subtypes": [],
        "cost": 1,
        "power": 2,
        "defense": 2,
        "life": None,
        "intellect": None,
        "keywords": [],
        "functional_text": "",
        "specialization": None,
        "is_deck_card": True,
        "is_arena_card": False,
        "equipment_slot": None,
        "hands": None,
        "image_url": None,
        "double_faced_with": None,
        "draftable": True,
        "data_complete": data_complete,
    }


def _write_snapshot(path: Path, cards: list[dict], expected_counts: dict) -> None:
    snapshot = {
        "set_code": "MOCK",
        "name": "Mock",
        "release_date": "2026-01-01",
        "source": {"provider": "test", "commit": "n/a", "retrieved_at": "2026-01-01T00:00:00Z"},
        "expected_counts": expected_counts,
        "cards": cards,
        "integrity": {"counts_match": True, "incomplete_cards": []},
    }
    path.write_text(json.dumps(snapshot))


def _write_config(config_dir: Path, set_code: str, expected_counts: dict) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / f"{set_code.lower()}.expected_counts.json").write_text(
        json.dumps(expected_counts)
    )


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return tmp_path / "config"


def test_validate_passes_and_stamps_complete(tmp_path: Path, config_dir: Path) -> None:
    counts = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    _write_config(config_dir, "MOCK", counts)
    snapshot = SetSnapshot.model_validate(
        {
            "set_code": "MOCK",
            "name": "Mock",
            "release_date": "2026-01-01",
            "source": {
                "provider": "test",
                "commit": "n/a",
                "retrieved_at": "2026-01-01T00:00:00Z",
            },
            "expected_counts": counts,
            "cards": [_minimal_card("a", "C")],
            "integrity": {"counts_match": True, "incomplete_cards": []},
        }
    )
    stamped, status = validate(snapshot, counts, allow_incomplete=False)
    assert status == "complete"
    assert stamped.integrity.counts_match is True
    assert stamped.integrity.incomplete_cards == []


def test_validate_raises_when_counts_mismatch_and_not_allowed() -> None:
    counts_claimed = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    real_expected = {"total": 2, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 2, "B": 0}
    snapshot = SetSnapshot.model_validate(
        {
            "set_code": "MOCK",
            "name": "Mock",
            "release_date": "2026-01-01",
            "source": {
                "provider": "test",
                "commit": "n/a",
                "retrieved_at": "2026-01-01T00:00:00Z",
            },
            "expected_counts": counts_claimed,
            "cards": [_minimal_card("a", "C")],
            "integrity": {"counts_match": True, "incomplete_cards": []},
        }
    )
    from fabdraft_core.errors import DataIncompleteError

    with pytest.raises(DataIncompleteError):
        validate(snapshot, real_expected, allow_incomplete=False)


def test_cli_exits_zero_and_writes_out_file_on_success(tmp_path: Path, config_dir: Path) -> None:
    counts = {"total": 2, "F": 0, "V": 0, "L": 0, "M": 0, "R": 1, "C": 1, "B": 0}
    _write_config(config_dir, "MOCK", counts)
    in_path = tmp_path / "in.json"
    out_path = tmp_path / "out.json"
    _write_snapshot(in_path, [_minimal_card("a", "C"), _minimal_card("b", "R")], counts)

    exit_code = main(
        [
            "--in",
            str(in_path),
            "--out",
            str(out_path),
            "--config-dir",
            str(config_dir),
        ]
    )
    assert exit_code == 0
    assert out_path.exists()
    written = json.loads(out_path.read_text())
    assert written["integrity"]["counts_match"] is True


def test_cli_exits_nonzero_on_count_mismatch_without_allow_incomplete(
    tmp_path: Path, config_dir: Path
) -> None:
    real_counts = {"total": 5, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 5, "B": 0}
    _write_config(config_dir, "MOCK", real_counts)
    in_path = tmp_path / "in.json"
    # snapshot only has 1 card, but the real config expects 5
    claimed_counts = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    _write_snapshot(in_path, [_minimal_card("a", "C")], claimed_counts)

    exit_code = main(["--in", str(in_path), "--config-dir", str(config_dir)])
    assert exit_code == 1
    # nothing should have been written anywhere since no --out was given / gate refused


def test_cli_allow_incomplete_lets_a_mismatched_set_through_and_stamps_incomplete(
    tmp_path: Path, config_dir: Path
) -> None:
    real_counts = {"total": 5, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 5, "B": 0}
    _write_config(config_dir, "MOCK", real_counts)
    in_path = tmp_path / "in.json"
    out_path = tmp_path / "out.json"
    claimed_counts = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    _write_snapshot(in_path, [_minimal_card("a", "C")], claimed_counts)

    exit_code = main(
        [
            "--in",
            str(in_path),
            "--out",
            str(out_path),
            "--config-dir",
            str(config_dir),
            "--allow-incomplete",
        ]
    )
    assert exit_code == 0
    written = json.loads(out_path.read_text())
    assert written["integrity"]["counts_match"] is False


def test_cli_refuses_on_incomplete_cards_without_allow_incomplete(
    tmp_path: Path, config_dir: Path
) -> None:
    counts = {"total": 1, "F": 0, "V": 0, "L": 0, "M": 0, "R": 0, "C": 1, "B": 0}
    _write_config(config_dir, "MOCK", counts)
    in_path = tmp_path / "in.json"
    _write_snapshot(in_path, [_minimal_card("a", "C", data_complete=False)], counts)

    exit_code = main(["--in", str(in_path), "--config-dir", str(config_dir)])
    assert exit_code == 1


def test_real_fixture_set_passes_validation_against_its_own_config() -> None:
    """Integration test tying WP-01 and WP-02 together: the committed
    fixture set must actually pass its own gate.
    """
    fixture_path = REPO_ROOT / "data" / "fixtures" / "fixture_set.json"
    config_dir = REPO_ROOT / "data" / "config"
    exit_code = main(["--in", str(fixture_path), "--config-dir", str(config_dir)])
    assert exit_code == 0

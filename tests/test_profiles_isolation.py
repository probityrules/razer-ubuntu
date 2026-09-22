"""Profile isolation and identity tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tartarus_v2 import actions
from tartarus_v2 import profiles as prof


@pytest.fixture()
def profile_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path


def test_load_profile_forces_filename_name(profile_home: Path) -> None:
    path = prof.profiles_dir() / "arena.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"name": "default", "standard": {"bindings": {"key_01": "z"}}}),
        encoding="utf-8",
    )
    data = prof.load_profile("arena")
    assert data["name"] == "arena"
    assert data["standard"]["bindings"]["key_01"] == "z"


def test_cloned_profiles_are_independent(profile_home: Path) -> None:
    prof.ensure_default_profile()
    actions.create_profile("one")
    actions.create_profile("two")

    actions.save_bindings("one", "standard", {"key_01": "x"}, "mode")
    actions.save_bindings("two", "standard", {"key_01": "y"}, "mode")

    one = prof.load_profile("one")
    two = prof.load_profile("two")
    assert one["name"] == "one"
    assert two["name"] == "two"
    assert one["standard"]["bindings"]["key_01"] == "x"
    assert two["standard"]["bindings"]["key_01"] == "y"

    # Mutating one in memory must not affect the other on disk/reload.
    one["standard"]["bindings"]["key_01"] = "Q"
    two_again = prof.load_profile("two")
    assert two_again["standard"]["bindings"]["key_01"] == "y"

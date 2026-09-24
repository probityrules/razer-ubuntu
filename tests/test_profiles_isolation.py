"""Profile isolation and identity tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tartarus_v2 import actions
from tartarus_v2 import profiles as prof
from tartarus_v2.gui.controllers import BindingsController


@pytest.fixture()
def profile_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path


def test_key_20_is_the_thumb_key(profile_home: Path) -> None:
    """Legacy profiles that stored thumb and key_20 separately collapse to one key."""
    path = prof.profiles_dir() / "legacy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "name": "legacy",
                "hypershift_key": "thumb",
                "standard": {"bindings": {"key_20": "n", "thumb": "space", "key_19": "b"}},
                "hypershift": {"bindings": {"key_20": "F17", "thumb": "enter"}},
            }
        ),
        encoding="utf-8",
    )
    data = prof.load_profile("legacy")
    assert data["hypershift_key"] == "key_20"
    assert data["standard"]["bindings"]["key_20"] == "space"
    assert data["hypershift"]["bindings"]["key_20"] == "enter"
    assert "thumb" not in data["standard"]["bindings"]
    assert "thumb" not in data["hypershift"]["bindings"]
    assert data["standard"]["bindings"]["key_19"] == "b"

    prof.save_profile(data, "legacy")
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["hypershift_key"] == "key_20"
    assert "thumb" not in stored["standard"]["bindings"]


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


def test_save_bindings_does_not_overwrite_sibling_profile(profile_home: Path) -> None:
    """Editing profile A must leave profile B's file untouched."""
    prof.ensure_default_profile()
    actions.create_profile("alpha")
    actions.create_profile("beta")

    actions.save_bindings(
        "alpha",
        "standard",
        {"key_01": "a", "key_02": "b"},
        "mode",
    )
    actions.save_bindings(
        "beta",
        "standard",
        {"key_01": "1", "key_02": "2"},
        "mode",
    )

    # Simulate Bindings Apply on alpha only (both layers, like the GUI).
    actions.save_bindings("alpha", "standard", {"key_01": "Z", "key_02": "b"}, "mode")
    actions.save_bindings("alpha", "hypershift", {"key_01": "F1"}, "mode")

    beta_disk = json.loads((prof.profiles_dir() / "beta.json").read_text(encoding="utf-8"))
    assert beta_disk["standard"]["bindings"]["key_01"] == "1"
    assert beta_disk["standard"]["bindings"]["key_02"] == "2"

    alpha = prof.load_profile("alpha")
    assert alpha["standard"]["bindings"]["key_01"] == "Z"
    assert alpha["hypershift"]["bindings"]["key_01"] == "F1"


def test_stale_embedded_name_cannot_redirect_save(profile_home: Path) -> None:
    """A JSON whose 'name' claims another profile must still save to the filename."""
    prof.ensure_default_profile()
    actions.create_profile("real")
    actions.create_profile("decoy")

    actions.save_bindings("decoy", "standard", {"key_01": "keep-me"}, "mode")

    # Poison the real file's embedded name (pre-0.6.1 footgun).
    real_path = prof.profiles_dir() / "real.json"
    poisoned = json.loads(real_path.read_text(encoding="utf-8"))
    poisoned["name"] = "decoy"
    poisoned["standard"] = {"bindings": {"key_01": "from-real"}}
    real_path.write_text(json.dumps(poisoned, indent=2) + "\n", encoding="utf-8")

    loaded = prof.load_profile("real")
    assert loaded["name"] == "real"
    actions.save_bindings("real", "standard", {"key_01": "saved-as-real"}, "mode")

    decoy = prof.load_profile("decoy")
    assert decoy["standard"]["bindings"]["key_01"] == "keep-me"
    real = prof.load_profile("real")
    assert real["name"] == "real"
    assert real["standard"]["bindings"]["key_01"] == "saved-as-real"


def test_gui_bindings_controller_apply_switch_preserves_siblings(
    profile_home: Path,
) -> None:
    """BindingsController path used by the GUI must not cross-write profiles."""
    prof.ensure_default_profile()
    actions.create_profile("p1")
    actions.create_profile("p2")
    actions.save_bindings("p1", "standard", {"key_01": "one"}, "mode")
    actions.save_bindings("p2", "standard", {"key_01": "two"}, "mode")

    ctrl = BindingsController()

    # Load / edit / apply p1 (mirrors draft Apply all).
    draft = ctrl.load_bindings("p1")
    assert draft["name"] == "p1"
    std = dict((draft.get("standard") or {}).get("bindings") or {})
    hyp = dict((draft.get("hypershift") or {}).get("bindings") or {})
    std["key_01"] = "CHANGED"
    ctrl.save_bindings("p1", "standard", std, draft.get("hypershift_key") or "mode")
    ctrl.save_bindings("p1", "hypershift", hyp, draft.get("hypershift_key") or "mode")

    # Switch to p2 and load — must still be the original.
    other = ctrl.load_bindings("p2")
    assert other["name"] == "p2"
    assert other["standard"]["bindings"]["key_01"] == "two"

    # Mutating the returned draft must not rewrite p2 on disk.
    other["standard"]["bindings"]["key_01"] = "MUTATED-IN-MEMORY"
    p2_disk = prof.load_profile("p2")
    assert p2_disk["standard"]["bindings"]["key_01"] == "two"

    p1_disk = prof.load_profile("p1")
    assert p1_disk["standard"]["bindings"]["key_01"] == "CHANGED"


def test_shared_bindings_dict_argument_does_not_alias_profiles(
    profile_home: Path,
) -> None:
    """Caller reusing one bindings dict must not couple two profile files."""
    prof.ensure_default_profile()
    actions.create_profile("left")
    actions.create_profile("right")

    shared = {"key_01": "shared"}
    actions.save_bindings("left", "standard", shared, "mode")
    shared["key_01"] = "only-right"
    actions.save_bindings("right", "standard", shared, "mode")

    # Further mutate the caller's dict — disk copies must stay frozen.
    shared["key_01"] = "caller-mutated"

    left = prof.load_profile("left")
    right = prof.load_profile("right")
    assert left["standard"]["bindings"]["key_01"] == "shared"
    assert right["standard"]["bindings"]["key_01"] == "only-right"


def test_new_profile_clones_active_but_then_diverges(profile_home: Path) -> None:
    """New profiles start as a clone (expected); later edits must not sync both ways."""
    prof.ensure_default_profile()
    actions.use_profile("default")
    actions.save_bindings("default", "standard", {"key_01": "base"}, "mode")
    actions.create_profile("clone")

    clone = prof.load_profile("clone")
    assert clone["standard"]["bindings"]["key_01"] == "base"

    actions.save_bindings("default", "standard", {"key_01": "default-only"}, "mode")
    clone_again = prof.load_profile("clone")
    assert clone_again["standard"]["bindings"]["key_01"] == "base"

    actions.save_bindings("clone", "standard", {"key_01": "clone-only"}, "mode")
    default_again = prof.load_profile("default")
    assert default_again["standard"]["bindings"]["key_01"] == "default-only"

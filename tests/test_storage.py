"""Storage layer: crash-safe atomic writes + one-time legacy migration.

Runs against the fake in-memory Store in conftest. The real atomicity lives in
HA's Store; these lock down our migration/round-trip logic and, crucially,
that the truncate-then-write path that caused issue #104 is gone (we only ever
hand the store a complete dict, via async_save, never async_delay_save).
"""
import asyncio
from pathlib import Path

import bps.storage as st
from conftest import make_hass


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _legacy_layout(hass):
    d = Path(hass.config.path("www", "bps_maps"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "bpsdata.txt"


def _legacy_calib(hass):
    d = Path(hass.config.path("www", "bps_maps"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "bps_calibration_state.json"


# --- fresh install ----------------------------------------------------------
def test_fresh_install_is_empty(tmp_path):
    hass = make_hass(tmp_path)
    run(st.migrate_legacy(hass))   # nothing to migrate
    run(st.load_bps_data(hass))
    assert st.get_bps_data(hass) == []           # matches old empty-file behaviour
    assert st.get_bps_data_for_edit(hass) is None


# --- migration --------------------------------------------------------------
def test_migrate_valid_layout(tmp_path):
    hass = make_hass(tmp_path)
    legacy = _legacy_layout(hass)
    legacy.write_text('{"floor":[{"name":"Home"}]}')
    run(st.migrate_legacy(hass))
    run(st.load_bps_data(hass))
    assert st.get_bps_data(hass) == {"floor": [{"name": "Home"}]}
    assert not legacy.exists()                    # old www copy removed (closes /local exposure)


def test_migrate_zero_byte_is_the_issue_104_guard(tmp_path):
    hass = make_hass(tmp_path)
    legacy = _legacy_layout(hass)
    legacy.write_text("")                         # the 0-byte artifact
    run(st.migrate_legacy(hass))                  # must not raise
    run(st.load_bps_data(hass))
    assert st.get_bps_data(hass) == []
    assert not legacy.exists()                    # unrecoverable blank file cleaned up


def test_migrate_corrupt_layout_is_preserved(tmp_path):
    hass = make_hass(tmp_path)
    legacy = _legacy_layout(hass)
    legacy.write_text('{"floor": [ this is not json')
    run(st.migrate_legacy(hass))
    run(st.load_bps_data(hass))
    assert st.get_bps_data(hass) == []            # start empty...
    assert legacy.exists()                        # ...but keep the file for manual recovery


def test_migrate_does_not_overwrite_populated_store(tmp_path):
    hass = make_hass(tmp_path)
    run(st.save_bps_data(hass, {"floor": [{"name": "Already"}]}))   # store already owns data
    legacy = _legacy_layout(hass)
    legacy.write_text('{"floor":[{"name":"Stale"}]}')
    run(st.migrate_legacy(hass))                  # store non-empty: don't re-import
    run(st.load_bps_data(hass))
    assert st.get_bps_data(hass) == {"floor": [{"name": "Already"}]}  # store data wins
    assert not legacy.exists()                    # stale exposed copy cleaned up


# --- save / load round-trip -------------------------------------------------
def test_save_survives_restart(tmp_path):
    hass = make_hass(tmp_path)
    run(st.save_bps_data(hass, {"floor": [{"name": "Home"}]}))
    # Simulate a restart: fresh in-memory cache, same .storage backing.
    hass.data.get(st.DOMAIN, {}).pop("layout", None)
    run(st.load_bps_data(hass))
    assert st.get_bps_data(hass) == {"floor": [{"name": "Home"}]}


def test_save_is_immediate_and_never_truncates(tmp_path):
    hass = make_hass(tmp_path)
    run(st.save_bps_data(hass, {"floor": []}))
    # async_save (atomic), never the debounced async_delay_save.
    assert hass._store_delay_saves == []
    assert [k for k, _ in hass._store_saves] == ["bps"]
    # The store is only ever handed a complete object — never "" — so the old
    # truncate-then-write 0-byte path (issue #104) cannot recur.
    assert all(isinstance(v, (dict, list)) for _, v in hass._store_saves)


def test_get_for_edit_returns_a_copy(tmp_path):
    hass = make_hass(tmp_path)
    run(st.save_bps_data(hass, {"floor": [{"name": "Home"}]}))
    editable = st.get_bps_data_for_edit(hass)
    editable["floor"].append({"name": "Injected"})
    # Mutating the editable copy must not touch the live cache the loop reads.
    assert st.get_bps_data(hass) == {"floor": [{"name": "Home"}]}


# --- calibration state ------------------------------------------------------
def test_calib_state_roundtrip(tmp_path):
    hass = make_hass(tmp_path)
    run(st.save_calib_state(hass, {"results": {"F": 1}, "saved_at": 123}))
    assert run(st.load_calib_state(hass)) == {"results": {"F": 1}, "saved_at": 123}


def test_calib_state_migrates_and_removes_legacy(tmp_path):
    hass = make_hass(tmp_path)
    legacy = _legacy_calib(hass)
    legacy.write_text('{"results": {"F": 2}}')
    run(st.migrate_legacy(hass))
    assert run(st.load_calib_state(hass)) == {"results": {"F": 2}}
    assert not legacy.exists()


# --- resilience -------------------------------------------------------------
def test_corrupt_store_starts_empty_not_crash(tmp_path):
    # A corrupt/unreadable .storage file must degrade (start empty), not abort
    # setup the way an unguarded Store.async_load() would.
    hass = make_hass(tmp_path)
    hass._store_raise_on_load = {"bps", "bps_calibration_state"}
    _legacy_layout(hass).write_text('{"floor":[{"name":"Home"}]}')
    run(st.migrate_legacy(hass))                 # must not raise
    run(st.load_bps_data(hass))                  # must not raise
    assert st.get_bps_data(hass) == []
    assert run(st.load_calib_state(hass)) is None
    # Corrupt store: don't touch the possibly-recoverable legacy file.
    assert _legacy_layout(hass).exists()


def test_legacy_cleanup_retries_when_store_already_populated(tmp_path):
    # A leftover www copy (failed prior delete, or restored from backup) must
    # be cleaned up on a later boot even though the store already has the data.
    hass = make_hass(tmp_path)
    run(st.save_bps_data(hass, {"floor": [{"name": "Home"}]}))
    stale = _legacy_layout(hass)
    stale.write_text('{"floor":[{"name":"Home"}]}')   # reappeared /local-exposed copy
    run(st.migrate_legacy(hass))
    assert not stale.exists()                          # removed despite store non-empty
    assert st.get_bps_data(hass) == {"floor": [{"name": "Home"}]}  # data untouched

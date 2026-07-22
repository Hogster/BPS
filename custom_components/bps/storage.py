"""Persistent storage for BPS layout + calibration state.

The floor/zone/receiver layout and the calibration state used to live as flat
files in ``www/bps_maps`` (``bpsdata.txt`` / ``bps_calibration_state.json``),
written with ``open(path, "w")`` — which truncates to zero *before* writing, so
an interrupted write left a 0-byte file and wiped the config (issue #104).
Being under ``www/`` also made them readable unauthenticated via ``/local/``.

Both now live in Home Assistant's ``Store`` (``config/.storage/``):
``Store.async_save`` writes atomically (temp file + ``os.replace`` — the live
file is never truncated), and ``.storage`` is not web-served. This module is
the single owner of that data and imports nothing from the rest of the package
(so both ``__init__`` and ``calibration`` can import it without a cycle).
"""
import asyncio
import copy
import json
import logging
from pathlib import Path

import aiofiles
import aiofiles.os
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bps"
STORAGE_VERSION = 1
STORAGE_KEY_LAYOUT = "bps"                       # -> config/.storage/bps
STORAGE_KEY_CALIB = "bps_calibration_state"      # -> config/.storage/bps_calibration_state

# Serializes read-modify-write sequences on the layout across every writer
# (panel save + calibration). Lives here so both importers share one lock
# without an import cycle (was previously defined in calibration.py).
BPS_FILE_LOCK = asyncio.Lock()


def _legacy_layout_path(hass) -> Path:
    return Path(hass.config.path("www/bps_maps")) / "bpsdata.txt"


def _legacy_calib_path(hass) -> Path:
    return Path(hass.config.path("www/bps_maps")) / "bps_calibration_state.json"


def _bucket(hass) -> dict:
    return hass.data.setdefault(DOMAIN, {})


def _layout_store(hass) -> Store:
    bucket = _bucket(hass)
    store = bucket.get("_layout_store")
    if store is None:
        store = bucket["_layout_store"] = Store(hass, STORAGE_VERSION, STORAGE_KEY_LAYOUT)
    return store


def _calib_store(hass) -> Store:
    bucket = _bucket(hass)
    store = bucket.get("_calib_store")
    if store is None:
        store = bucket["_calib_store"] = Store(hass, STORAGE_VERSION, STORAGE_KEY_CALIB)
    return store


# --- Layout (bpsdata) --------------------------------------------------------

def get_bps_data(hass):
    """The cached layout for READ-ONLY consumers.

    Defaults to ``[]`` on a fresh install, matching the old empty-file
    behaviour (a populated layout is a dict; consumers guard with isinstance).
    """
    return _bucket(hass).get("layout", [])


def get_bps_data_for_edit(hass):
    """A deep copy of the layout for read-modify-write callers (calibration).

    Returns ``None`` when there is no layout yet — matching the old
    ``_read_coords`` contract — so callers must never mutate the live cache
    the tracking loop reads.
    """
    data = get_bps_data(hass)
    return copy.deepcopy(data) if isinstance(data, dict) else None


async def load_bps_data(hass):
    """Load the layout from the store into the in-memory cache (at setup).

    A corrupt/unreadable store must not abort setup — the old flat-file reader
    tolerated bad JSON and ran with an empty layout, so keep that resilience.
    """
    try:
        data = await _layout_store(hass).async_load()
    except Exception as e:
        _LOGGER.error("Could not load layout from storage; starting empty: %s", e)
        data = None
    _bucket(hass)["layout"] = data if data is not None else []
    return _bucket(hass)["layout"]


async def save_bps_data(hass, data) -> None:
    """Persist the layout dict atomically, THEN refresh the cache.

    Uses ``async_save`` (immediate atomic write), never ``async_delay_save`` —
    a debounced write could still be lost on a crash inside the delay window.
    Persist first so a raising write leaves the cache matching what survives a
    restart rather than running ahead of disk.
    """
    await _layout_store(hass).async_save(data)
    _bucket(hass)["layout"] = data


# --- Calibration state -------------------------------------------------------

async def load_calib_state(hass):
    """The persisted calibration state, or None on first run / if unreadable."""
    try:
        return await _calib_store(hass).async_load()
    except Exception as e:
        _LOGGER.warning("Could not load calibration state; starting cold: %s", e)
        return None


async def save_calib_state(hass, payload) -> None:
    await _calib_store(hass).async_save(payload)


# --- One-time migration of the old flat files -------------------------------

async def _read_legacy(path: Path):
    """Read a legacy file. Returns (content, existed)."""
    try:
        async with aiofiles.open(path, "r") as f:
            return await f.read(), True
    except FileNotFoundError:
        return None, False
    except OSError as e:
        _LOGGER.warning("Could not read legacy file %s: %s", path, e)
        return None, True  # exists but unreadable — don't delete it


async def _remove_legacy(path: Path) -> None:
    if not path.exists():
        return
    try:
        await aiofiles.os.remove(path)
        _LOGGER.info("Removed legacy file %s (data now lives in .storage)", path.name)
    except OSError as e:
        _LOGGER.error(
            "Could not remove legacy %s — it stays readable via /local until "
            "removed by hand: %s", path.name, e)


async def migrate_legacy(hass) -> None:
    """Move the old ``www/bps_maps`` files into the store, once.

    Idempotent: only runs while the store is still empty. For each file:
    a blank/whitespace file (the issue-#104 artifact — no recoverable data) is
    deleted; a corrupt-but-non-empty file is LEFT in place (may be
    hand-recoverable); a valid file is saved to the store, verified, and only
    then deleted — closing the ``/local/`` exposure. Map images stay in
    ``www/bps_maps`` (served via ``/local/``) and are untouched.
    """
    await _migrate_one(
        _layout_store(hass), _legacy_layout_path(hass), "layout",
        lambda parsed: isinstance(parsed, (dict, list)),
    )
    await _migrate_one(
        _calib_store(hass), _legacy_calib_path(hass), "calibration state",
        lambda parsed: isinstance(parsed, dict),
    )


async def _migrate_one(store: Store, legacy: Path, label: str, is_valid) -> None:
    try:
        existing = await store.async_load()
    except Exception as e:
        # Corrupt/unreadable store: don't migrate over it (may be recoverable)
        # and don't touch the legacy file — just don't crash setup.
        _LOGGER.warning("Could not read %s store; leaving legacy file: %s", label, e)
        return
    if existing is not None:
        # Store already owns the data. Retry the cleanup every boot so a
        # previously-failed delete (or a legacy file restored from a backup)
        # can't linger /local-exposed forever.
        await _remove_legacy(legacy)
        return
    content, existed = await _read_legacy(legacy)
    if not existed or content is None:
        return  # fresh install, or unreadable — leave it
    if not content.strip():
        # 0-byte / whitespace: the data-loss artifact, nothing to recover.
        await _remove_legacy(legacy)
        return
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        _LOGGER.warning(
            "Legacy %s file %s is not valid JSON; leaving it in place for "
            "manual recovery and starting empty", label, legacy.name)
        return
    if not is_valid(parsed):
        _LOGGER.warning("Legacy %s file %s has unexpected shape; leaving it", label, legacy.name)
        return
    await store.async_save(parsed)
    if await store.async_load() is None:
        _LOGGER.error("Migrating %s to storage failed to verify; keeping %s", label, legacy.name)
        return
    _LOGGER.info("Migrated %s from %s into .storage", label, legacy.name)
    await _remove_legacy(legacy)

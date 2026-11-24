"""What a suggestion does, exactly: its base changes plus people's own extras.

A suggestion has two parts:

* **Base changes** (``changes`` in ``bps.suggest``): exact levels for lights
  that are linked to the suggestion's zone, and nothing else. BPS refuses a
  definition that touches anything outside the zone, and never runs scripts
  for it. An administrator can change a level or leave a light out
  (*overrides*, Learned tab).
* **Extras**: things people add themselves in the Learned tab: more lights
  (any zone), speakers (one or all, mute / pause / volume) and scripts,
  scenes or automations they pick. Each extra has a set of people it applies
  to; it runs only when one of them answers yes (or it runs automatically
  for one of them). Somebody else's yes never runs your extras.

Safety: a light outside the suggestion's zone is skipped when someone who
is not part of the decision is in that light's zone.

Everything here is pure (plain data in, plain data out) so it can be tested
without Home Assistant.
"""
from __future__ import annotations

import re
import uuid

ALL_SPEAKERS = "all_speakers"
RUN_DOMAINS = ("script", "scene", "automation")
MEDIA_DO = ("mute", "pause", "volume")


# --- values -----------------------------------------------------------------------
def light_spec(value) -> dict:
    """30 / "30%" / "off" / "on" / {brightness_pct, color_temp_kelvin, rgb_color}."""
    if isinstance(value, bool):
        return {"state": "on" if value else "off"}
    if isinstance(value, (int, float)):
        value = {"brightness_pct": value}
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("off", "on"):
            return {"state": v}
        m = re.fullmatch(r"(\d{1,3})\s*%?", v)
        if not m:
            raise ValueError(f"light level {value!r}: use a percentage, 'on' or 'off'")
        value = {"brightness_pct": int(m.group(1))}
    if not isinstance(value, dict):
        raise ValueError(f"light level {value!r}: use a percentage, 'on' or 'off'")
    if str(value.get("state", "on")).lower() == "off":
        return {"state": "off"}
    out = {"state": "on"}
    pct = value.get("brightness_pct", value.get("brightness"))
    if pct is not None:
        try:
            pct = int(round(float(str(pct).rstrip("%"))))
        except ValueError:
            raise ValueError(f"brightness {pct!r} is not a number") from None
        if not 0 <= pct <= 100:
            raise ValueError("brightness must be 0-100 %")
        if pct == 0:
            return {"state": "off"}
        out["brightness_pct"] = pct
    k = value.get("color_temp_kelvin", value.get("kelvin"))
    if k is not None:
        k = int(k)
        if not 1500 <= k <= 9000:
            raise ValueError("color temperature must be 1500-9000 K")
        out["color_temp_kelvin"] = k
    rgb = value.get("rgb_color")
    if rgb is not None:
        if not (isinstance(rgb, (list, tuple)) and len(rgb) == 3
                and all(isinstance(c, int) and 0 <= c <= 255 for c in rgb)):
            raise ValueError("rgb_color must be [r, g, b] with 0-255")
        out["rgb_color"] = list(rgb)
    return out


def media_spec(value) -> dict:
    """"mute" / "pause" / {"media": "volume", "volume": 20}."""
    if isinstance(value, str):
        value = {"media": value.strip().lower()}
    if not isinstance(value, dict) or value.get("media") not in MEDIA_DO:
        raise ValueError("speakers: use mute, pause or volume")
    if value["media"] != "volume":
        return {"media": value["media"]}
    try:
        vol = int(round(float(value.get("volume"))))
    except (TypeError, ValueError):
        raise ValueError("volume must be 0-100 %") from None
    if not 0 <= vol <= 100:
        raise ValueError("volume must be 0-100 %")
    return {"media": "volume", "volume": vol}


def kind_of(entity) -> str:
    if entity == ALL_SPEAKERS or entity.startswith("media_player."):
        return "media"
    domain = entity.split(".", 1)[0]
    if domain == "light":
        return "light"
    if domain in RUN_DOMAINS:
        return "run"
    raise ValueError(f"{entity}: only lights, speakers, scripts, scenes and automations")


def spec_for(entity, value) -> dict:
    kind = kind_of(entity)
    if kind == "light":
        return light_spec(value)
    if kind == "media":
        return media_spec(value)
    return {"run": True}


# --- definitions ------------------------------------------------------------------
def parse_changes(raw) -> dict:
    """The ``changes`` field of bps.suggest -> {light entity: spec}."""
    if isinstance(raw, list):   # [{entity_id, ...level}] also accepted
        items = {}
        for it in raw:
            if not isinstance(it, dict) or not it.get("entity_id"):
                raise ValueError("changes: each item needs entity_id")
            val = {k: v for k, v in it.items() if k != "entity_id"}
            items[str(it["entity_id"])] = val.get("level", val) if "level" in val else val
        raw = items
    if not isinstance(raw, dict) or not raw:
        raise ValueError("changes is required: the zone's lights and their levels")
    out = {}
    for eid, val in raw.items():
        eid = str(eid).strip()
        if not eid.startswith("light."):
            raise ValueError(f"changes may only contain lights ({eid})")
        out[eid] = light_spec(val)
    return out


def check_zone(changes, zone, zone_lights) -> None:
    """Base changes may only touch lights linked to the suggestion's zone."""
    outside = sorted(e for e in changes if e not in set(zone_lights))
    if outside:
        raise ValueError(
            f"{', '.join(outside)} {'is' if len(outside) == 1 else 'are'} not linked to the zone "
            f"{zone}. A suggestion only changes the zone's own lights: link them under "
            f"Zone links -> Lights, or add other things as your own extras in the Learned tab.")


def base_changes(changes, overrides) -> dict:
    """Base changes after the administrator's overrides ({"skip": True} drops one)."""
    out = {}
    for eid, spec in (changes or {}).items():
        o = (overrides or {}).get(eid)
        if o and o.get("skip"):
            continue
        out[eid] = dict(o) if o else dict(spec)
    return out


# --- extras -----------------------------------------------------------------------
def make_extra(raw, people_known, extra_id=None) -> dict:
    """Validate an extra from the panel: {entity, do, people}."""
    if not isinstance(raw, dict):
        raise ValueError("extra must be an object")
    entity = str(raw.get("entity") or "").strip()
    if not entity:
        raise ValueError("pick what the extra should change")
    spec = spec_for(entity, raw.get("do", True))
    people = sorted({str(p) for p in raw.get("people") or []})
    if not people:
        raise ValueError("tick at least one person")
    unknown = [p for p in people if p not in people_known]
    if unknown:
        raise ValueError(f"unknown person {unknown[0]}")
    return {"id": extra_id or raw.get("id") or uuid.uuid4().hex[:10],
            "entity": entity, "do": spec, "people": people}


def may_change_extra(old, new, me, can_configure) -> bool:
    """Who may add / edit / delete an extra (old None = add, new None = delete).

    Configurers: anything. Everyone else only decides for themselves: they may
    tick or untick their own box, and change or delete an extra only when it
    applies to nobody but them.
    """
    if can_configure:
        return True
    if not me:
        return False
    mine_only = lambda e: e is not None and set(e["people"]) <= {me}
    if old is None:
        return mine_only(new)
    if new is None:
        return mine_only(old)
    if mine_only(old) and mine_only(new):
        return True
    same = old["entity"] == new["entity"] and old["do"] == new["do"]
    return same and (set(old["people"]) ^ set(new["people"])) <= {me}


def visible_extras(extras, me, is_admin):
    return [dict(e) for e in extras or [] if is_admin or (me and me in e["people"])]


# --- the plan ---------------------------------------------------------------------
def plan(d, overrides, extras, deciders, *, zone_lights, zone_of, occupants, speakers):
    """Steps for the people who decided (answered yes / auto).

    d:          the suggestion definition (zone, changes)
    zone_lights: lights linked to d's zone now (a light unlinked since the
                 definition was made is no longer changed)
    zone_of:    entity -> zone or None
    occupants:  zone -> [person]
    speakers:   all speakers in the house (for ALL_SPEAKERS)

    Returns [{"entity", "do", "extra", "zone"}] and skipped [{"entity", "reason", "zone"}].
    """
    deciders = set(deciders)
    steps, skipped, seen = [], [], set()
    linked = set(zone_lights)
    for eid, spec in base_changes(d.get("changes"), overrides).items():
        if eid not in linked:
            skipped.append({"entity": eid, "reason": "not_linked", "zone": d.get("zone")})
            continue
        steps.append({"entity": eid, "do": spec, "extra": False, "zone": d.get("zone")})
        seen.add(eid)
    for ex in extras or []:
        if not deciders & set(ex["people"]):
            continue
        targets = list(speakers) if ex["entity"] == ALL_SPEAKERS else [ex["entity"]]
        for eid in targets:
            zone = zone_of(eid)
            if eid.startswith("light.") and zone and zone != d.get("zone"):
                others = set(occupants(zone)) - deciders
                if others:
                    skipped.append({"entity": eid, "reason": "someone_there", "zone": zone})
                    continue
            if eid in seen and not ex["entity"] == ALL_SPEAKERS:
                steps = [s for s in steps if s["entity"] != eid]   # your own level wins
            elif eid in seen:
                continue
            steps.append({"entity": eid, "do": ex["do"], "extra": True, "zone": zone,
                          "group": ex["entity"] if ex["entity"] == ALL_SPEAKERS else None})
            seen.add(eid)
    return steps, skipped


def service_calls(steps) -> list:
    """(domain, service, data) for each step."""
    calls = []
    for s in steps:
        eid, do = s["entity"], s["do"]
        domain = eid.split(".", 1)[0]
        if domain == "light":
            if do.get("state") == "off":
                calls.append(("light", "turn_off", {"entity_id": eid}))
            else:
                data = {"entity_id": eid}
                for k in ("brightness_pct", "color_temp_kelvin", "rgb_color"):
                    if k in do:
                        data[k] = do[k]
                calls.append(("light", "turn_on", data))
        elif domain == "media_player":
            if do["media"] == "mute":
                calls.append(("media_player", "volume_mute", {"entity_id": eid, "is_volume_muted": True}))
            elif do["media"] == "pause":
                calls.append(("media_player", "media_pause", {"entity_id": eid}))
            else:
                calls.append(("media_player", "volume_set",
                              {"entity_id": eid, "volume_level": round(do["volume"] / 100, 2)}))
        elif domain == "automation":
            calls.append(("automation", "trigger", {"entity_id": eid}))
        else:
            calls.append((domain, "turn_on", {"entity_id": eid}))
    return calls


def undo_entities(steps) -> list:
    """What an Undo can restore: lights and speakers (not scripts/automations)."""
    return sorted({s["entity"] for s in steps if s["entity"].split(".", 1)[0] in ("light", "media_player")})


def describe(do, t) -> str:
    """One step's effect in words; t(key) gives the localized word."""
    if do.get("run"):
        return t("do_run")
    if "media" in do:
        if do["media"] == "volume":
            return t("do_volume").format(do["volume"])
        return t(f"do_{do['media']}")
    if do.get("state") == "off":
        return t("do_off")
    parts = []
    if "brightness_pct" in do:
        parts.append(f"{do['brightness_pct']} %")
    if "color_temp_kelvin" in do:
        parts.append(f"{do['color_temp_kelvin']} K")
    if "rgb_color" in do:
        parts.append(t("do_color"))
    return " ".join(parts) or t("do_on")


def summary(steps, name_of, t, zone=None) -> str:
    """'Ceiling 30 % · Spots off · 🔇 All speakers (whole house)' for a notification."""
    out, groups = [], set()
    for s in steps:
        if s.get("group"):
            if s["group"] in groups:
                continue
            groups.add(s["group"])
            out.append(f"{t('all_speakers')} {describe(s['do'], t)}")
            continue
        if s["entity"].split(".", 1)[0] in RUN_DOMAINS:
            out.append(f"{describe(s['do'], t)} {name_of(s['entity'])}")
            continue
        text = f"{name_of(s['entity'])} {describe(s['do'], t)}"
        if s.get("zone") and zone and s["zone"] != zone:
            text += f" ({s['zone']})"
        out.append(text)
    return " · ".join(out)


# --- the Learned tab --------------------------------------------------------------
def learned_view(d, overrides, extras, zone_lights, name_of, zone_of):
    """Base changes (with the administrator's overrides) and extras, for the panel."""
    overrides = overrides or {}
    linked = set(zone_lights)
    base = []
    for eid, spec in (d.get("changes") or {}).items():
        o = overrides.get(eid)
        base.append({"entity": eid, "name": name_of(eid), "default": spec,
                     "do": spec if not o or o.get("skip") else o,
                     "overridden": bool(o and not o.get("skip")), "skip": bool(o and o.get("skip")),
                     "linked": eid in linked})
    ext = [{**e, "name": name_of(e["entity"]) if e["entity"] != ALL_SPEAKERS else None,
            "zone": zone_of(e["entity"]) if e["entity"] != ALL_SPEAKERS else None}
           for e in extras or []]
    return {"base": base, "extras": ext}


def set_override(overrides, entity, value) -> None:
    """value None: back to the definition; "skip": leave the light out; else a level."""
    if value is None:
        overrides.pop(entity, None)
    elif value == "skip":
        overrides[entity] = {"skip": True}
    else:
        overrides[entity] = light_spec(value)

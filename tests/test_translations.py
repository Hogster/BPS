"""Swedish and English ship by default: every text exists in both."""
import json
import re
from pathlib import Path

from bps.texts import TEXTS

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "bps"


def _keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out |= _keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {prefix + k}
    return out


def _services(text):
    """{service: {"fields": {name: ...}}} from services.yaml (no yaml dependency)."""
    out, cur, in_fields = {}, None, False
    for line in text.splitlines():
        if re.match(r"^[a-z_]+:\s*$", line):
            cur = out.setdefault(line.split(":")[0], {"fields": {}})
            in_fields = False
        elif re.match(r"^  fields:\s*$", line):
            in_fields = True
        elif in_fields and cur is not None and re.match(r"^    [a-z_]+:\s*$", line):
            cur["fields"][line.strip()[:-1]] = {}
    return out


def test_notification_texts_complete():
    assert set(TEXTS["sv"]) == set(TEXTS["en"])


def test_ha_translations_match_and_cover_services():
    en = json.loads((ROOT / "translations" / "en.json").read_text())
    sv = json.loads((ROOT / "translations" / "sv.json").read_text())
    assert _keys(en) == _keys(sv)
    services = _services((ROOT / "services.yaml").read_text())
    assert set(services) == set(en["services"])
    for name, svc in services.items():
        assert set((svc or {}).get("fields") or {}) == set(en["services"][name]["fields"])


def test_panel_dictionary_has_no_duplicate_keys():
    src = (ROOT / "frontend" / "i18n.js").read_text()
    block = src[src.index("const TEXT = { sv: {"):src.index("const HTML")]
    keys = re.findall(r'^\s*"((?:[^"\\]|\\.)*)":', block, re.M)
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, dupes

"""The translation files stay in step with each other."""
from __future__ import annotations

import json
from pathlib import Path

TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / "leakomatic" / "translations"


def _keys(obj: dict, prefix: str = "") -> set[str]:
    keys = set()
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        keys |= _keys(value, path) if isinstance(value, dict) else {path}
    return keys


def _load(language: str) -> dict:
    return json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))


def test_swedish_has_the_same_keys_as_english() -> None:
    assert _keys(_load("sv")) == _keys(_load("en"))


def test_only_language_files() -> None:
    """HA-206: a custom integration reads translations/<language>.json only; strings.json there was never used."""
    assert sorted(p.name for p in TRANSLATIONS.iterdir()) == ["en.json", "sv.json"]

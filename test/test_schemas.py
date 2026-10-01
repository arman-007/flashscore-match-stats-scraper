"""The `.actor` schemas, and the nullable trap Apify enforces on every pushed row."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.input import INCLUDES, parse_input

ROOT = Path(__file__).resolve().parents[1]
ACTOR_DIR = ROOT / ".actor"


def load(name: str) -> dict:
    return json.loads((ACTOR_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def input_schema() -> dict:
    return load("input_schema.json")


def test_actor_json():
    actor = load("actor.json")
    assert 40 <= len(actor["title"]) <= 50
    assert len(actor["description"]) <= 300
    assert actor["defaultRunOptions"]["memoryMbytes"] == 512
    for key in ("input", "output"):
        assert (ACTOR_DIR / Path(actor[key]).name).exists()


def test_input_schema_enums_match_the_code(input_schema):
    items = input_schema["properties"]["include"]["items"]
    assert items["enum"] == list(INCLUDES)
    assert len(items["enum"]) == len(items["enumTitles"])


def test_schema_defaults_parse(input_schema):
    props = input_schema["properties"]
    defaults = {k: v["default"] for k, v in props.items() if "default" in v}
    prefills = {k: v["prefill"] for k, v in props.items() if "prefill" in v}
    parse_input({**defaults, **prefills})
    parse_input(prefills)


def test_canary_input_passes_the_platform_enums(input_schema):
    canary = json.loads((ROOT / "scripts" / "canary-input.json").read_text(encoding="utf-8"))
    parse_input(canary)
    for key, value in canary.items():
        prop = input_schema["properties"][key]
        allowed = prop.get("enum") or prop.get("items", {}).get("enum")
        if allowed:
            for item in value if isinstance(value, list) else [value]:
                assert item in allowed, f"{key}={item!r} is rejected by the input schema"


def test_dataset_fields_are_nullable():
    props = load("dataset_schema.json")["fields"]["properties"]
    for name, prop in props.items():
        assert "null" in prop["type"], name


def test_views_reference_declared_fields():
    schema = load("dataset_schema.json")
    props = schema["fields"]["properties"]
    assert set(schema["views"]) == {"matches", "players"}
    for view in schema["views"].values():
        for field in view["transformation"]["fields"]:
            assert field in props
        assert set(view["display"]["properties"]) == set(view["transformation"]["fields"])

"""Flashscore's text-feed formats -> Python structures. Pure functions.

Two formats share one set of separators (docs/architecture.md §2):

* **Flat records** -- `¬~` ends a record, `¬` ends a field, `÷` splits key and
  value. **Keys repeat within a record** (a set-score record holds `IG` twice),
  so a record is a list of pairs, never a dict.
* **Trees** (rankings) -- `TS÷tag` opens a node, `TE÷tag` closes it, `PT`/`PV`
  is a property name/value pair, a bare `K÷V` is an attribute. `¬~` can appear
  mid-tree and means nothing there.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

RECORD_SEP = "¬~"
FIELD_SEP = "¬"
KV_SEP = "÷"

Record = list[tuple[str, str]]


def is_empty(text: str | None) -> bool:
    """`0`, an empty body, or a lone signature record mean "nothing there"."""
    body = (text or "").strip()
    return body in ("", "0") or body.startswith("A1÷") and RECORD_SEP not in body.rstrip(RECORD_SEP)


def records(text: str) -> list[Record]:
    out: list[Record] = []
    for chunk in (text or "").split(RECORD_SEP):
        pairs = []
        for field in chunk.split(FIELD_SEP):
            key, sep, value = field.partition(KV_SEP)
            if sep:
                pairs.append((key, value))
        if pairs and pairs[0][0] != "A1":
            out.append(pairs)
    return out


def first(record: Record, key: str, default: str | None = None) -> str | None:
    return next((value for k, value in record if k == key), default)


def every(record: Record, key: str) -> list[str]:
    return [value for k, value in record if k == key]


def has(record: Record, key: str) -> bool:
    return any(k == key for k, _ in record)


def as_dict(record: Record) -> dict[str, str]:
    """First value per key. Only for records known not to repeat keys."""
    out: dict[str, str] = {}
    for key, value in record:
        out.setdefault(key, value)
    return out


def parse_tree(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {"tag": "ROOT", "props": {}, "children": []}
    stack = [root]
    pending: str | None = None
    for field in (text or "").replace(RECORD_SEP, FIELD_SEP).split(FIELD_SEP):
        key, sep, value = field.partition(KV_SEP)
        if not sep:
            continue
        if key == "TS":
            node = {"tag": value, "props": {}, "children": []}
            stack[-1]["children"].append(node)
            stack.append(node)
        elif key == "TE":
            while len(stack) > 1 and stack.pop()["tag"] != value:
                pass
        elif key == "PT":
            pending = value
        elif key == "PV" and pending is not None:
            stack[-1]["props"][pending] = value
            pending = None
        else:
            stack[-1]["props"][key] = value
    return root


def walk(node: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    """Every descendant node with this tag, in document order."""
    found = []
    for child in node["children"]:
        if child["tag"] == tag:
            found.append(child)
        found.extend(walk(child, tag))
    return found


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def iso(ts: Any) -> str | None:
    """Epoch seconds -> ISO 8601 UTC. Matches before 1970 (Arsenal's 1910s
    history) are negative; `0` means "no time"."""
    seconds = to_int(ts)
    if not seconds:
        return None
    return (_EPOCH + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

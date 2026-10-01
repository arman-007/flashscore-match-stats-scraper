from __future__ import annotations

import gzip
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

# Captured 2026-10-01 by probe/capture.py.
BHA = "j52jHsN8"  # Brighton 3-0 Arsenal, Premier League (football: every tab)
NHL = "dW4Uio9K"  # Philadelphia 0-7 Pittsburgh (hockey box score, lines)
NBA = "pnOhtTOH"  # San Antonio 90-94 New York, NBA final (basketball box score)
ATP = "MyyzpiYp"  # Zverev 3-1 Shelton, US Open final (tennis: no lineups)
PREMIER_LEAGUE = "/football/england/premier-league/"
KNICKS = "/team/new-york-knicks/WCNO4nbt/"


def read(name: str) -> str:
    return gzip.decompress((FIXTURES / f"{name}.gz").read_bytes()).decode("utf-8")


def read_json(name: str):
    return json.loads(read(name))


def page_name(path: str) -> str:
    return "page" + path.replace("/", "_").rstrip("_")


def all_pages() -> dict[str, str]:
    return {
        path: read(page_name(path))
        for path in [f"/match/{e}/" for e in (BHA, NHL, NBA, ATP)] + [PREMIER_LEAGUE, KNICKS]
    }


def all_feeds() -> dict[str, str]:
    return {p.name[:-3]: read(p.name[:-3]) for p in FIXTURES.glob("*.gz") if not p.name.startswith(("page_", "gql_"))}


def all_graphql() -> dict[tuple[str, str], object]:
    out = {}
    for p in FIXTURES.glob("gql_*.gz"):
        _, query, event = p.name[:-3].split("_", 2)
        out[(query, event)] = read_json(p.name[:-3])
    return out

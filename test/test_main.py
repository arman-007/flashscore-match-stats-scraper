"""Orchestration against a fake client serving the fixtures."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from src import billing as billing_module
from src import main as main_module
from src.discovery import league_source, team_source
from src.flashscore_client import FlashscoreError, FlashscoreNotFoundError
from src.input import INCLUDES, parse_input
from src.main import RunState, discover, run_all

from conftest import ATP, BHA, KNICKS, NBA, NHL, PREMIER_LEAGUE, all_feeds, all_graphql, all_pages

PAGES, FEEDS, GRAPHQL = all_pages(), all_feeds(), all_graphql()


class _Log:
    def info(self, *_a, **_k): ...
    def warning(self, *_a, **_k): ...
    def error(self, *_a, **_k): ...


class FakeActor:
    log = _Log()
    rows: list = []

    @classmethod
    async def push_data(cls, row, charged_event_name=None):
        cls.rows.append(row)


@pytest.fixture(autouse=True)
def fake_actor(monkeypatch):
    FakeActor.rows = []
    monkeypatch.setattr(main_module, "Actor", FakeActor)
    monkeypatch.setattr(billing_module, "Actor", FakeActor)
    return FakeActor


class FakeBilling:
    def __init__(self):
        self.budget_exhausted = False
        self.charged = Counter()
        self.pushed: list[tuple[str, list]] = []

    async def push(self, rows, event):
        self.pushed.append((event, rows))
        self.charged[event] += len(rows)
        return len(rows)

    def rows(self, event=None):
        return [r for e, rows in self.pushed if event in (None, e) for r in rows]


class FakeClient:
    def __init__(self, *, pages=None, feeds=None, graphql=None):
        self.pages = PAGES if pages is None else pages
        self.feeds = FEEDS if feeds is None else feeds
        self.graphql_data = GRAPHQL if graphql is None else graphql
        self.calls: list[str] = []

    async def feed(self, name):
        self.calls.append(name)
        value = self.feeds.get(name, "")
        if isinstance(value, Exception):
            raise value
        return value

    async def page(self, path):
        self.calls.append(path)
        value = self.pages.get(path)
        if value is None:
            raise FlashscoreNotFoundError(path)
        if isinstance(value, Exception):
            raise value
        return value

    async def graphql(self, query, **params):
        self.calls.append(f"{query}:{params['eventId']}")
        value = self.graphql_data.get((query, params["eventId"]))
        if isinstance(value, Exception):
            raise value
        return value


SCHEMA = json.loads((Path(__file__).resolve().parents[1] / ".actor" / "dataset_schema.json").read_text())
JSON_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "array": list, "object": dict}


def assert_schema_ok(row):
    """Declared fields have the declared type; undeclared ones are player stats."""
    props = SCHEMA["fields"]["properties"]
    for key, value in row.items():
        if key not in props:
            assert row["recordType"] == "player" and isinstance(value, (int, float)) and not isinstance(value, bool), key
            continue
        if value is None:
            continue
        kinds = tuple(JSON_TYPES[t] for t in props[key]["type"] if t != "null")
        assert isinstance(value, kinds) and not (bool in kinds) ^ isinstance(value, bool), (key, value)


def state_for(raw):
    return RunState(billing=FakeBilling(), actor_input=parse_input(raw))


async def test_football_match_with_everything():
    client = FakeClient()
    state = state_for({"matchUrls": [BHA], "include": list(INCLUDES)})
    await run_all(client, state)
    b = state.billing
    assert [e for e, _ in b.pushed] == ["match", "player-match"]

    m = b.rows("match")[0]
    assert list(m)[:2] == ["recordType", "eventId"]
    assert (m["homeTeam"], m["homeScore"], m["awayScore"], m["awayTeam"], m["halfTimeScore"]) == ("Brighton", 3, 0, "Arsenal", "2-0")
    assert (m["venue"], m["attendance"], m["referee"]) == ("Amex Stadium", 31944, "England D.")
    assert (m["homeFormation"], m["awayCoach"], m["homeAverageRating"]) == ("4-2-3-1", "Arteta M.", 7.3)
    assert len(m["incidents"]) == 18 and len(m["statistics"]) == 122 and len(m["missingPlayers"]) == 11
    assert len(m["momentum"]) == 99 and len(m["commentary"]) == 98 and len(m["headToHead"]["meetings"]) == 31

    players = b.rows("player-match")
    assert len(players) == 32 and all(p["played"] for p in players)
    assert [p["side"] for p in players] == ["home"] * 16 + ["away"] * 16
    assert all(p["starter"] for p in players[:11]) and not players[11]["starter"]
    gross = next(p for p in players if p["playerId"] == "trpxfbO3")
    assert (gross["player"], gross["team"], gross["opponent"], gross["position"]) == ("Gross P.", "Brighton", "Arsenal", "Midfielder")
    assert (gross["rating"], gross["isBestRating"], gross["goals"], gross["minutesPlayed"]) == (8.3, True, 1, 90)
    dowman = next(p for p in players if p["player"] == "Dowman M.")
    assert (dowman["starter"], dowman["subbedInMinute"], dowman["minutesPlayed"]) == (False, 81, 9)
    for row in b.rows():
        assert_schema_ok(row)
    assert state.matches_done == 1 and not state.failed


async def test_defaults_skip_the_optional_sources():
    client = FakeClient()
    state = state_for({"matchUrls": [BHA]})
    await run_all(client, state)
    m = state.billing.rows("match")[0]
    assert m["statistics"] and m["missingPlayers"] and m["homeFormation"]
    assert (m["momentum"], m["commentary"], m["headToHead"]) == (None, None, None)
    assert not any(c.startswith(("mmts", "df_lc", "df_hh")) for c in client.calls)


async def test_unused_substitutes_on_request():
    state = state_for({"matchUrls": [BHA], "includeUnusedSubstitutes": True})
    await run_all(FakeClient(), state)
    players = state.billing.rows("player-match")
    assert len(players) == 40 and sum(p["played"] is False for p in players) == 8


async def test_lineups_without_player_stats():
    client = FakeClient()
    state = state_for({"matchUrls": [BHA], "include": ["lineups"]})
    await run_all(client, state)
    players = state.billing.rows("player-match")
    assert len(players) == 32 and "goals" not in players[0] and players[0]["rating"] == 8.0
    assert not any(c.startswith(("epms", "df_st")) for c in client.calls)


async def test_match_only():
    client = FakeClient()
    state = state_for({"matchUrls": [BHA], "include": ["statistics"]})
    await run_all(client, state)
    assert [e for e, _ in state.billing.pushed] == ["match"]
    assert client.calls == [f"/match/{BHA}/", f"df_sui_1_{BHA}", f"df_st_1_{BHA}"]


async def test_other_sports():
    client = FakeClient()
    state = state_for({"matchUrls": [NHL, NBA, ATP]})
    await run_all(client, state)
    players = Counter(p["eventId"] for p in state.billing.rows("player-match"))
    assert players == {NHL: 38, NBA: 21}

    nhl = [p for p in state.billing.rows("player-match") if p["eventId"] == NHL]
    goalie = next(p for p in nhl if p["player"] == "Vladar D.")
    assert (goalie["isGoalkeeper"], goalie["saves"], goalie["lineupGroup"], goalie["team"]) == (True, 31, "Line 1", "Philadelphia Flyers")
    nba = next(p for p in state.billing.rows("player-match") if p["eventId"] == NBA)
    assert (nba["player"], nba["points"], nba["shirtNumber"], nba["rating"]) == ("Vassell D.", 12, 24, 7.0)

    atp = next(m for m in state.billing.rows("match") if m["eventId"] == ATP)
    assert (atp["duration"], len(atp["periodScores"]), atp["homeCoach"]) == ("3:36", 4, None)
    assert not any(c.endswith(ATP) and c.startswith(("dlie2", "df_psn", "epms")) for c in client.calls)
    assert not any(c.startswith("epms") for c in client.calls)  # football only
    for row in state.billing.rows():
        assert_schema_ok(row)


async def test_league_discovery_takes_the_newest_finished():
    client = FakeClient()
    state = state_for({"leagueUrls": ["https://www.flashscore.com" + PREMIER_LEAGUE], "maxMatchesPerSource": 6})
    ids = await discover(client, state, league_source("https://www.flashscore.com" + PREMIER_LEAGUE))
    assert len(ids) == 6 and ids[5] == BHA
    assert client.calls == [PREMIER_LEAGUE]


async def test_team_discovery_pages_the_continuation_feed():
    client = FakeClient()
    source = team_source("https://www.flashscore.com" + KNICKS)
    state = state_for({"teamUrls": [source.url], "maxMatchesPerSource": 45})
    ids = await discover(client, state, source)
    assert len(ids) == 45 and len(set(ids)) == 45 and NBA in ids
    assert client.calls == [KNICKS, "pr_3_200_WCNO4nbt_1_0_en_1"]


async def test_date_range_stops_paging_once_past_it():
    client = FakeClient()
    source = team_source("https://www.flashscore.com" + KNICKS)
    state = state_for({"teamUrls": [source.url], "maxMatchesPerSource": 0, "dateFrom": "2026-03-01", "dateTo": "2026-03-10"})
    ids = await discover(client, state, source)
    assert len(ids) == 6
    assert client.calls == [KNICKS, "pr_3_200_WCNO4nbt_1_0_en_1"]


async def test_discovered_matches_that_are_missing_are_unbilled():
    client = FakeClient()
    state = state_for({"leagueUrls": ["https://www.flashscore.com" + PREMIER_LEAGUE], "maxMatchesPerSource": 6, "include": []})
    await run_all(client, state)
    assert [m["eventId"] for m in state.billing.rows("match")] == [BHA]
    assert state.not_found == 5 and all(r["error"] == "MATCH_NOT_FOUND" for r in FakeActor.rows)


async def test_unknown_source_and_match_are_unbilled_rows():
    state = state_for({"matchUrls": ["AAAAAAAA"], "teamUrls": ["https://www.flashscore.com/team/narnia/BBBBBBBB/"]})
    await run_all(FakeClient(), state)
    assert [r["error"] for r in FakeActor.rows] == ["SOURCE_NOT_FOUND", "MATCH_NOT_FOUND"]
    assert state.billing.pushed == [] and state.not_found == 2


async def test_failures_are_recorded_not_raised():
    feeds = {**FEEDS, f"df_st_1_{BHA}": FlashscoreError("df_st", 500, "boom")}
    graphql = {**GRAPHQL, ("dlie2", BHA): FlashscoreError("dlie2", 500, "boom")}
    pages = {**PAGES, f"/match/{NBA}/": FlashscoreError("page", 500, "boom")}
    state = state_for({"matchUrls": [BHA, NBA]})
    await run_all(FakeClient(pages=pages, feeds=feeds, graphql=graphql), state)
    assert len(state.failed) == 3
    m = state.billing.rows("match")[0]
    assert m["statistics"] is None and m["homeFormation"] is None and m["incidents"]
    # Without the lineup the rows come from the player-stats feed alone.
    players = state.billing.rows("player-match")
    assert len(players) == 32 and players[0]["shirtNumber"] is None and players[0]["team"] == "Brighton"


async def test_max_items_caps_rows():
    state = state_for({"matchUrls": [BHA, NHL], "maxItems": 10})
    await run_all(FakeClient(), state)
    assert [len(rows) for _, rows in state.billing.pushed] == [1, 9] and state.done

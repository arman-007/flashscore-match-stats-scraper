"""Parsers against the captured fixtures."""

from __future__ import annotations

import pytest

from src.discovery import (
    continuation_feed,
    event_id_from,
    league_source,
    parse_match_list,
    parse_source_page,
    team_source,
)
from src.match_feeds import (
    box_value,
    parse_box_score,
    parse_commentary,
    parse_head_to_head,
    parse_missing_players,
    parse_statistics,
    parse_summary,
    stat_value,
)
from src.match_graphql import parse_lineups, parse_momentum, parse_player_stats
from src.match_page import MatchPageError, parse_match_page, split_round

from conftest import ATP, BHA, KNICKS, NBA, NHL, PREMIER_LEAGUE, page_name, read, read_json


# ------------------------------------------------------------------ URLs


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("j52jHsN8", "j52jHsN8"),
        ("https://www.flashscore.com/match/j52jHsN8/", "j52jHsN8"),
        ("https://www.flashscore.com/match/j52jHsN8/#/match-summary/player-statistics", "j52jHsN8"),
        ("https://www.flashscore.com/match/football/brighton-2XrRecc3/arsenal-hA1Zm19f/?mid=j52jHsN8", "j52jHsN8"),
        ("https://www.flashscore.co.uk/match/j52jHsN8/", "j52jHsN8"),
        ("football", None),
        ("https://www.flashscore.com/team/arsenal/hA1Zm19f/", None),
        ("j52jHsN", None),
    ],
)
def test_event_id_from(value, expected):
    assert event_id_from(value) == expected


def test_league_and_team_sources():
    assert league_source("https://www.flashscore.com/football/england/premier-league/results/").path == PREMIER_LEAGUE
    assert league_source("flashscore.com/soccer/england/premier-league-2024-2025").path == "/football/england/premier-league-2024-2025/"
    assert league_source("https://www.flashscore.com/football/england/") is None
    assert league_source("https://www.flashscore.com/team/arsenal/hA1Zm19f/") is None
    team = team_source("https://www.flashscore.co.uk/team/New-York-Knicks/WCNO4nbt/results/")
    assert (team.path, team.team_id) == (KNICKS, "WCNO4nbt")


# ------------------------------------------------------------------ match page


def test_match_page_football():
    p = parse_match_page(read(page_name(f"/match/{BHA}/")), BHA)
    assert (p["homeTeam"], p["homeScore"], p["awayScore"], p["awayTeam"]) == ("Brighton", 3, 0, "Arsenal")
    assert (p["sport"], p["competition"], p["round"], p["country"]) == ("football", "Premier League", "Round 5", "England")
    assert (p["status"], p["decidedBy"], p["startTime"]) == ("finished", "regular-time", "2026-09-19T14:00:00Z")
    assert p["homeTeamUrl"] == "https://www.flashscore.com/team/brighton/2XrRecc3/"
    assert {"ST", "PS", "LI", "LC", "MC", "HH", "SCR"} <= set(p["tabs"])


def test_match_page_other_sports():
    nhl = parse_match_page(read(page_name(f"/match/{NHL}/")), NHL)
    assert (nhl["sport"], nhl["competition"], nhl["round"]) == ("hockey", "NHL", None)
    nba = parse_match_page(read(page_name(f"/match/{NBA}/")), NBA)
    assert (nba["competition"], nba["round"], nba["homeScore"], nba["awayScore"]) == ("NBA - Play Offs", "Final", 90, 94)
    atp = parse_match_page(read(page_name(f"/match/{ATP}/")), ATP)
    assert atp["homeTeamUrl"] == "https://www.flashscore.com/player/zverev-alexander/dGbUhw9m/"
    assert "LI" not in atp["tabs"] and "PS" not in atp["tabs"]


def test_match_page_without_environment():
    with pytest.raises(MatchPageError):
        parse_match_page("<html></html>", BHA)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Premier League - Round 5", ("Premier League", "Round 5")),
        ("NBA - Play Offs - Final", ("NBA - Play Offs", "Final")),
        ("ATP - SINGLES: US Open, hard - Final", ("ATP - SINGLES: US Open, hard", "Final")),
        ("NBA - Play Offs", ("NBA", "Play Offs")),
        ("Champions League - League phase - Round 2", ("Champions League - League phase", "Round 2")),
        ("NHL", ("NHL", None)),
        (None, (None, None)),
    ],
)
def test_split_round(text, expected):
    assert split_round(text) == expected


# ------------------------------------------------------------------ summary


def test_summary_football():
    s = parse_summary(read(f"df_sui_1_{BHA}"))
    assert [(p["period"], p["home"], p["away"]) for p in s["periodScores"]] == [("1st Half", 2, 0), ("2nd Half", 1, 0)]
    assert s["info"] == {
        "venue": "Amex Stadium", "city": "Brighton", "attendance": 31944, "capacity": 31876,
        "referee": "England D.", "refereeCountry": "Eng", "referees": [{"name": "England D.", "country": "Eng"}],
    }
    goals = [i for i in s["incidents"] if i["type"] == "Goal"]
    assert [(g["minute"], g["player"], g["relatedPlayer"], g["homeScoreAfter"]) for g in goals] == [
        ("31'", "Gross P.", "Kostoulas C.", 1), ("45'", "Kostoulas C.", "Gomez D.", 2), ("57'", "Andres C.", "Gross P.", 3),
    ]
    card = next(i for i in s["incidents"] if i["minute"] == "45+1'")
    assert (card["type"], card["minuteValue"], card["addedTime"], card["side"]) == ("Yellow Card", 45, 1, "home")
    sub = next(i for i in s["incidents"] if i["type"] == "Substitution")
    assert (sub["player"], sub["relatedPlayer"], sub["relatedRole"]) == ("Zubimendi M.", "Timber J.", "Substitution - Out")
    assert goals[0]["commentary"].startswith("Pascal Gross")


def test_summary_tennis_and_hockey():
    atp = parse_summary(read(f"df_sui_1_{ATP}"))
    assert [(p["home"], p["away"], p["homeTiebreak"], p["awayTiebreak"]) for p in atp["periodScores"]] == [
        (6, 3, None, None), (7, 6, 7, 2), (5, 7, None, None), (6, 2, None, None),
    ]
    assert (atp["info"]["duration"], atp["info"]["venue"]) == ("3:36", "Arthur Ashe Stadium")
    nhl = parse_summary(read(f"df_sui_1_{NHL}"))
    first = nhl["incidents"][0]
    assert (first["minute"], first["player"], first["relatedPlayer"]) == ("07:26", "Robertson N.", "Letang K.")
    assert first["otherPlayers"] == [{"role": "Assistance 2", "player": "Crosby S.", "playerId": "UTbIZpKC"}]
    assert nhl["incidents"][1]["reason"] == "Holding"


def test_summary_empty():
    assert parse_summary("") == {"periodScores": [], "incidents": [], "info": {}}


# ------------------------------------------------------------------ statistics


def test_statistics():
    stats = parse_statistics(read(f"df_st_1_{BHA}"))
    assert stats[0] == {
        "period": "Match", "section": "Top stats", "stat": "Expected goals (xG)", "statId": 432,
        "home": 1.31, "away": 1.63, "homeDisplay": "1.31", "awayDisplay": "1.63",
        "homeMade": None, "homeAttempted": None, "awayMade": None, "awayAttempted": None,
    }
    passes = next(s for s in stats if s["stat"] == "Passes")
    assert (passes["home"], passes["homeMade"], passes["homeAttempted"]) == (76, 260, 343)
    assert {s["period"] for s in stats} == {"Match", "1st Half", "2nd Half"}
    assert len(parse_statistics(read(f"df_st_1_{ATP}"))) == 103


@pytest.mark.parametrize(
    ("display", "expected"),
    [("76% (260/343)", (76, 260, 343)), ("2/3", (None, 2, 3)), ("213 km/h", (213, None, None)), ("1.31", (1.31, None, None)), ("", (None, None, None))],
)
def test_stat_value(display, expected):
    assert stat_value(display) == expected


# ------------------------------------------------------------------ box scores


def test_box_score_basketball():
    players = parse_box_score(read(f"df_psn_1_{NBA}"))
    assert len(players) == 21
    vassell = players[0]
    assert (vassell["player"], vassell["teamName"], vassell["playerId"]) == ("Vassell D.", "San Antonio Spurs", "hIJfdJJJ")
    assert vassell["stats"]["points"] == 12 and vassell["stats"]["minutesPlayed"] == 39.2
    assert (vassell["stats"]["threePointersMade"], vassell["stats"]["threePointersAttempted"]) == (2, 5)


def test_box_score_hockey():
    players = parse_box_score(read(f"df_psn_1_{NHL}"))
    goalie = next(p for p in players if p["boxScoreTable"] == "goalkeeper")
    assert goalie["player"] == "Vladar D."
    assert goalie["stats"] == {"points": 0, "penaltyMinutes": 0, "timeOnIce": 59.68, "saves": 31, "shotsAgainst": 38, "savePercentage": 81.6}
    assert {p["teamName"] for p in players} == {"Philadelphia Flyers", "Pittsburgh Penguins"}


@pytest.mark.parametrize(("raw", "kind", "expected"), [("-", "num", 0), ("39:12", "time", 39.2), ("12", "num", 12), ("", "num", None)])
def test_box_value(raw, kind, expected):
    assert box_value(raw, kind) == expected


# ------------------------------------------------------------------ other feeds


def test_missing_players():
    missing = parse_missing_players(read(f"df_scr_1_{BHA}"))
    assert missing[0] == {
        "side": "home", "player": "Azeez F.", "playerId": "d6gBWKm0",
        "playerUrl": "https://www.flashscore.com/player/azeez-femi/d6gBWKm0/", "nationality": "Nigeria",
        "reason": "Abdominal strain", "availability": "There is some chance of playing.",
    }
    assert {m["side"] for m in missing} == {"home", "away"}


def test_commentary_is_oldest_first():
    c = parse_commentary(read(f"df_lc_1_{BHA}"))
    assert len(c) == 98
    assert c[0]["minute"] is None and c[0]["text"].startswith("Welcome")
    assert (c[-1]["minute"], c[-1]["type"], c[-1]["important"]) == ("90+7'", "whistle", True)


def test_head_to_head():
    h = parse_head_to_head(read(f"df_hh_1_{BHA}"), "Brighton")
    assert {k: len(v) for k, v in h.items()} == {"homeLastMatches": 50, "awayLastMatches": 50, "meetings": 31}
    assert h["meetings"][0]["winner"] == "home" and "result" not in h["meetings"][0]
    assert h["homeLastMatches"][0]["result"] == "W" and h["awayLastMatches"][0]["result"] == "L"
    tennis = parse_head_to_head(read(f"df_hh_1_{ATP}"), "Zverev A.")
    assert len(tennis["meetings"]) == 6 and tennis["homeLastMatches"]


# ------------------------------------------------------------------ GraphQL


def test_lineups_football():
    l = parse_lineups(read_json(f"gql_dlie2_{BHA}"))
    home, away = l["home"], l["away"]
    assert (home["formation"], home["coach"], home["averageRating"]) == ("4-2-3-1", "Hurzeler F.", 7.3)
    assert (away["formation"], away["coach"]) == ("4-2-3-1", "Arteta M.")
    assert sum(p["starter"] for p in home["players"]) == 11
    keeper = home["players"][0]
    assert (keeper["player"], keeper["shirtNumber"], keeper["isGoalkeeper"], keeper["rating"]) == ("Verbruggen B.", 1, True, 8.0)
    saka = next(p for p in away["players"] if p["player"] == "Saka B.")
    assert saka["subbedOutMinute"] == 81
    dowman = next(p for p in away["players"] if p["player"] == "Dowman M.")
    assert (dowman["starter"], dowman["subbedInMinute"]) == (False, 81)


def test_lineups_hockey_lines():
    l = parse_lineups(read_json(f"gql_dlie2_{NHL}"))
    assert l["home"]["formation"] == "4 lines" and l["home"]["coach"] == "Tocchet R."
    assert {p["lineupGroup"] for p in l["home"]["players"]} >= {"Line 1", "Line 4"}


def test_player_stats():
    players = parse_player_stats(read_json(f"gql_epmsd_{BHA}"), read_json(f"gql_epmsse_{BHA}"))
    assert len(players) == 40
    gross = next(p for p in players if p["playerId"] == "trpxfbO3")
    assert (gross["position"], gross["rating"], gross["isBestRating"], gross["teamId"]) == ("Midfielder", 8.3, True, "2XrRecc3")
    assert gross["stats"]["goals"] == 1 and gross["stats"]["minutesPlayed"] == 90
    for key in ("goalsPrevented", "expectedGoalsOnTargetFaced", "shotsFaced", "fsRating"):
        assert key not in gross["stats"]
    assert gross["stats"]["goalsConceded"] == 0
    keeper = next(p for p in players if p["isGoalkeeper"] and p["starter"] and p["teamId"] == "2XrRecc3")
    assert keeper["stats"]["goalsPrevented"] == 1.0844 and keeper["stats"]["expectedGoalsOnTargetFaced"] == 1.0844
    assert all(0 <= p["stats"].get("duelsEfficiency", 0) <= 100 for p in players)


def test_player_stats_empty():
    assert parse_player_stats(None, None) == []


def test_momentum():
    m = parse_momentum(read_json(f"gql_mmts_{BHA}"))
    assert len(m) == 99 and m[0] == {"minute": "1'", "period": "1st Half", "value": 0.0424}
    assert parse_momentum(read_json(f"gql_mmts_{ATP}")) == []


# ------------------------------------------------------------------ discovery


def test_league_page():
    source = league_source("https://www.flashscore.com" + PREMIER_LEAGUE)
    page = parse_source_page(read(page_name(PREMIER_LEAGUE)), source)
    assert (len(page["matches"]), page["total"], page["seasonId"], page["templateId"], page["countryId"]) == (50, 50, 190, "dYlOSQOD", "198")
    assert continuation_feed(source, page, 1) == "tr_1_198_dYlOSQOD_190_1_0_en_1"


def test_team_page_and_continuation():
    source = team_source("https://www.flashscore.com" + KNICKS)
    page = parse_source_page(read(page_name(KNICKS)), source)
    assert (page["total"], page["sportId"], page["countryId"], page["teamId"]) == (2989, 3, "200", "WCNO4nbt")
    assert continuation_feed(source, page, 1) == "pr_3_200_WCNO4nbt_1_0_en_1"
    more = parse_match_list(read("pr_3_200_WCNO4nbt_1_0_en_1"))
    assert len(more) == 40 and more[0]["competition"] == "USA: NBA" and more[0]["finished"]

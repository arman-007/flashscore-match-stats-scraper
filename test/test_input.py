from __future__ import annotations

from datetime import date

import pytest

from src.input import DEFAULT_INCLUDES, DEFAULT_MAX_PER_SOURCE, parse_input


def test_defaults():
    i = parse_input({"matchUrls": ["https://www.flashscore.com/match/j52jHsN8/"]})
    assert i.event_ids == ["j52jHsN8"] and i.sources == []
    assert i.include == list(DEFAULT_INCLUDES) and i.wants_players
    assert (i.max_per_source, i.max_items, i.date_from, i.date_to) == (DEFAULT_MAX_PER_SOURCE, 10000, None, None)
    assert not i.include_unused_substitutes


def test_urls_are_routed_by_kind_and_deduplicated():
    i = parse_input({
        "matchUrls": [
            "j52jHsN8",
            {"url": "https://www.flashscore.com/match/football/brighton-2XrRecc3/arsenal-hA1Zm19f/?mid=j52jHsN8"},
            "https://www.flashscore.com/team/arsenal/hA1Zm19f/",
        ],
        "leagueUrls": ["https://www.flashscore.com/match/pnOhtTOH/", "https://www.flashscore.com/football/england/premier-league/results/"],
        "teamUrls": ["https://www.flashscore.co.uk/team/arsenal/hA1Zm19f/", ""],
    })
    assert i.event_ids == ["j52jHsN8", "pnOhtTOH"]
    assert [(s.kind, s.path) for s in i.sources] == [
        ("team", "/team/arsenal/hA1Zm19f/"), ("league", "/football/england/premier-league/"),
    ]


def test_include_and_limits():
    i = parse_input({"leagueUrls": ["https://www.flashscore.com/football/england/premier-league/"],
                     "include": ["Statistics", "statistics", "headtohead"], "maxMatchesPerSource": 0})
    assert i.include == ["statistics", "headToHead"] and not i.wants_players
    assert i.max_per_source is None
    assert parse_input({"matchUrls": ["j52jHsN8"], "include": []}).include == []


def test_date_range():
    i = parse_input({"teamUrls": ["https://www.flashscore.com/team/arsenal/hA1Zm19f/"],
                     "dateFrom": "2026-08-01", "dateTo": "2026-09-30T00:00:00.000Z"})
    assert (i.date_from, i.date_to) == (date(2026, 8, 1), date(2026, 9, 30))
    assert i.in_range(1789822800)  # 2026-09-19
    assert not i.in_range(1753999200)  # 2025-07-31
    assert not i.in_range(None)


@pytest.mark.parametrize("raw, message", [
    ({}, "at least one match, league or team"),
    ({"matchUrls": [""]}, "at least one match, league or team"),
    ({"leagueUrls": ["https://www.flashscore.com/football/england/"]}, "not a Flashscore match, league or team URL"),
    ({"matchUrls": ["j52jHsN8"], "include": ["odds"]}, "not valid in `include`"),
    ({"matchUrls": ["j52jHsN8"], "maxMatchesPerSource": -1}, r"0 \(no limit\) or more"),
    ({"matchUrls": ["j52jHsN8"], "maxItems": 0}, "at least 1"),
    ({"matchUrls": ["j52jHsN8"], "maxItems": True}, "whole number"),
    ({"matchUrls": ["j52jHsN8"], "dateFrom": "19/09/2026"}, "date like"),
    ({"matchUrls": ["j52jHsN8"], "dateFrom": "2026-09-20", "dateTo": "2026-09-19"}, "is after"),
])
def test_invalid_input(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_input(raw)

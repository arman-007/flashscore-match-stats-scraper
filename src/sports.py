"""Flashscore's numeric sport ids, keyed by the first segment of a league URL.

The ids are Flashscore's own: they are the first segment of every result-page
feed name (`tr_{sportId}_...`), and each one was verified on 2026-09-27 by
reading the league URL paths its feeds return (`ZL÷/football/...`).

Only **duel** sports are listed. Golf, racing, cycling and horse racing have
feeds too, but their events are fields of runners rather than a home and an
away side, which this Actor's match rows cannot represent.
"""

from __future__ import annotations

SPORTS: dict[str, int] = {
    "football": 1,
    "tennis": 2,
    "basketball": 3,
    "hockey": 4,
    "american-football": 5,
    "baseball": 6,
    "handball": 7,
    "rugby-union": 8,
    "floorball": 9,
    "futsal": 11,
    "volleyball": 12,
    "cricket": 13,
    "boxing": 16,
    "aussie-rules": 18,
    "rugby-league": 19,
    "badminton": 21,
    "water-polo": 22,
    "field-hockey": 24,
    "table-tennis": 25,
    "mma": 28,
    "esports": 36,
}

SPORT_BY_ID: dict[int, str] = {sport_id: slug for slug, sport_id in SPORTS.items()}

# What people actually type. Flashscore's slug for ice hockey is `hockey` and
# for association football is `football`; rejecting "soccer" would be pedantry.
ALIASES: dict[str, str] = {
    "soccer": "football",
    "ice-hockey": "hockey",
    "nfl": "american-football",
    "rugby": "rugby-union",
    "ufc": "mma",
    "e-sports": "esports",
}

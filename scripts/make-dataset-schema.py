"""Writes .actor/dataset_schema.json. Run: python scripts/make-dataset-schema.py

Player stat columns vary by sport (about 100 for football, a box score for
basketball and hockey), so only the common ones are declared; the rest pass
through as extra row keys.
"""

from __future__ import annotations

import json
from pathlib import Path

S, N, I, B, A, O = "string", "number", "integer", "boolean", "array", "object"

FIELDS: list[tuple[str, str, str, object]] = [
    ("recordType", S, "`match`, `player`, or `error` for a diagnostic row (never charged).", "match"),
    ("eventId", S, "Flashscore's 8-character match id.", "j52jHsN8"),
    ("url", S, "Match page (match rows) or the URL an error row refers to.", "https://www.flashscore.com/match/j52jHsN8/"),
    ("matchUrl", S, "Player rows: the match page.", "https://www.flashscore.com/match/j52jHsN8/"),
    ("sport", S, "Sport slug.", "football"),
    ("country", S, "Country or region of the competition.", "England"),
    ("competition", S, "Competition name.", "Premier League"),
    ("competitionUrl", S, "Competition page.", "https://www.flashscore.com/football/england/premier-league/"),
    ("round", S, "Round or stage.", "Round 5"),
    ("startTime", S, "Kick-off, ISO 8601 UTC.", "2026-09-19T14:00:00Z"),
    ("status", S, "`finished`, `live`, `scheduled`, `postponed`, `cancelled`, `abandoned`, ...", "finished"),
    ("decidedBy", S, "`regular-time`, `extra-time`, `penalties` or `overtime`.", "regular-time"),
    ("homeTeam", S, "Home team (or first player in tennis).", "Brighton"),
    ("homeTeamId", S, "Home team id.", "2XrRecc3"),
    ("homeTeamUrl", S, "Home team page.", "https://www.flashscore.com/team/brighton/2XrRecc3/"),
    ("awayTeam", S, "Away team.", "Arsenal"),
    ("awayTeamId", S, "Away team id.", "hA1Zm19f"),
    ("awayTeamUrl", S, "Away team page.", "https://www.flashscore.com/team/arsenal/hA1Zm19f/"),
    ("homeScore", I, "Home final score (sets won in tennis).", 3),
    ("awayScore", I, "Away final score.", 0),
    ("halfTimeScore", S, "Football: score at half time.", "2-0"),
    ("periodScores", A, "Score per half, quarter, period or set (with tiebreak points in tennis).", [{"period": "1st Half", "home": 2, "away": 0}]),
    ("duration", S, "Tennis: total match duration (h:mm).", "3:36"),
    ("venue", S, "Stadium or arena.", "Amex Stadium"),
    ("city", S, "Venue city.", "Brighton"),
    ("attendance", I, "Spectators.", 31944),
    ("capacity", I, "Venue capacity.", 31876),
    ("referee", S, "Main referee.", "England D."),
    ("refereeCountry", S, "Main referee's country code.", "Eng"),
    ("referees", A, "Every listed official with country.", [{"name": "England D.", "country": "Eng"}]),
    ("homeFormation", S, "Home formation (football), or `4 lines` in hockey.", "4-2-3-1"),
    ("awayFormation", S, "Away formation.", "4-2-3-1"),
    ("homeCoach", S, "Home coach.", "Hurzeler F."),
    ("awayCoach", S, "Away coach.", "Arteta M."),
    ("homeAverageRating", N, "Average Flashscore player rating of the home side.", 7.3),
    ("awayAverageRating", N, "Average Flashscore player rating of the away side.", 6.3),
    ("incidents", A, "Goals, cards, substitutions and penalties with minute, player, assist and running score.", [{"minute": "31'", "type": "Goal", "player": "Gross P."}]),
    ("statistics", A, "Team statistics per period: xG, possession, shots, passes ... with display and made/attempted values.", [{"period": "Match", "stat": "Expected goals (xG)", "home": 1.31, "away": 1.63}]),
    ("missingPlayers", A, "Injured or suspended players with reason and availability.", [{"side": "home", "player": "Azeez F.", "reason": "Abdominal strain"}]),
    ("momentum", A, "Football: per-minute momentum, positive = home pressure, negative = away.", [{"minute": "1'", "value": 0.0424}]),
    ("commentary", A, "Text commentary, oldest first.", [{"minute": "31'", "text": "Goal! ..."}]),
    ("headToHead", O, "Both sides' last matches and previous meetings, as Flashscore shows them today.", {"meetings": []}),
    ("side", S, "Player rows: `home` or `away`.", "home"),
    ("team", S, "Player rows: the player's team.", "Brighton"),
    ("teamId", S, "Player rows: team id.", "2XrRecc3"),
    ("opponent", S, "Player rows: the opponent.", "Arsenal"),
    ("opponentId", S, "Player rows: opponent id.", "hA1Zm19f"),
    ("player", S, "Player name.", "Gross P."),
    ("playerId", S, "Flashscore's 8-character player id.", "trpxfbO3"),
    ("playerUrl", S, "Player page.", "https://www.flashscore.com/player/gross-pascal/trpxfbO3/"),
    ("shirtNumber", I, "Shirt number.", 13),
    ("nationality", S, "Player nationality.", "Germany"),
    ("position", S, "Football: position from the player-stats feed.", "Midfielder"),
    ("isGoalkeeper", B, "Goalkeeper (or hockey goalie).", False),
    ("isCaptain", B, "Captain.", False),
    ("starter", B, "In the starting lineup.", True),
    ("played", B, "Took part in the match (starters and used substitutes).", True),
    ("lineupGroup", S, "Lineup group: `Starting Lineups`, `Substitutes`, or the hockey line.", "Starting Lineups"),
    ("subbedInMinute", I, "Minute the player came on.", 62),
    ("subbedOutMinute", I, "Minute the player went off.", 78),
    ("rating", N, "Flashscore player rating.", 8.4),
    ("isBestRating", B, "Football: the match's best-rated player.", True),
    ("minutesPlayed", N, "Minutes played (basketball: decimal minutes, 39.2 = 39:12).", 90),
    ("goals", I, "Goals.", 1),
    ("assists", I, "Assists.", 0),
    ("expectedGoals", N, "Football: xG.", 0.38),
    ("expectedAssists", N, "Football: xA.", 0.05),
    ("points", I, "Basketball/hockey: points.", 12),
    ("rebounds", I, "Basketball: rebounds.", 7),
    ("timeOnIce", N, "Hockey: decimal minutes on ice.", 19.5),
    ("saves", I, "Saves (football keepers, hockey goalies).", 31),
    ("error", S, "Error rows: `INVALID_INPUT`, `MATCH_NOT_FOUND`, `SOURCE_NOT_FOUND`, `NO_MATCHES`.", "MATCH_NOT_FOUND"),
    ("errorMessage", S, "Error rows: what went wrong and how to fix it.", "Flashscore has no match abcdefgh (not charged)."),
]

FORMATS = {S: "text", N: "number", I: "number", B: "boolean", A: "array", O: "object"}

VIEWS = {
    "matches": ("Matches", "One row per match: score, venue, officials and formations.", [
        ("startTime", "Start", "date"), ("competition", "Competition", None), ("round", "Round", None),
        ("homeTeam", "Home", None), ("homeScore", "H", None), ("awayScore", "A", None),
        ("awayTeam", "Away", None), ("halfTimeScore", "HT", None), ("status", "Status", None),
        ("venue", "Venue", None), ("attendance", "Attendance", None), ("referee", "Referee", None),
        ("homeFormation", "Home formation", None), ("awayFormation", "Away formation", None),
        ("url", "URL", "link"),
    ]),
    "players": ("Players", "One row per player per match: lineup entry with the key stats.", [
        ("startTime", "Start", "date"), ("team", "Team", None), ("opponent", "Opponent", None),
        ("shirtNumber", "#", None), ("player", "Player", None), ("position", "Position", None),
        ("starter", "Starter", None), ("minutesPlayed", "Min", None), ("rating", "Rating", None),
        ("goals", "Goals", None), ("assists", "Assists", None), ("expectedGoals", "xG", None),
        ("points", "Pts", None), ("subbedInMinute", "On", None), ("subbedOutMinute", "Off", None),
        ("playerUrl", "URL", "link"),
    ]),
}


def main() -> None:
    kinds = {name: kind for name, kind, _, _ in FIELDS}
    schema = {
        "actorSpecification": 1,
        "fields": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                name: {"type": [kind, "null"], "description": desc, "nullable": True, "example": example}
                for name, kind, desc, example in FIELDS
            },
        },
        "views": {
            key: {
                "title": title,
                "description": desc,
                "transformation": {"fields": [f for f, _, _ in cols]},
                "display": {
                    "component": "table",
                    "properties": {
                        f: {"label": label, "format": fmt or FORMATS[kinds[f]]} for f, label, fmt in cols
                    },
                },
            }
            for key, (title, desc, cols) in VIEWS.items()
        },
    }
    path = Path(__file__).resolve().parents[1] / ".actor" / "dataset_schema.json"
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

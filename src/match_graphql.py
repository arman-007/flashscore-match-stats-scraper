"""Persisted GraphQL answers -> Python structures. Pure functions.

* `dlie2` -- lineups for every team sport that has them: per side the
  formation, average rating, coaches, players (shirt number, nationality as
  `teamName`, rating, role suffixes `(G)` `(C)` `(A)`), groups (`STARTERS`,
  `SUBSTITUTES`) and used substitutions with minutes.
* `epmsd` -- football player match stats: one entry per (player, stat type),
  about 100 types; `rawValue` is unrounded and ratios are 0-1. `ratings`
  holds the Flashscore rating per player.
* `epmsse` -- the players those stats belong to (team, position,
  goalkeeper flag, starter flag).
* `mmts` -- momentum: one signed value per minute.
"""

from __future__ import annotations

import re
from typing import Any

from .feeds import to_float

SITE_URL = "https://www.flashscore.com"

# Stats that only mean something for a goalkeeper. For outfield players
# Flashscore fills them with the team's numbers while the player was on.
GOALKEEPER_ONLY = {
    "SAVES_TOTAL", "GOALS_PREVENTED", "GOALS_PREVENTED_NO_PENALTIES", "PUNCHES_TOTAL",
    "KEEPER_THROWS_TOTAL", "KEEPER_SWEEPER_TOTAL", "HIGH_CLAIM_TOTAL", "HIGH_CLAIM_SAVED",
    "HIGH_CLAIM_EFFICIENCY", "PENALTIES_SAVED", "BIG_CHANCES_SAVED",
    "PENALTY_SHOOTOUT_ATTEMPTS_SAVES", "EXPECTED_GOALS_ON_TARGET_FACED", "SHOTS_FACED",
}
# Live-only flags and the rating (exposed as `rating`).
SKIPPED = {"MATCH_MINUTES_PLAYED_LIVE", "MATCH_ON_PITCH_LIVE", "FS_RATING"}
RENAMED = {
    "MATCH_MINUTES_PLAYED": "minutesPlayed",
    "ASSISTS_GOAL": "assists",
    "CARDS_YELLOW": "yellowCards",
    "CARDS_RED": "redCards",
    "CARDS_YELLOW_SECOND": "secondYellowCards",
    "GOALS_OWN": "ownGoals",
    "EXPECTED_GOALS": "expectedGoals",
    "EXPECTED_ASSISTS": "expectedAssists",
    "EXPECTED_GOALS_ON_TARGET": "expectedGoalsOnTarget",
    "EXPECTED_GOALS_ON_TARGET_FACED": "expectedGoalsOnTargetFaced",
}

PERIOD_BY_STAGE = {12: "1st Half", 13: "2nd Half", 6: "Extra Time", 7: "Penalties", 39: "1st Half ET", 40: "2nd Half ET"}


def stat_key(type_id: str) -> str:
    if type_id in RENAMED:
        return RENAMED[type_id]
    words = type_id.lower().split("_")
    return words[0] + "".join(w.capitalize() for w in words[1:])


def player_url(slug: str | None, player_id: str | None) -> str | None:
    if not slug or not player_id:
        return None
    return f"{SITE_URL}/player/{slug}/{player_id}/"


# ------------------------------------------------------------------ lineups


def parse_lineups(data: dict[str, Any] | None) -> dict[str, Any]:
    """`dlie2` -> {"home": side, "away": side}; a side is None without a lineup."""
    out: dict[str, Any] = {"home": None, "away": None}
    event = (data or {}).get("findEventById") or {}
    for participant in event.get("eventParticipants") or []:
        side = ((participant.get("type") or {}).get("side") or "").lower()
        lineup = participant.get("lineup") or {}
        players = lineup.get("players") or []
        if side not in out or not players:
            continue
        group_of: dict[str, tuple[str | None, str | None]] = {}
        for group in lineup.get("groups") or []:
            for pid in group.get("playerIds") or []:
                group_of[pid] = (group.get("groupType"), group.get("name"))
        subbed_in: dict[str, str | None] = {}
        subbed_out: dict[str, str | None] = {}
        for sub in lineup.get("usedSubstitutions") or []:
            if sub.get("playerId"):
                subbed_in[sub["playerId"]] = sub.get("minute")
            if sub.get("playerOutId"):
                subbed_out[sub["playerOutId"]] = sub.get("minute")
        coaches = ((lineup.get("coaches") or {}).get("players")) or []
        out[side] = {
            "formation": (lineup.get("formation") or {}).get("name") or None,
            "averageRating": to_float(participant.get("averageRating")),
            "coach": coaches[0].get("listName") or coaches[0].get("name") if coaches else None,
            "coachId": coaches[0].get("participantId") if coaches else None,
            "players": [
                _lineup_player(p, group_of, subbed_in, subbed_out) for p in players if p.get("participantId") or p.get("id")
            ],
        }
    return out


def _lineup_player(
    p: dict[str, Any],
    group_of: dict[str, tuple[str | None, str | None]],
    subbed_in: dict[str, str | None],
    subbed_out: dict[str, str | None],
) -> dict[str, Any]:
    pid = p.get("participantId") or p.get("id")
    group_type, group_name = group_of.get(pid, (None, None))
    roles = p.get("playerRoles") or []
    suffixes = {r.get("suffix") for r in roles}
    rating = p.get("rating") or {}
    return {
        "playerId": pid,
        "player": p.get("listName") or p.get("fieldName") or None,
        "playerUrl": player_url((p.get("participant") or {}).get("url"), pid),
        "shirtNumber": _int(p.get("number")),
        "nationality": p.get("teamName") or None,
        "starter": group_type == "STARTERS",
        "lineupGroup": group_name,
        "isGoalkeeper": "(G)" in suffixes,
        "isCaptain": "(C)" in suffixes,
        "roles": [r.get("title") for r in roles if r.get("title")] or None,
        "rating": to_float(rating.get("value")),
        "subbedInMinute": _minute(subbed_in.get(pid)),
        "subbedOutMinute": _minute(subbed_out.get(pid)),
    }


def _minute(text: str | None) -> int | None:
    m = re.match(r"(\d+)", text or "")
    return int(m.group(1)) if m else None


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ football player stats


def parse_player_stats(stats: dict[str, Any] | None, meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    """`epmsd` + `epmsse` -> one entry per player with a `stats` dict."""
    node = (stats or {}).get("findEventPMSById") or {}
    entries = (node.get("stats") or {}).get("entries") or []
    if not entries:
        return []
    ratings = {r.get("participantId"): r for r in node.get("ratings") or []}
    info: dict[str, dict[str, Any]] = {}
    for p in ((meta or {}).get("findEventPMSById") or {}).get("players") or []:
        participant = p.get("participant") or {}
        if participant.get("id"):
            info[participant["id"]] = {
                "player": participant.get("name") or participant.get("shortDisplayName"),
                "playerUrl": player_url(participant.get("url"), participant["id"]),
                "teamId": p.get("teamId"),
                "position": (p.get("position") or {}).get("name") or None,
                "isGoalkeeper": bool((p.get("position") or {}).get("isGoalkeeper")),
                "starter": p.get("inBaseLineup"),
            }

    by_player: dict[str, dict[str, Any]] = {}
    for e in entries:
        pid, type_id = e.get("playerId"), e.get("typeId")
        if not pid or not type_id or type_id in SKIPPED:
            continue
        by_player.setdefault(pid, {})[type_id] = e

    out = []
    for pid, values in by_player.items():
        meta_p = info.get(pid, {})
        goalkeeper = meta_p.get("isGoalkeeper", False)
        row_stats: dict[str, Any] = {}
        for type_id, e in sorted(values.items()):
            if type_id in GOALKEEPER_ONLY and not goalkeeper:
                continue
            row_stats[stat_key(type_id)] = _stat(e)
        rating = ratings.get(pid) or {}
        out.append({
            "playerId": pid,
            **meta_p,
            "rating": to_float(rating.get("value")),
            "isBestRating": bool(rating.get("isBestRating")) if rating else None,
            "stats": row_stats,
        })
    return out


def _stat(entry: dict[str, Any]) -> float | int | None:
    """`rawValue`, with ratios (displayed `78.12%`) as percentages like every other source."""
    raw = to_float(entry.get("rawValue"))
    if raw is None:
        return None
    if str(entry.get("value") or "").endswith("%"):
        return round(raw * 100, 2)
    return int(raw) if raw.is_integer() else round(raw, 4)


# ------------------------------------------------------------------ momentum


def parse_momentum(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """`mmts` -> per-minute momentum. Positive favours the home side."""
    node = (data or {}).get("findMatchMomentumStatsByMatchId") or {}
    entries = (node.get("momentum") or {}).get("entries") or []
    out = []
    for e in entries:
        frame = e.get("timeFrame") or {}
        value = e.get("momentumValue")
        if value is None:
            continue
        out.append({
            "minute": frame.get("displayTime"),
            "period": PERIOD_BY_STAGE.get(frame.get("eventStage"), str(frame.get("eventStage"))),
            "value": round(float(value), 4),
        })
    return out

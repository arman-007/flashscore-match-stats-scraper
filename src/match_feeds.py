"""A match's text feeds -> Python structures. Pure functions.

| Feed | Content |
| --- | --- |
| `df_sui_1_{E}` | period headers (`AC` label, `IG`/`IH` score), incidents (`III` ...), and the officials/venue block (`MIT`/`MIV` pairs) |
| `df_st_1_{E}` | team statistics: `SE` period, `SF` section, `SD` id, `SG` label, `SH`/`SI` home/away display value |
| `df_psn_1_{E}` | box score (basketball, hockey ...): `PA` section, `TT` table, `PF` columns, `PJ` player rows with `PC` values joined by `|` |
| `df_scr_1_{E}` | missing players |
| `df_lc_1_{E}` | live commentary |
| `df_hh_1_{E}` | head-to-head and both teams' last matches |

Incident records repeat keys: one `IE` starts each participant (scorer then
assist, player off then player on), so a record is walked as pairs.
"""

from __future__ import annotations

import re
from typing import Any

from .feeds import Record, every, first, is_empty, iso, records, to_float, to_int

SITE_URL = "https://www.flashscore.com"

_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?")
_RATIO_RE = re.compile(r"\((\d+)/(\d+)\)|^(\d+)/(\d+)$")
_APOSTROPHE_MINUTE_RE = re.compile(r"^(\d+)(?:\+(\d+))?'$")
_PLAYER_ID_RE = re.compile(r"/player/[^/]+/(\w{8})/?")


def player_id_from_url(url: str | None) -> str | None:
    m = _PLAYER_ID_RE.search(url or "")
    return m.group(1) if m else None


def absolute(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else SITE_URL + path


# ------------------------------------------------------------------ summary


def parse_summary(text: str) -> dict[str, Any]:
    """`df_sui_` -> period scores, incidents and the officials/venue block."""
    periods: list[dict[str, Any]] = []
    incidents: list[dict[str, Any]] = []
    info: dict[str, Any] = {}
    period: str | None = None
    if is_empty(text):
        return {"periodScores": [], "incidents": [], "info": info}
    for rec in records(text):
        key = rec[0][0]
        if key == "AC":
            period = rec[0][1]
            games_home, games_away = every(rec, "IG"), every(rec, "IH")
            periods.append({
                "period": period,
                "home": to_int(games_home[0]) if games_home else None,
                "away": to_int(games_away[0]) if games_away else None,
                "homeTiebreak": to_int(games_home[1]) if len(games_home) > 1 else None,
                "awayTiebreak": to_int(games_away[1]) if len(games_away) > 1 else None,
            })
        elif key == "III":
            incidents.append(_incident(rec, period))
        elif any(k == "MIT" for k, _ in rec):
            info.update(_info(rec))
        elif key == "RB":
            info["duration"] = rec[0][1] or None
    return {"periodScores": periods, "incidents": incidents, "info": info}


def _incident(rec: Record, period: str | None) -> dict[str, Any]:
    top: dict[str, str] = {}
    people: list[dict[str, str]] = []
    for key, value in rec:
        if key == "IE":
            people.append({})
        elif people:
            people[-1].setdefault(key, value)
        else:
            top.setdefault(key, value)
    for person in people:
        for key in ("INX", "IOX", "IJ", "IL"):
            if key in person:
                top.setdefault(key, person[key])

    roles = [p.get("IK") or "" for p in people]
    primary = 0
    for i, role in enumerate(roles):
        if role.endswith(" - In"):
            primary = i
    kind = roles[0] if roles else None
    if kind and kind.startswith("Substitution"):
        kind = "Substitution"
    main = people[primary] if people else {}
    others = [p for i, p in enumerate(people) if i != primary]
    related = others[0] if others else {}
    minute = top.get("IB") or None
    m = _APOSTROPHE_MINUTE_RE.match(minute or "")
    commentary = next((p.get("ICT") for p in people if p.get("ICT")), None)
    side = top.get("IA")
    return {
        "incidentId": top.get("III"),
        "period": period,
        "minute": minute,
        "minuteValue": int(m.group(1)) if m else None,
        "addedTime": int(m.group(2)) if m and m.group(2) else None,
        "side": "home" if side == "1" else "away" if side == "2" else None,
        "type": kind,
        "player": main.get("IF") or None,
        "playerId": main.get("IM") or None,
        "relatedPlayer": related.get("IF") or None,
        "relatedPlayerId": related.get("IM") or None,
        "relatedRole": related.get("IK") or None,
        "otherPlayers": [
            {"role": p.get("IK") or None, "player": p.get("IF") or None, "playerId": p.get("IM") or None}
            for p in others[1:]
        ] or None,
        "reason": top.get("IL") or None,
        "homeScoreAfter": to_int(top.get("INX")),
        "awayScoreAfter": to_int(top.get("IOX")),
        "commentary": commentary,
    }


def _info(rec: Record) -> dict[str, Any]:
    referees: list[dict[str, Any]] = []
    out: dict[str, Any] = {}
    kind: str | None = None
    for key, value in rec:
        if key == "MIT":
            kind = value
            continue
        if key != "MIV" or kind is None:
            continue
        if kind == "REF":
            referees.append({"name": value or None, "country": None})
        elif kind == "RCC" and referees:
            referees[-1]["country"] = value or None
        elif kind == "VEN":
            out["venue"] = value or None
        elif kind == "TWN":
            out["city"] = value or None
        elif kind == "ATT":
            out["attendance"] = to_int(value.replace(" ", "").replace(",", ""))
        elif kind == "CAP":
            out["capacity"] = to_int(value.replace(" ", "").replace(",", ""))
    if referees:
        out["referee"] = referees[0]["name"]
        out["refereeCountry"] = referees[0]["country"]
        out["referees"] = referees
    return out


# ------------------------------------------------------------------ team statistics


def parse_statistics(text: str) -> list[dict[str, Any]]:
    """`df_st_` -> one entry per (period, stat), periods in feed order (`Match` first)."""
    out: list[dict[str, Any]] = []
    period: str | None = None
    section: str | None = None
    if is_empty(text):
        return out
    for rec in records(text):
        key = rec[0][0]
        if key == "SE":
            period, section = rec[0][1], None
        elif key == "SF":
            section = rec[0][1] or None
        elif any(k == "SG" for k, _ in rec):
            home, away = first(rec, "SH"), first(rec, "SI")
            hv, hm, ha = stat_value(home)
            av, am, aa = stat_value(away)
            out.append({
                "period": period,
                "section": section,
                "stat": first(rec, "SG"),
                "statId": to_int(first(rec, "SD")),
                "home": hv,
                "away": av,
                "homeDisplay": home,
                "awayDisplay": away,
                "homeMade": hm,
                "homeAttempted": ha,
                "awayMade": am,
                "awayAttempted": aa,
            })
    return out


def stat_value(display: str | None) -> tuple[float | int | None, int | None, int | None]:
    """`76% (260/343)` -> (76, 260, 343); `2/3` -> (None, 2, 3); `213 km/h` -> (213, None, None)."""
    if display is None:
        return None, None, None
    text = display.strip()
    made = attempted = None
    ratio = _RATIO_RE.search(text)
    if ratio:
        made = int(ratio.group(1) or ratio.group(3))
        attempted = int(ratio.group(2) or ratio.group(4))
        if ratio.group(3):
            return None, made, attempted
    m = _NUMBER_RE.match(text)
    return (_number(m.group(0)) if m else None), made, attempted


def _number(text: str) -> float | int | None:
    value = to_float(text)
    if value is None:
        return None
    return int(value) if value.is_integer() and "." not in text else value


# ------------------------------------------------------------------ box score

BOX_KEYS = {
    "PTS": "points", "REB": "rebounds", "AST": "assists", "MIN": "minutesPlayed",
    "FGM": "fieldGoalsMade", "FGA": "fieldGoalsAttempted",
    "2PM": "twoPointersMade", "2PA": "twoPointersAttempted",
    "3PM": "threePointersMade", "3PA": "threePointersAttempted",
    "FTM": "freeThrowsMade", "FTA": "freeThrowsAttempted",
    "+/-": "plusMinus", "OR": "offensiveRebounds", "DR": "defensiveRebounds",
    "PF": "personalFouls", "ST": "steals", "TO": "turnovers", "BS": "blockedShots",
    "BA": "blocksAgainst", "TFS": "technicalFouls",
    "G": "goals", "A": "assists", "P": "points", "PIM": "penaltyMinutes",
    "SOG": "shotsOnGoal", "HT": "hits", "GV": "giveaways", "TK": "takeaways",
    "FO": "faceoffs", "FOW": "faceoffsWon", "FO%": "faceoffPercentage",
    "TOI": "timeOnIce", "SV": "saves", "SV%": "savePercentage",
}
# `fg` columns hold `made-attempted`; the second number gets its own key.
BOX_ATTEMPTED_KEYS = {"SV": "shotsAgainst"}


def parse_box_score(text: str) -> list[dict[str, Any]]:
    """`df_psn_` -> one entry per player from the first (`Overall`) section.

    The later sections repeat each team's players under the team's full name,
    which is how a row is tied to a side (`PN` is only a three-letter code).
    """
    if is_empty(text):
        return []
    sections: list[tuple[str, list[Record]]] = []
    for rec in records(text):
        if rec[0][0] == "PA":
            sections.append((rec[0][1], []))
        elif sections:
            sections[-1][1].append(rec)
    if not sections:
        return []

    team_of: dict[str, str] = {}
    for name, recs in sections[1:]:
        for rec in recs:
            if rec[0][0] == "PJ":
                team_of.setdefault(first(rec, "PK") or first(rec, "PJ") or "", name)

    players: list[dict[str, Any]] = []
    table: str | None = None
    columns: list[tuple[str, str, str]] = []
    for rec in sections[0][1]:
        key = rec[0][0]
        if key == "TT":
            table, columns = rec[0][1] or None, []
        elif key == "PF":
            label = first(rec, "PG")
            if label:
                columns.append((rec[0][1], label, first(rec, "PH") or "num"))
        elif key == "PJ":
            url = first(rec, "PK")
            values = (first(rec, "PC") or "").split("|")
            stats: dict[str, Any] = {}
            for (code, label, kind), raw in zip(columns, values):
                name = BOX_KEYS.get(code) or camel(label)
                if kind == "fg":
                    made, _, attempted = raw.partition("-")
                    stats[name] = to_int(made) if raw != "-" else 0
                    stats[BOX_ATTEMPTED_KEYS.get(code, name + "Attempted")] = to_int(attempted) if attempted else 0
                else:
                    stats[name] = box_value(raw, kind)
            players.append({
                "player": first(rec, "PJ") or None,
                "playerId": player_id_from_url(url),
                "playerUrl": absolute(url),
                "nationality": first(rec, "PL") or None,
                "teamCode": first(rec, "PN") or None,
                "teamName": team_of.get(url or first(rec, "PJ") or ""),
                "boxScoreTable": table,
                "stats": stats,
            })
    return players


def box_value(raw: str, kind: str) -> float | int | None:
    """`-` is Flashscore's zero. `time` is `mm:ss` -> minutes."""
    text = (raw or "").strip()
    if not text:
        return None
    if text == "-":
        return 0
    if kind == "time" and ":" in text:
        minutes, _, seconds = text.partition(":")
        if minutes.isdigit() and seconds.isdigit():
            return round(int(minutes) + int(seconds) / 60, 2)
        return None
    return _number(text.rstrip("%"))


def camel(label: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", label.replace("%", " percentage").replace("+/-", "plus minus"))
    if not words:
        return label
    return words[0].lower() + "".join(w[:1].upper() + w[1:].lower() for w in words[1:])


# ------------------------------------------------------------------ missing players, commentary


def parse_missing_players(text: str) -> list[dict[str, Any]]:
    out = []
    if is_empty(text):
        return out
    for rec in records(text):
        if rec[0][0] != "SPT":
            continue
        url = first(rec, "SPR")
        out.append({
            "side": "home" if first(rec, "SPT") == "1" else "away",
            "player": first(rec, "SPN") or None,
            "playerId": first(rec, "SPI") or player_id_from_url(url),
            "playerUrl": absolute(url),
            "nationality": first(rec, "SPG") or None,
            "reason": first(rec, "SPE") or None,
            "availability": first(rec, "SPD") or None,
        })
    return out


def parse_commentary(text: str) -> list[dict[str, Any]]:
    """`df_lc_` -> commentary lines, oldest first (the feed is newest first)."""
    out = []
    if is_empty(text):
        return out
    for rec in records(text):
        if not any(k == "MD" for k, _ in rec):
            continue
        clock = (first(rec, "MK") or "").strip()
        out.append({
            "minute": first(rec, "MB") or None,
            "clock": clock if clock.strip("'") else None,
            "type": first(rec, "MC") or None,
            "text": first(rec, "MD") or None,
            "important": first(rec, "MF") == "1",
        })
    out.reverse()
    return out


# ------------------------------------------------------------------ head-to-head

_RESULT = {"w": "W", "d": "D", "l": "L", "lo": "L", "wo": "W"}


def parse_head_to_head(text: str, home_team: str | None) -> dict[str, list[dict[str, Any]]]:
    """`df_hh_` -> the first tab (`Overall`, or `All surfaces` in tennis): both
    sides' last matches and their meetings. Later tabs are home/away or surface splits."""
    out: dict[str, list[dict[str, Any]]] = {"homeLastMatches": [], "awayLastMatches": [], "meetings": []}
    if is_empty(text):
        return out
    tabs_seen = 0
    bucket: list[dict[str, Any]] | None = None
    for rec in records(text):
        key = rec[0][0]
        if key == "KA":
            tabs_seen += 1
            bucket = None
        elif key == "KB":
            if tabs_seen > 1:
                bucket = None
                continue
            name = rec[0][1]
            if name.lower().startswith("head-to-head"):
                bucket = out["meetings"]
            elif home_team and name.split(":", 1)[-1].strip() == home_team:
                bucket = out["homeLastMatches"]
            else:
                bucket = out["awayLastMatches"]
        elif key == "KC" and bucket is not None:
            bucket.append(_h2h_match(rec, with_result=bucket is not out["meetings"]))
    return out


def _h2h_match(rec: Record, *, with_result: bool) -> dict[str, Any]:
    home, away = first(rec, "KJ") or "", first(rec, "KK") or ""
    event_id = first(rec, "KP")
    winner = "home" if home.startswith("*") else "away" if away.startswith("*") else None
    row = {
        "eventId": event_id,
        "url": f"{SITE_URL}/match/{event_id}/" if event_id else None,
        "startTime": iso(first(rec, "KC")),
        "competition": first(rec, "KF") or None,
        "competitionCountry": first(rec, "KH") or None,
        "homeTeam": home.lstrip("*") or None,
        "homeTeamId": first(rec, "UQ") or None,
        "awayTeam": away.lstrip("*") or None,
        "awayTeamId": first(rec, "UO") or None,
        "homeScore": to_int(first(rec, "KU")),
        "awayScore": to_int(first(rec, "KT")),
        "winner": winner,
    }
    if with_result:
        row["result"] = _RESULT.get((first(rec, "WIS") or "").lower())
    return row

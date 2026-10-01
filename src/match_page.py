"""A match's HTML page -> header, teams and the tabs the match has.

`/match/{eventId}/` embeds `window.environment`, a JSON object with:

* `participantsData.home/away[]` -- team id (`2XrRecc3`, the id in team URLs),
  name, `detail_link`. Tennis doubles list two players per side.
* `header.tournament` -- `{"tournament": "Premier League - Round 5",
  "link": "/football/england/premier-league/"}` and `country_name`.
* `common_feed` -- one-key dicts: `DA` status, `DB` stage, `DC` start time,
  `DE`/`DF` score, and **`DX`, the comma-separated tabs this match has**
  (`ST` statistics, `PS` player stats, `LI` lineups, `SCR` missing players,
  `LC` commentary, `MC` momentum, `HH` head-to-head ...). Only the feeds a
  match advertises are worth requesting.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .feeds import iso, to_int
from .sports import SPORT_BY_ID

SITE_URL = "https://www.flashscore.com"

_ENV_RE = re.compile(r"window\.environment\s*=\s*(\{.*?\});\s*</script>", re.S)

STATUS_BY_CODE = {
    "1": "scheduled",
    "2": "live",
    "3": "finished",
    "4": "postponed",
    "5": "cancelled",
    "36": "interrupted",
    "37": "abandoned",
    "43": "delayed",
    "54": "awarded",
}

# `DB` when the match is over: how it ended.
DECIDED_BY = {"3": "regular-time", "10": "extra-time", "11": "penalties", "9": "walkover", "54": "awarded"}


class MatchPageError(ValueError):
    """The page is not a match page this parser recognises."""


def parse_match_page(html: str, event_id: str) -> dict[str, Any]:
    m = _ENV_RE.search(html)
    if not m:
        raise MatchPageError(f"match {event_id}: no window.environment on the page")
    try:
        env = json.loads(m.group(1))
    except ValueError as exc:
        raise MatchPageError(f"match {event_id}: window.environment is not JSON") from exc

    sides = env.get("participantsData") or {}
    home, away = sides.get("home") or [], sides.get("away") or []
    if not home or not away:
        raise MatchPageError(f"match {event_id}: the page names no home or away side")

    core: dict[str, Any] = {}
    for entry in env.get("common_feed") or []:
        if isinstance(entry, dict):
            core.update(entry)

    header = env.get("header") or {}
    tournament = header.get("tournament") or {}
    competition, round_name = split_round(tournament.get("tournament"))
    category = tournament.get("category") or None
    league_path = tournament.get("link") or None
    sport_id = to_int(env.get("sport_id"))
    status_code = str(core.get("DA") or "")
    status = STATUS_BY_CODE.get(status_code)
    stage_code = str(core.get("DB") or "")
    scored = status in ("live", "finished", "awarded")

    return {
        "eventId": env.get("event_id_c") or event_id,
        "url": f"{SITE_URL}/match/{env.get('event_id_c') or event_id}/",
        "sport": SPORT_BY_ID.get(sport_id or 0) or (env.get("sport_url") or "").strip("/") or None,
        "sportId": sport_id,
        "country": header.get("country_name") or None,
        "competition": f"{category}: {competition}" if category and competition else competition,
        "competitionUrl": SITE_URL + league_path if league_path else None,
        "round": round_name,
        "startTime": iso(core.get("DC")),
        "status": status,
        "decidedBy": DECIDED_BY.get(stage_code) if status == "finished" else None,
        **_side("home", home),
        **_side("away", away),
        "homeScore": to_int(core.get("DE")) if scored else None,
        "awayScore": to_int(core.get("DF")) if scored else None,
        "tabs": [t for t in str(core.get("DX") or "").split(",") if t],
    }


def split_round(text: str | None) -> tuple[str | None, str | None]:
    """`Premier League - Round 5` -> (`Premier League`, `Round 5`).

    Only the last ` - ` splits, and only when the tail reads like a stage
    (`Round 5`, `Final`, `Play Offs`), so `Bosnia - Herzegovina Cup` stays whole.
    """
    if not text:
        return None, None
    head, sep, tail = text.rpartition(" - ")
    if sep and head and re.search(
        r"round|final|play|group|semi|quarter|qualif|stage|phase|week|leg|1/\d+|knockout",
        tail,
        re.I,
    ):
        return head, tail
    return text, None


def _side(prefix: str, players: list[dict[str, Any]]) -> dict[str, Any]:
    names = [p.get("name") for p in players if p.get("name")]
    first = players[0]
    link = first.get("detail_link") or None
    return {
        f"{prefix}Team": "/".join(names) if names else None,
        f"{prefix}TeamId": first.get("id") or None,
        f"{prefix}TeamUrl": f"{SITE_URL}{link.rstrip('/')}/" if link else None,
    }

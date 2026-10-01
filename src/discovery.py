"""League, season and team URLs -> the finished matches to scrape.

Both page types embed page 0 of their results list in
`cjs.initialFeeds['results'] = {data: `...`, allEventsCount: N, seasonId: S}`
and continue it through text feeds, 40 matches a page, newest first:

* league / season pages: `tr_{sport}_{country}_{templateId}_{seasonId}_{page}_0_en_1`
  (template id from `leaguePageHeaderData` or `"tournament_id"`);
* team pages: `pr_{sport}_{country}_{teamId}_{page}_0_en_1` (inline
  `country_id = "198"; participant_id = "hA1Zm19f"`).

The sport id is the list's own `SA` record; the country id is the
competition header's `ZB` (league lists) or the page's `country_id` (teams).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .feeds import first, is_empty, records, to_int
from .sports import ALIASES, SPORTS

SITE_URL = "https://www.flashscore.com"

_FEED_RE = re.compile(
    r"cjs\.initialFeeds\[['\"]results['\"]\]\s*=\s*\{\s*data:\s*`(.*?)`,"
    r"\s*allEventsCount:\s*(\d+),(?:\s*seasonId:\s*(\d+),)?",
    re.S,
)
_TEMPLATE_RES = (
    re.compile(r"leaguePageHeaderData\s*=\s*\{.*?tournamentTemplateId:\s*\"(\w+)\"", re.S),
    re.compile(r'"tournament_id":"(\w+)"'),
)
_TEAM_COUNTRY_RE = re.compile(r'country_id\s*=\s*"(\d+)"')
_TEAM_ID_RE = re.compile(r'participant_id\s*=\s*"(\w+)"')

_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9]{8}$")
_MID_IN_URL = re.compile(r"[?&]mid=([A-Za-z0-9]{8})")
_ID_IN_MATCH_URL = re.compile(r"/match/([A-Za-z0-9]{8})(?:[/?#]|$)")
_TEAM_URL_RE = re.compile(r"/team/([a-z0-9][a-z0-9-]*)/([A-Za-z0-9]{8})(?=/|$|[?#])", re.I)
_HOST_RE = re.compile(r"^(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?=/|$)", re.I)
_LEAGUE_SUBPAGES = {"results", "fixtures", "standings", "draw", "archive", "summary", "news", "top-scorers", "odds"}


class DiscoveryError(ValueError):
    """A league or team page did not have the list this module reads."""


@dataclass(frozen=True)
class Source:
    """A league/season or team page to list matches from."""

    kind: str  # "league" | "team"
    path: str
    team_id: str | None = None

    @property
    def url(self) -> str:
        return SITE_URL + self.path


# ------------------------------------------------------------------ URL parsing


def event_id_from(value: str) -> str | None:
    """A bare id or any match URL. `/match/football/a-x/b-y/?mid=ID` names the
    sport after `/match/`, which has the shape of an id, so `mid=` wins."""
    text = value.strip()
    m = _MID_IN_URL.search(text)
    if m:
        return m.group(1)
    m = _ID_IN_MATCH_URL.search(text)
    if m and m.group(1).lower() not in SPORTS:
        return m.group(1)
    return text if _EVENT_ID_RE.match(text) and text.lower() not in SPORTS else None


def team_source(value: str) -> Source | None:
    m = _TEAM_URL_RE.search(value)
    if not m:
        return None
    return Source("team", f"/team/{m.group(1).lower()}/{m.group(2)}/", m.group(2))


def league_source(value: str) -> Source | None:
    """`.../football/england/premier-league-2024-2025/results/` -> that season's page."""
    text = _HOST_RE.sub("", value.strip()).split("?", 1)[0].split("#", 1)[0]
    parts = [p for p in text.lower().split("/") if p]
    if len(parts) < 3:
        return None
    sport = ALIASES.get(parts[0], parts[0])
    country, slug = parts[1], parts[2]
    if sport not in SPORTS or country in ("match", "team", "player") or slug in _LEAGUE_SUBPAGES:
        return None
    if not re.fullmatch(r"[a-z0-9-]+", country) or not re.fullmatch(r"[a-z0-9-]+", slug):
        return None
    return Source("league", f"/{sport}/{country}/{slug}/")


# ------------------------------------------------------------------ pages and lists


def parse_source_page(html: str, source: Source) -> dict[str, Any]:
    """The page's first results page plus what its continuation feed needs."""
    m = _FEED_RE.search(html)
    if not m:
        raise DiscoveryError(f"{source.path}: the page has no results list")
    data = m.group(1)
    matches = parse_match_list(data)
    page: dict[str, Any] = {
        "matches": matches,
        "total": int(m.group(2)),
        "seasonId": int(m.group(3)) if m.group(3) else None,
        "sportId": next((x["sportId"] for x in matches if x["sportId"]), None) or _sport_id(data),
    }
    if source.kind == "team":
        country = _TEAM_COUNTRY_RE.search(html)
        team = _TEAM_ID_RE.search(html)
        page["countryId"] = country.group(1) if country else None
        page["teamId"] = team.group(1) if team else source.team_id
    else:
        template = next((r.search(html) for r in _TEMPLATE_RES if r.search(html)), None)
        page["templateId"] = template.group(1) if template else None
        page["countryId"] = next((x["countryId"] for x in matches if x["countryId"]), None)
    return page


def continuation_feed(source: Source, page: dict[str, Any], number: int) -> str | None:
    sport, country = page.get("sportId"), page.get("countryId")
    if not sport or not country:
        return None
    if source.kind == "team":
        return f"pr_{sport}_{country}_{page['teamId']}_{number}_0_en_1" if page.get("teamId") else None
    if not page.get("templateId") or page.get("seasonId") is None:
        return None
    return f"tr_{sport}_{country}_{page['templateId']}_{page['seasonId']}_{number}_0_en_1"


def parse_match_list(text: str) -> list[dict[str, Any]]:
    """A results list -> `{eventId, timestamp, status, competition, ...}` in feed order."""
    out: list[dict[str, Any]] = []
    if is_empty(text):
        return out
    sport_id: int | None = None
    header: list[tuple[str, str]] = []
    for rec in records(text):
        key = rec[0][0]
        if key == "SA":
            sport_id = to_int(rec[0][1])
        elif key == "ZA":
            header = rec
        elif key == "AA":
            out.append({
                "eventId": first(rec, "AA"),
                "timestamp": to_int(first(rec, "AD")),
                "finished": first(rec, "AB") == "3",
                "competition": first(header, "ZA"),
                "countryId": first(header, "ZB"),
                "sportId": sport_id,
            })
    return out


def _sport_id(text: str) -> int | None:
    m = re.search(r"SA÷(\d+)", text)
    return int(m.group(1)) if m else None

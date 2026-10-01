"""Actor input parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .discovery import Source, event_id_from, league_source, team_source

INCLUDES = ("statistics", "lineups", "playerStats", "missingPlayers", "momentum", "commentary", "headToHead")
DEFAULT_INCLUDES = ("statistics", "lineups", "playerStats", "missingPlayers")
DEFAULT_MAX_PER_SOURCE = 10
DEFAULT_MAX_ITEMS = 10000

MAX_URLS = 1000


@dataclass(frozen=True)
class ActorInput:
    event_ids: list[str]
    sources: list[Source]
    include: list[str]
    max_per_source: int | None
    date_from: date | None
    date_to: date | None
    include_unused_substitutes: bool
    max_items: int
    proxy_config_input: dict[str, Any] | None

    def wants(self, part: str) -> bool:
        return part in self.include

    @property
    def wants_players(self) -> bool:
        return self.wants("lineups") or self.wants("playerStats")

    def in_range(self, timestamp: int | None) -> bool:
        if timestamp is None:
            return self.date_from is None and self.date_to is None
        day = datetime.fromtimestamp(0, tz=timezone.utc).date() + timedelta(seconds=timestamp)
        if self.date_from and day < self.date_from:
            return False
        return not (self.date_to and day > self.date_to)


def parse_input(raw: dict[str, Any] | None) -> ActorInput:
    raw = raw or {}

    event_ids: list[str] = []
    sources: list[Source] = []
    for name in ("matchUrls", "leagueUrls", "teamUrls"):
        for value in _as_list(raw.get(name), name, MAX_URLS):
            text = _url_value(value)
            if not text:
                continue
            # Route by what the URL is, whichever field it was pasted into.
            event_id = event_id_from(text)
            if event_id:
                if event_id not in event_ids:
                    event_ids.append(event_id)
                continue
            source = team_source(text) or league_source(text)
            if source is None:
                raise ValueError(
                    f"{text!r} in `{name}` is not a Flashscore match, league or team URL. Use e.g. "
                    "https://www.flashscore.com/match/j52jHsN8/, "
                    "https://www.flashscore.com/football/england/premier-league/ or "
                    "https://www.flashscore.com/team/arsenal/hA1Zm19f/."
                )
            if source not in sources:
                sources.append(source)

    if not event_ids and not sources:
        raise ValueError(
            "Add at least one match, league or team URL: `matchUrls` (e.g. "
            "https://www.flashscore.com/match/j52jHsN8/), `leagueUrls` (e.g. "
            "https://www.flashscore.com/football/england/premier-league/) or `teamUrls` (e.g. "
            "https://www.flashscore.com/team/arsenal/hA1Zm19f/)."
        )

    date_from = _date(raw.get("dateFrom"), "dateFrom")
    date_to = _date(raw.get("dateTo"), "dateTo")
    if date_from and date_to and date_from > date_to:
        raise ValueError(f"`dateFrom` ({date_from}) is after `dateTo` ({date_to}).")

    return ActorInput(
        event_ids=event_ids,
        sources=sources,
        include=_includes(raw.get("include")),
        max_per_source=_limit(raw.get("maxMatchesPerSource"), "maxMatchesPerSource", DEFAULT_MAX_PER_SOURCE),
        date_from=date_from,
        date_to=date_to,
        include_unused_substitutes=bool(raw.get("includeUnusedSubstitutes")),
        max_items=_positive(raw.get("maxItems"), "maxItems", DEFAULT_MAX_ITEMS),
        proxy_config_input=raw.get("proxyConfiguration"),
    )


def _includes(raw: Any) -> list[str]:
    if raw is None:
        return list(DEFAULT_INCLUDES)
    by_lower = {o.lower(): o for o in INCLUDES}
    out: list[str] = []
    for value in _as_list(raw, "include", len(INCLUDES) * 2):
        text = str(value or "").strip().lower()
        if text not in by_lower:
            raise ValueError(f"{value!r} is not valid in `include`. Use any of: {', '.join(INCLUDES)}.")
        if by_lower[text] not in out:
            out.append(by_lower[text])
    return out


def _date(value: Any, name: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"`{name}` must be a date like 2026-09-19; got {value!r}.") from exc


def _limit(value: Any, name: str, default: int) -> int | None:
    """A per-source cap: blank -> default, 0 -> no cap."""
    if value in (None, ""):
        return default
    number = _int(value, name)
    if number < 0:
        raise ValueError(f"`{name}` must be 0 (no limit) or more; got {number}.")
    return number or None


def _positive(value: Any, name: str, default: int) -> int:
    if value in (None, ""):
        return default
    number = _int(value, name)
    if number < 1:
        raise ValueError(f"`{name}` must be at least 1; got {number}.")
    return number


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"`{name}` must be a whole number; got {value!r}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{name}` must be a whole number; got {value!r}.") from exc


def _url_value(value: Any) -> str:
    """Apify's `requestListSources` editor sends `{"url": ...}` objects."""
    if isinstance(value, dict):
        value = value.get("url")
    return str(value or "").strip()


def _as_list(raw: Any, name: str, limit: int) -> list:
    if raw in (None, ""):
        return []
    values = raw if isinstance(raw, list) else [raw]
    if len(values) > limit:
        raise ValueError(f"`{name}` accepts at most {limit} values; got {len(values)}.")
    return values

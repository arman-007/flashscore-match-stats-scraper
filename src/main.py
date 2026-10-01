"""Orchestration: list matches from leagues and teams, then scrape each match
(page -> the feeds its tabs advertise) into one match row plus player rows."""

from __future__ import annotations

import asyncio
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any

from apify import Actor

from . import billing as bill
from .billing import Billing
from .discovery import DiscoveryError, Source, continuation_feed, parse_match_list, parse_source_page
from .feeds import is_empty
from .flashscore_client import FlashscoreClient, FlashscoreError, FlashscoreNotFoundError
from .input import ActorInput, parse_input
from .match_feeds import (
    parse_box_score,
    parse_commentary,
    parse_head_to_head,
    parse_missing_players,
    parse_statistics,
    parse_summary,
)
from .match_graphql import parse_lineups, parse_momentum, parse_player_stats
from .match_page import MatchPageError, parse_match_page
from .proxy_tiers import SessionRotator, TieredProxyFallback

# Matches scraped at once; each is one page plus ~6 feeds fetched together.
MATCH_CONCURRENCY = 4
# Safety stop for list paging (40 matches a page; a team's whole history is ~130).
MAX_LIST_PAGES = 150
FOOTBALL = 1
PROJECT_ID = 2
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


async def main() -> None:
    async with Actor:
        try:
            await _run()
        except Exception as exc:  # noqa: BLE001 - surface it, don't exit opaquely
            Actor.log.exception("Unhandled error")
            await Actor.fail(
                status_message=f"Unhandled error: {exc!r}\n{traceback.format_exc()[-1500:]}"
            )


async def _run() -> None:
    raw_input = await Actor.get_input() or {}
    try:
        actor_input = parse_input(raw_input)
    except ValueError as exc:
        await _report_bad_input(exc)
        return

    proxy_url, proxy_fallback = await _build_proxy_strategy(actor_input)
    state = RunState(billing=await Billing.create(), actor_input=actor_input)

    async with FlashscoreClient(proxy=proxy_url, proxy_fallback=proxy_fallback) as client:
        await run_all(client, state)
        state.escalations = client.escalations_used

    await _report(state)


class RunState:
    def __init__(self, *, billing: Billing, actor_input: ActorInput) -> None:
        self.billing = billing
        self.actor_input = actor_input
        self.event_ids: list[str] = list(actor_input.event_ids)
        self.pushed = 0
        self.matches_done = 0
        self.not_found = 0
        self.empty_sources = 0
        self.errors: list[str] = []
        self.failed: list[str] = []
        self.escalations = 0

    @property
    def done(self) -> bool:
        return self.pushed >= self.actor_input.max_items or self.billing.budget_exhausted

    def add(self, event_id: str) -> None:
        if event_id not in self.event_ids:
            self.event_ids.append(event_id)

    async def push(self, rows: list[dict[str, Any]], event: str) -> int:
        room = self.actor_input.max_items - self.pushed
        if room <= 0 or self.billing.budget_exhausted or not rows:
            return 0
        pushed = await self.billing.push(rows[:room], event)
        self.pushed += pushed
        return pushed

    def record_failure(self, label: str, exc: Exception) -> None:
        Actor.log.warning(f"Failed to scrape {label}: {exc}")
        self.errors.append(str(exc))
        self.failed.append(label)


async def run_all(client: FlashscoreClient, state: RunState) -> None:
    for source in state.actor_input.sources:
        for event_id in await discover(client, state, source):
            state.add(event_id)
    index = 0
    while index < len(state.event_ids) and not state.done:
        chunk = state.event_ids[index : index + MATCH_CONCURRENCY]
        index += len(chunk)
        results = await asyncio.gather(*(scrape_match(client, state, e) for e in chunk))
        for result in results:
            if result is None:
                continue
            match_row, player_rows = result
            if state.done:
                return
            if await state.push([match_row], bill.MATCH_EVENT):
                await state.push(player_rows, bill.PLAYER_EVENT)
                state.matches_done += 1


# ------------------------------------------------------------------ discovery


async def discover(client: FlashscoreClient, state: RunState, source: Source) -> list[str]:
    """The newest finished matches of a league/season or team, within the date range."""
    actor_input = state.actor_input
    try:
        page = parse_source_page(await client.page(source.path), source)
    except FlashscoreNotFoundError:
        state.not_found += 1
        await Billing.push_unbilled({
            "recordType": "error",
            "error": "SOURCE_NOT_FOUND",
            "url": source.url,
            "errorMessage": (
                f"Flashscore has no {source.kind} page at {source.url} (not charged). Copy the URL "
                "from the address bar of the league or team page."
            ),
        })
        return []
    except DiscoveryError:
        await _no_matches(
            state,
            source,
            "the page lists no results yet. For a season that has not started, use a past "
            "season's URL such as .../premier-league-2025-2026/",
        )
        return []
    except FlashscoreError as exc:
        state.record_failure(f"{source.kind} {source.url}", exc)
        return []

    limit = actor_input.max_per_source
    seen: dict[str, dict[str, Any]] = {}

    def take(matches: list[dict[str, Any]]) -> None:
        for m in matches:
            if m["eventId"]:
                seen.setdefault(m["eventId"], m)

    def selected() -> list[dict[str, Any]]:
        return [m for m in seen.values() if m["finished"] and actor_input.in_range(m["timestamp"])]

    def oldest_before_range() -> bool:
        if actor_input.date_from is None:
            return False
        stamps = [m["timestamp"] for m in seen.values() if m["timestamp"] is not None]
        return bool(stamps) and _day(min(stamps)) < actor_input.date_from

    take(page["matches"])
    for number in range(1, MAX_LIST_PAGES + 1):
        if (limit and len(selected()) >= limit) or len(seen) >= page["total"] or oldest_before_range():
            break
        name = continuation_feed(source, page, number)
        if name is None:
            break
        try:
            text = await client.feed(name)
        except FlashscoreError as exc:
            state.record_failure(f"match list page {number} of {source.url}", exc)
            break
        more = parse_match_list(text) if not is_empty(text) else []
        if not more:
            break
        before = len(seen)
        take(more)
        if len(seen) == before:
            break

    picked = sorted(selected(), key=lambda m: m["timestamp"] or 0, reverse=True)
    if limit:
        picked = picked[:limit]
    if not picked:
        why = "no finished match in the requested range"
        if source.kind == "league" and actor_input.date_from is None and actor_input.date_to is None:
            why += (
                ". A league URL lists its current season only; for one that has not started yet, "
                "use a past season's URL such as .../premier-league-2025-2026/"
            )
        await _no_matches(state, source, why)
    else:
        Actor.log.info(f"{source.url}: {len(picked)} finished match(es) to scrape.")
    return [m["eventId"] for m in picked]


def _day(timestamp: int) -> date:
    return (_EPOCH + timedelta(seconds=timestamp)).date()


async def _no_matches(state: RunState, source: Source, why: str) -> None:
    state.empty_sources += 1
    await Billing.push_unbilled({
        "recordType": "error",
        "error": "NO_MATCHES",
        "url": source.url,
        "errorMessage": f"{source.url}: {why} (not charged).",
    })


# ------------------------------------------------------------------ one match


async def scrape_match(
    client: FlashscoreClient, state: RunState, event_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    try:
        page = parse_match_page(await client.page(f"/match/{event_id}/"), event_id)
    except FlashscoreNotFoundError:
        state.not_found += 1
        await Billing.push_unbilled({
            "recordType": "error",
            "error": "MATCH_NOT_FOUND",
            "eventId": event_id,
            "url": f"https://www.flashscore.com/match/{event_id}/",
            "errorMessage": f"Flashscore has no match {event_id} (not charged).",
        })
        return None
    except (FlashscoreError, MatchPageError) as exc:
        state.record_failure(f"match {event_id}", exc)
        return None

    actor_input = state.actor_input
    tabs = set(page["tabs"])
    label = f"{page['homeTeam']} v {page['awayTeam']} ({event_id})"
    football = page["sportId"] == FOOTBALL

    async def feed(name: str) -> str:
        try:
            return await client.feed(f"{name}_1_{event_id}")
        except FlashscoreNotFoundError:
            return ""
        except FlashscoreError as exc:
            state.record_failure(f"{name} of {label}", exc)
            return ""

    async def graphql(query: str, **params: Any) -> dict[str, Any] | None:
        try:
            return await client.graphql(query, eventId=event_id, **params)
        except FlashscoreError as exc:
            state.record_failure(f"{query} of {label}", exc)
            return None

    async def nothing() -> None:
        return None

    want_stats = actor_input.wants("playerStats") and "PS" in tabs
    jobs = {
        "summary": feed("df_sui"),
        "statistics": feed("df_st") if actor_input.wants("statistics") and "ST" in tabs else nothing(),
        "lineups": graphql("dlie2", projectId=PROJECT_ID) if actor_input.wants_players and "LI" in tabs else nothing(),
        "pms": graphql("epmsd", providerId=7) if want_stats and football else nothing(),
        "pmsMeta": graphql("epmsse", projectId=PROJECT_ID) if want_stats and football else nothing(),
        "box": feed("df_psn") if want_stats and not football else nothing(),
        "missing": feed("df_scr") if actor_input.wants("missingPlayers") and "SCR" in tabs else nothing(),
        "momentum": graphql("mmts", providerId=7)
        if actor_input.wants("momentum") and tabs & {"MC", "MMT"}
        else nothing(),
        "commentary": feed("df_lc") if actor_input.wants("commentary") and "LC" in tabs else nothing(),
        "h2h": feed("df_hh") if actor_input.wants("headToHead") and "HH" in tabs else nothing(),
    }
    results = dict(zip(jobs, await asyncio.gather(*jobs.values())))

    stat_players = parse_player_stats(results["pms"], results["pmsMeta"]) if results["pms"] else []
    box_text = results["box"]
    if want_stats and not stat_players and box_text is None:
        box_text = await feed("df_psn")
    box_players = parse_box_score(box_text) if box_text else []

    summary = parse_summary(results["summary"] or "")
    lineups = parse_lineups(results["lineups"]) if results["lineups"] else {"home": None, "away": None}
    match_row = build_match_row(
        page,
        summary,
        statistics=parse_statistics(results["statistics"]) if results["statistics"] else None,
        lineups=lineups,
        missing=parse_missing_players(results["missing"]) if results["missing"] is not None else None,
        momentum=parse_momentum(results["momentum"]) if results["momentum"] else None,
        commentary=parse_commentary(results["commentary"]) if results["commentary"] is not None else None,
        h2h=parse_head_to_head(results["h2h"], page["homeTeam"]) if results["h2h"] is not None else None,
    )
    players = (
        build_player_rows(
            page,
            lineups,
            stat_players,
            box_players,
            with_lineups=actor_input.wants("lineups"),
            include_unused=actor_input.include_unused_substitutes,
        )
        if actor_input.wants_players
        else []
    )
    Actor.log.info(
        f"{page['homeTeam']} {page['homeScore']}-{page['awayScore']} {page['awayTeam']} "
        f"({page['competition']}): {len(players)} player row(s)."
    )
    return match_row, players


def build_match_row(
    page: dict[str, Any],
    summary: dict[str, Any],
    *,
    statistics: list[dict[str, Any]] | None,
    lineups: dict[str, Any],
    missing: list[dict[str, Any]] | None,
    momentum: list[dict[str, Any]] | None,
    commentary: list[dict[str, Any]] | None,
    h2h: dict[str, Any] | None,
) -> dict[str, Any]:
    periods = summary["periodScores"]
    info = summary["info"]
    home, away = lineups.get("home") or {}, lineups.get("away") or {}
    first_period = periods[0] if periods else None
    half_time = (
        f"{first_period['home']}-{first_period['away']}"
        if page["sport"] == "football" and first_period and first_period["home"] is not None
        else None
    )
    return {
        "recordType": "match",
        "eventId": page["eventId"],
        "url": page["url"],
        "sport": page["sport"],
        "country": page["country"],
        "competition": page["competition"],
        "competitionUrl": page["competitionUrl"],
        "round": page["round"],
        "startTime": page["startTime"],
        "status": page["status"],
        "decidedBy": page["decidedBy"],
        "homeTeam": page["homeTeam"],
        "homeTeamId": page["homeTeamId"],
        "homeTeamUrl": page["homeTeamUrl"],
        "awayTeam": page["awayTeam"],
        "awayTeamId": page["awayTeamId"],
        "awayTeamUrl": page["awayTeamUrl"],
        "homeScore": page["homeScore"],
        "awayScore": page["awayScore"],
        "halfTimeScore": half_time,
        "periodScores": periods or None,
        "duration": info.get("duration"),
        "venue": info.get("venue"),
        "city": info.get("city"),
        "attendance": info.get("attendance"),
        "capacity": info.get("capacity"),
        "referee": info.get("referee"),
        "refereeCountry": info.get("refereeCountry"),
        "referees": info.get("referees"),
        "homeFormation": home.get("formation"),
        "awayFormation": away.get("formation"),
        "homeCoach": home.get("coach"),
        "awayCoach": away.get("coach"),
        "homeAverageRating": home.get("averageRating"),
        "awayAverageRating": away.get("averageRating"),
        "incidents": summary["incidents"] or None,
        "statistics": statistics or None,
        "missingPlayers": missing or None,
        "momentum": momentum or None,
        "commentary": commentary or None,
        "headToHead": h2h if h2h and any(h2h.values()) else None,
    }


def build_player_rows(
    page: dict[str, Any],
    lineups: dict[str, Any],
    stat_players: list[dict[str, Any]],
    box_players: list[dict[str, Any]],
    *,
    with_lineups: bool,
    include_unused: bool,
) -> list[dict[str, Any]]:
    """Lineup entries merged with match stats, home side first, starters first.

    `played` is False only when that is known: the player has stats with zero
    minutes, or the lineup records substitutions and he was neither a starter
    nor brought on. Such rows are dropped unless `include_unused`.
    """
    teams = {
        "home": (page["homeTeam"], page["homeTeamId"]),
        "away": (page["awayTeam"], page["awayTeamId"]),
    }
    rows: dict[str, dict[str, Any]] = {}
    for side in ("home", "away"):
        for p in (lineups.get(side) or {}).get("players") or []:
            rows[p["playerId"]] = {"side": side, **p}
    subs_known = any(r.get("subbedInMinute") is not None for r in rows.values())

    stats_by_player: dict[str, dict[str, Any]] = {}
    for s in stat_players:
        pid = s["playerId"]
        side = "home" if s.get("teamId") == page["homeTeamId"] else "away" if s.get("teamId") == page["awayTeamId"] else None
        row = rows.setdefault(pid, {"side": side, "playerId": pid, "player": s.get("player"), "playerUrl": s.get("playerUrl")})
        row["position"] = s.get("position")
        row["isGoalkeeper"] = bool(row.get("isGoalkeeper") or s.get("isGoalkeeper"))
        if row.get("rating") is None:
            row["rating"] = s.get("rating")
        row["isBestRating"] = s.get("isBestRating")
        if row.get("starter") is None and s.get("starter") is not None:
            row["starter"] = s["starter"]
        stats_by_player[pid] = s["stats"]
    for b in box_players:
        pid = b["playerId"]
        if not pid:
            continue
        name = (b.get("teamName") or "").lower()
        side = "home" if name == (page["homeTeam"] or "").lower() else "away" if name == (page["awayTeam"] or "").lower() else None
        row = rows.setdefault(pid, {"side": side, "playerId": pid, "player": b.get("player"), "playerUrl": b.get("playerUrl")})
        if row.get("side") is None:
            row["side"] = side
        row.setdefault("nationality", b.get("nationality"))
        if b.get("boxScoreTable") == "goalkeeper":
            row["isGoalkeeper"] = True
        stats_by_player[pid] = b["stats"]

    if not with_lineups:
        rows = {pid: r for pid, r in rows.items() if pid in stats_by_player}

    context = {
        "eventId": page["eventId"],
        "matchUrl": page["url"],
        "sport": page["sport"],
        "competition": page["competition"],
        "round": page["round"],
        "startTime": page["startTime"],
    }
    out = []
    for pid, r in rows.items():
        side = r.get("side")
        stats = stats_by_player.get(pid)
        minutes = None
        if stats is not None:
            minutes = stats.get("minutesPlayed", stats.get("timeOnIce"))
        if stats is not None and minutes is not None:
            played: bool | None = minutes > 0
        elif r.get("starter") or r.get("subbedInMinute") is not None:
            played = True
        elif subs_known or stats_by_player:
            played = False
        else:
            played = None
        if played is False and not include_unused:
            continue
        team, team_id = teams.get(side, (None, None)) if side else (None, None)
        other = "away" if side == "home" else "home" if side == "away" else None
        opponent, opponent_id = teams[other] if other else (None, None)
        out.append({
            "recordType": "player",
            **context,
            "side": side,
            "team": team,
            "teamId": team_id,
            "opponent": opponent,
            "opponentId": opponent_id,
            "player": r.get("player"),
            "playerId": pid,
            "playerUrl": r.get("playerUrl"),
            "shirtNumber": r.get("shirtNumber"),
            "nationality": r.get("nationality"),
            "position": r.get("position"),
            "isGoalkeeper": r.get("isGoalkeeper"),
            "isCaptain": r.get("isCaptain"),
            "starter": r.get("starter"),
            "played": played,
            "lineupGroup": r.get("lineupGroup"),
            "subbedInMinute": r.get("subbedInMinute"),
            "subbedOutMinute": r.get("subbedOutMinute"),
            "rating": r.get("rating"),
            "isBestRating": r.get("isBestRating"),
            **(stats or {}),
        })
    order = {"home": 0, "away": 1, None: 2}
    out.sort(key=lambda r: (order.get(r["side"], 2), not r["starter"], r["shirtNumber"] is None))
    return out


# ------------------------------------------------------------------ reporting


async def _report(state: RunState) -> None:
    if state.pushed == 0 and state.not_found == 0 and state.errors:
        sample = "; ".join(state.errors[:3])
        await Actor.fail(
            status_message=(
                f"Could not scrape anything -- every Flashscore request failed "
                f"({len(state.errors)} error(s)). Sample: {sample}"
            )
        )
        return

    if state.escalations:
        Actor.log.info(f"Flashscore refused some requests; {state.escalations} proxy IP(s) were used.")

    charged = state.billing.charged
    summary = (
        f"Done. {state.matches_done} match(es) scraped: {charged[bill.MATCH_EVENT]} match row(s), "
        f"{charged[bill.PLAYER_EVENT]} player row(s)."
    )
    if state.billing.budget_exhausted:
        summary += " Stopped early: the run's maximum charge was reached."
    elif state.pushed >= state.actor_input.max_items:
        summary += f" Stopped at the maxItems cap of {state.actor_input.max_items}."
    if state.not_found:
        summary += f" {state.not_found} match(es)/page(s) not found on Flashscore (not charged)."
    if state.empty_sources:
        summary += f" {state.empty_sources} league/team URL(s) had no finished match to scrape; see the NO_MATCHES row(s)."
    if state.failed:
        shown = ", ".join(state.failed[:10])
        more = f" and {len(state.failed) - 10} more" if len(state.failed) > 10 else ""
        summary += f" {len(state.failed)} request(s) failed: {shown}{more}. Re-running usually succeeds."
    Actor.log.info(summary)
    await Actor.set_status_message(summary)


async def _report_bad_input(exc: Exception) -> None:
    message = str(exc)
    Actor.log.error(f"Invalid input: {message}")
    await Actor.push_data({"recordType": "error", "error": "INVALID_INPUT", "errorMessage": message})
    await Actor.exit(status_message=f"Invalid input: {message}")


async def _build_proxy_strategy(actor_input: ActorInput) -> tuple[str | None, Any]:
    """No proxy by default: Flashscore's hosts do not gate on IP."""
    proxy_input = actor_input.proxy_config_input
    if proxy_input and proxy_input.get("useApifyProxy"):
        configuration = await Actor.create_proxy_configuration(actor_proxy_input=proxy_input)
        if configuration:
            Actor.log.info("Using the proxy configuration from input.")
            return await configuration.new_url(), SessionRotator(configuration)
        Actor.log.warning("The proxy configuration from input could not be created; going direct.")
    return None, TieredProxyFallback()

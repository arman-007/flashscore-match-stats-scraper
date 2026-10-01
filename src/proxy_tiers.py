"""Cheapest-first proxy escalation -- a safety net, not the hot path.

Measured 2026-09-27 (docs/architecture.md §5): neither of Flashscore's data
hosts gates on IP reputation or TLS stack, and 120 back-to-back requests from
one IP drew no throttling. And unlike most odds sources, **the bookmaker
country is a query parameter**, not the caller's IP -- so a proxy buys no
extra coverage either. A normal run therefore never creates a proxy
configuration at all.

This exists for the day that changes. It is only ever called *after* a
request was actually refused (HTTP 403, or a dead connection on a proxy),
and it escalates the fleet-standard way:

1. **Datacenter** -- included in every Apify plan, the free tier included.
2. **Residential** -- a metered add-on most lower plans do not have.

Tiers that are not on the account are detected and skipped rather than
failing the run.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import Any

from apify import Actor

DATACENTER = "datacenter"
RESIDENTIAL = "residential"

DEFAULT_TIERS: tuple[str, ...] = (DATACENTER, RESIDENTIAL)

# A datacenter IP is free and each attempt is one small request, so its
# budget is generous; residential is metered at $8/GB and most plans lack it.
DEFAULT_IPS_PER_TIER: dict[str, int] = {DATACENTER: 8, RESIDENTIAL: 3}

# Used only for a tier that somehow has no entry above, so a custom `tiers`
# tuple can never silently get a budget of zero.
FALLBACK_IPS_PER_TIER = 4


def _session_id() -> str:
    return f"fsleague{random.randrange(1_000_000_000)}"


class SessionRotator:
    """Rotates the IP *within* one fixed proxy configuration.

    Used when the input pins a specific proxy setup: the user chose that
    configuration, so don't escalate away from it -- but a blocked IP is
    still worth swapping for another one out of the same pool.
    """

    def __init__(self, configuration: Any) -> None:
        self._configuration = configuration

    async def __call__(self) -> str | None:
        return await self._configuration.new_url(_session_id())


class TieredProxyFallback:
    """Hands out a fresh proxy URL each call, escalating tier as IPs run out.

    Returns `None` once every tier is exhausted or unavailable, which tells
    the caller to stop retrying and fail with a real error.
    """

    def __init__(
        self,
        *,
        tiers: tuple[str, ...] = DEFAULT_TIERS,
        ips_per_tier: int | Mapping[str, int] = DEFAULT_IPS_PER_TIER,
    ) -> None:
        self._tiers = tiers
        self._budgets: Mapping[str, int] = (
            dict.fromkeys(tiers, ips_per_tier) if isinstance(ips_per_tier, int) else ips_per_tier
        )
        self._index = 0
        self._configuration: Any = None
        self._ips_used = 0

    @property
    def current_tier(self) -> str | None:
        return self._tiers[self._index] if self._index < len(self._tiers) else None

    async def __call__(self) -> str | None:
        while self._index < len(self._tiers):
            tier = self._tiers[self._index]

            configuration = await self._ensure_configuration(tier)
            if configuration is None:
                self._advance(f"{tier} proxy is not available on this Apify account")
                continue

            budget = self._budgets.get(tier, FALLBACK_IPS_PER_TIER)
            if self._ips_used >= budget:
                self._advance(f"still blocked after {self._ips_used} {tier} IP(s)")
                continue

            self._ips_used += 1
            url = await configuration.new_url(_session_id())
            Actor.log.info(
                f"Retrying through a {tier} proxy IP ({self._ips_used}/{budget} for this tier)."
            )
            return url

        Actor.log.error(
            "Every proxy tier is exhausted or unavailable -- Flashscore is refusing this "
            "run's IPs and no further IP can be tried."
        )
        return None

    async def _ensure_configuration(self, tier: str) -> Any:
        if self._configuration is not None:
            return self._configuration

        groups = ["RESIDENTIAL"] if tier == RESIDENTIAL else None
        try:
            configuration = await Actor.create_proxy_configuration(groups=groups)
        except BaseException as exc:  # noqa: BLE001 - an optional tier must never crash the run
            Actor.log.warning(f"Could not set up the {tier} proxy tier: {exc!r}")
            return None

        if configuration is None:
            return None

        self._configuration = configuration
        Actor.log.info(f"Flashscore refused a direct request -- escalating to the {tier} proxy tier.")
        return configuration

    def _advance(self, reason: str) -> None:
        remaining = self._tiers[self._index + 1 :]
        next_step = f"trying {remaining[0]} next" if remaining else "no tiers left"
        Actor.log.warning(f"{reason} -- {next_step}.")
        self._index += 1
        self._configuration = None
        self._ips_used = 0

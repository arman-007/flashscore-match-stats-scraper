"""Pay-per-event billing: exactly one event per dataset row.

| Row (`recordType`) | Event |
| --- | --- |
| `match` (header, incidents, team statistics, extras) | `match` |
| `player` (one player's lineup entry and match stats) | `player-match` |

Each row is charged through `push_data(..., charged_event_name=...)`.

Two configuration traps (both overbill real customers):

1. **`apify-default-dataset-item` must NOT be enabled in Console.** The SDK
   charges synthetic events inside `push_data`, so every row would bill twice.
2. **Never call `Actor.charge('apify-actor-start')`.** The platform charges it.

Diagnostics (`INVALID_INPUT`, `MATCH_NOT_FOUND`, `SOURCE_NOT_FOUND`,
`NO_MATCHES`) are pushed unbilled.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from apify import Actor

MATCH_EVENT = "match"
PLAYER_EVENT = "player-match"


class Billing:
    def __init__(self, *, pay_per_event: bool) -> None:
        self._pay_per_event = pay_per_event
        self.budget_exhausted = False
        self.charged: Counter[str] = Counter()

    @classmethod
    async def create(cls) -> Billing:
        try:
            pricing = Actor.get_charging_manager().get_pricing_info()
            pay_per_event = bool(pricing.is_pay_per_event)
        except Exception as exc:  # noqa: BLE001 - never let billing setup kill a run
            Actor.log.warning(f"Could not read pricing info, assuming not monetized: {exc!r}")
            pay_per_event = False
        if pay_per_event:
            Actor.log.info(
                "Pay-per-event billing active: each match row and each player row is one charge. "
                "Invalid input and matches that cannot be found are never charged."
            )
        return cls(pay_per_event=pay_per_event)

    async def push(self, rows: list[dict[str, Any]], event: str) -> int:
        """Push rows under one event. Returns how many were stored; when the
        run's maximum charge is reached mid-batch, only the part that fits is."""
        if not rows:
            return 0
        if not self._pay_per_event:
            await Actor.push_data(rows)
            self.charged[event] += len(rows)
            return len(rows)

        result = await Actor.push_data(rows, charged_event_name=event)
        charged_count = getattr(result, "charged_count", None)
        stored = len(rows) if charged_count is None else int(charged_count)
        self.charged[event] += stored
        if getattr(result, "event_charge_limit_reached", False) or stored < len(rows):
            if not self.budget_exhausted:
                Actor.log.warning(
                    'Maximum charge for this run reached -- stopping gracefully. Raise "Maximum '
                    'charge per run" to collect more.'
                )
            self.budget_exhausted = True
        return stored

    @staticmethod
    async def push_unbilled(row: dict[str, Any]) -> None:
        await Actor.push_data(row)

"""Re-captures test/fixtures/: every page, feed and GraphQL response a full run makes.

Run: .venv/bin/python scripts/capture-fixtures.py (the test expectations then need
updating wherever Flashscore's data has moved on).
"""

import asyncio
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import main as m  # noqa: E402
from src.billing import Billing  # noqa: E402
from src.flashscore_client import FlashscoreClient  # noqa: E402
from src.input import INCLUDES, parse_input  # noqa: E402

OUT = ROOT / "test" / "fixtures"


class Log:
    def info(self, msg, *a, **k): print(msg)
    warning = error = exception = info


class FakeActor:
    log = Log()

    @staticmethod
    async def push_data(*_a, **_k): ...


class NoBilling:
    budget_exhausted = False

    def __init__(self):
        from collections import Counter
        self.charged = Counter()

    async def push(self, rows, event):
        self.charged[event] += len(rows)
        return len(rows)


def save(name: str, text: str) -> None:
    (OUT / f"{name}.gz").write_bytes(gzip.compress(text.encode("utf-8"), mtime=0))


class Recorder:
    def __init__(self, client):
        self.c = client

    async def page(self, path):
        text = await self.c.page(path)
        save("page" + path.replace("/", "_").rstrip("_"), text)
        return text

    async def feed(self, name):
        text = await self.c.feed(name)
        save(name, text)
        return text

    async def graphql(self, query, **params):
        data = await self.c.graphql(query, **params)
        save(f"gql_{query}_{params['eventId']}", json.dumps(data))
        return data


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    m.Actor = FakeActor
    import src.billing as b
    b.Actor = FakeActor
    raw = {
        "matchUrls": ["j52jHsN8", "dW4Uio9K", "pnOhtTOH", "MyyzpiYp"],
        "leagueUrls": ["https://www.flashscore.com/football/england/premier-league/"],
        "teamUrls": ["https://www.flashscore.com/team/new-york-knicks/WCNO4nbt/"],
        "maxMatchesPerSource": 45,
        "include": list(INCLUDES),
    }
    state = m.RunState(billing=NoBilling(), actor_input=parse_input(raw))
    async with FlashscoreClient() as client:
        rec = Recorder(client)
        for source in state.actor_input.sources:
            print(source.url, await m.discover(rec, state, source))
        for e in state.actor_input.event_ids:
            await m.scrape_match(rec, state, e)
    print("failed:", state.failed)


if __name__ == "__main__":
    asyncio.run(main())

# Publishing

Market, pricing, listing copy and the Console settings. The Console steps
are applied by the agent. The only step reserved for the owner is the final
**Publish** click, which also accepts the monetization terms.

---

## 1. Market (Apify Store, 2026-10-01)

| Actor | Price |
| --- | ---: |
| Flashscore match details (`omkar-cloud`) | $3 / 1K matches |
| Sofascore match analytics (this account) | $4 / 1K matches |
| FotMob match details | $10 / 1K matches |

None of the Flashscore Actors returns per-player match stats. The Sofascore
and FotMob ones are football first. This listing competes on:

1. **Player stats.** About 100 per footballer from Flashscore's own player
   stats, plus box scores for basketball and hockey, as one flat row per
   player.
2. **Every sport** on one schema.
3. **Discovery.** League, season and team URLs, with a date range.
4. **Price.** A match row costs the same as the cheapest Flashscore Actor.
   Player rows cost $0.20 / 1K, so a full match with ~32 players is under
   one cent.

---

## 2. Pricing — pay per event

| Event | Code name | Price | Primary |
| --- | --- | ---: | :-: |
| Actor start | `apify-actor-start` | $0.00005 | |
| Match | `match` | **$0.003** | ✅ |
| Player in a match | `player-match` | $0.0002 | |

**Do not enable `apify-default-dataset-item`**, because it would bill every
row twice. Leave "Pay per event + usage" off. Set the minimum spend to $0.01.

### Measured cost (local, 2026-10-01)

| Run | Rows | Time | Peak memory |
| --- | ---: | ---: | ---: |
| 4 matches (football, NHL, NBA, tennis), every `include` | 95 | 4 s | |
| Canary: 8 matches, every `include` | 205 | 9 s | |
| 20 Premier League 2024-25 matches, default `include` | 637 | 19 s | 100 MB |

No proxy was used. A whole season (380 matches) takes about 6 minutes, which
is about 0.05 compute units at 512 MB, against $3.50 of events. The margin is
above 95%.

---

## 3. Event titles and descriptions

| Event | Title | Description |
| --- | --- | --- |
| `match` | Match | One match: score, period scores, incidents, venue, referee, formations and coaches, plus the team statistics, missing players, momentum, commentary and head-to-head you include. |
| `player-match` | Player in a match | One player's lineup entry and match stats: shirt number, position, rating, minutes, substitutions, and up to ~100 stats (football) or the box score (basketball, hockey). |
| `apify-actor-start` | Actor start | Charged once when a run starts. The Actor runs at 512 MB, so this is under a tenth of a cent. |

---

## 4. Listing copy

| Field | Value |
| --- | --- |
| Unique name | `flashscore-match-stats-scraper` |
| Title (49) | `Flashscore Match Stats: Player Stats, Lineups, xG` |
| SEO title | `Flashscore Match Stats Scraper: Player Stats, xG` |
| Categories | `SPORTS`, `DEVELOPER_TOOLS`, `OTHER` |

**Description** (same text as `.actor/actor.json`):

```
Scrape Flashscore match details: 100 stats per footballer (xG, xA, passes, duels), box scores for basketball and hockey, lineups with ratings, team stats by period, incidents, referee and attendance. Whole leagues or teams in one run. No API key.
```

**SEO description**:

```
Flashscore match data: player stats (xG, xA, passes, ratings), lineups, team stats, goals, cards, referee and attendance for football, NBA, NHL and more.
```

---

## 5. Console settings (applied by the agent)

1. `defaultRunOptions` → 512 MB, 3600 s, build `latest`. A new Actor reads
   4096 MB, and the start event is billed per GB.
2. `exampleRunInput` → Brighton v Arsenal (`j52jHsN8`) with the default
   `include`.
3. Display information: logo, title, SEO title and descriptions from §4.
4. Monetization: the events from §2 and §3. `match` is primary.
5. Publish. **This click is the owner's.**

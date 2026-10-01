# Flashscore Match Stats: Player Stats, Lineups, xG

Scrape **everything Flashscore shows about a match**: the score and goal
times, team statistics with xG, lineups and formations, and about 100
stats per footballer (xG, xA, passes, duels, tackles, rating). It also does
box scores for basketball and hockey, plus missing players, the momentum
graph, the text commentary and head-to-head. Give it match URLs, or a
league or team URL to get their latest matches.

- **Player stats you can't get elsewhere for free.** Every footballer gets
  one row with about 100 numbers: xG, xA, xGOT, big chances, key passes,
  progressive passes and carries, duels, aerials, tackles, recoveries and
  Flashscore's rating. Keepers also get saves, goals prevented and claims.
- **Every sport on one schema.** Football, basketball, hockey, tennis,
  handball, American football and more. NBA box scores (points, rebounds,
  assists, shooting splits, plus-minus) and NHL skater and goalie lines
  arrive as player rows too.
- **Whole leagues and teams.** Paste a league or season URL, or a team URL,
  and get its latest finished matches. You can also filter by a date range.
- **Flat rows, ready for a spreadsheet or a model.** One row per match and
  one row per player per match.
- **No API key, no browser, no proxy.** 20 Premier League matches with all
  player stats take about 20 seconds.

---

## What can it scrape?

| Data | What you get |
| --- | --- |
| **Match** | Competition, round, kick-off, status, teams, final and half-time score, score per half, quarter, period or set (with tiebreaks), extra time or penalties, venue, city, attendance, capacity, referees, tennis match duration |
| **Incidents** | Goals with assists (and the second assist in hockey), cards, substitutions and penalties, with the minute, side and running score |
| **Team statistics** | Every stat Flashscore lists for the whole match and for each half, quarter, period or set: xG, possession, shots, big chances, passes, tackles, aces, rebounds... Each comes as a number, its display text and made/attempted where there is a ratio |
| **Lineups** | One row per player: shirt number, nationality, starter or substitute, position, captain, Flashscore rating, minute subbed on or off. Also formations, coaches and average team rating. Hockey lines are kept as `Line 1`–`Line 4` |
| **Player stats** | Football: about 100 stats per player. Basketball: points, rebounds, assists, minutes, field goals, 2s, 3s, free throws, plus-minus, steals, blocks, turnovers. Hockey: goals, assists, plus-minus, shots, hits, faceoffs, time on ice; goalies get saves, shots against and save % |
| **Missing players** | Injured and suspended players with the reason and how likely they are to play |
| **Momentum** | Football: Flashscore's minute-by-minute pressure graph (positive values = home pressure) |
| **Commentary** | The full text commentary, oldest first, with the minute and the event type |
| **Head-to-head** | Both teams' last matches with W/D/L, and their previous meetings |

What each sport has depends on Flashscore's coverage. Top football leagues
have everything. The NBA and NHL have lineups, box scores and team stats.
Tennis has set scores and match stats.

---

## Output example

A **match row** (shortened: the lists keep only their first entry):

```json
{
  "recordType": "match",
  "eventId": "j52jHsN8",
  "url": "https://www.flashscore.com/match/j52jHsN8/",
  "sport": "football",
  "country": "England",
  "competition": "Premier League",
  "round": "Round 5",
  "startTime": "2026-09-19T14:00:00Z",
  "status": "finished",
  "decidedBy": "regular-time",
  "homeTeam": "Brighton",
  "awayTeam": "Arsenal",
  "homeScore": 3,
  "awayScore": 0,
  "halfTimeScore": "2-0",
  "periodScores": [{ "period": "1st Half", "home": 2, "away": 0 }],
  "venue": "Amex Stadium",
  "city": "Brighton",
  "attendance": 31944,
  "referee": "England D.",
  "homeFormation": "4-2-3-1",
  "awayFormation": "4-2-3-1",
  "homeCoach": "Hurzeler F.",
  "awayCoach": "Arteta M.",
  "homeAverageRating": 7.3,
  "awayAverageRating": 6.3,
  "incidents": [{
    "period": "1st Half", "minute": "31'", "minuteValue": 31, "side": "home",
    "type": "Goal", "player": "Gross P.", "playerId": "trpxfbO3",
    "relatedPlayer": "Kostoulas C.", "relatedRole": "Assistance",
    "homeScoreAfter": 1, "awayScoreAfter": 0
  }],
  "statistics": [{
    "period": "Match", "section": "Top stats", "stat": "Expected goals (xG)",
    "home": 1.31, "away": 1.63, "homeDisplay": "1.31", "awayDisplay": "1.63"
  }],
  "missingPlayers": [{
    "side": "home", "player": "Azeez F.", "reason": "Abdominal strain",
    "availability": "There is some chance of playing."
  }],
  "momentum": [{ "minute": "1'", "period": "1st Half", "value": 0.0424 }],
  "commentary": [{ "minute": "31'", "type": "soccer-ball", "important": true,
    "text": "Pascal Gross (Brighton) makes himself some space on the edge of the penalty area and pulls the trigger..." }],
  "headToHead": { "meetings": [{ "startTime": "2026-09-19T14:00:00Z", "homeTeam": "Brighton",
    "awayTeam": "Arsenal", "homeScore": 3, "awayScore": 0, "winner": "home" }] }
}
```

A **player row** (football, shortened from about 100 stats):

```json
{
  "recordType": "player",
  "eventId": "j52jHsN8",
  "competition": "Premier League",
  "startTime": "2026-09-19T14:00:00Z",
  "side": "home",
  "team": "Brighton",
  "opponent": "Arsenal",
  "player": "Gross P.",
  "playerId": "trpxfbO3",
  "playerUrl": "https://www.flashscore.com/player/gross-pascal/trpxfbO3/",
  "shirtNumber": 13,
  "nationality": "Germany",
  "position": "Midfielder",
  "isCaptain": true,
  "starter": true,
  "played": true,
  "rating": 8.3,
  "isBestRating": true,
  "minutesPlayed": 90,
  "goals": 1,
  "assists": 1,
  "expectedGoals": 0.1074,
  "expectedAssists": 0.2506,
  "keyPasses": 2,
  "bigChancesCreated": 1,
  "passesTotal": 32,
  "passesAccuracy": 78.12,
  "progressivePassesTotal": 7,
  "duelsWon": 1,
  "tacklesWon": 1,
  "interceptions": 2,
  "touchesTotal": 45
}
```

A **basketball player row** has the box score instead:

```json
{
  "recordType": "player",
  "competition": "NBA - Play Offs",
  "round": "Final",
  "team": "New York Knicks",
  "opponent": "San Antonio Spurs",
  "player": "Bridges M.",
  "shirtNumber": 25,
  "starter": true,
  "rating": 7.2,
  "points": 14,
  "rebounds": 2,
  "assists": 4,
  "minutesPlayed": 38.57,
  "fieldGoalsMade": 5,
  "fieldGoalsAttempted": 10,
  "threePointersMade": 3,
  "threePointersAttempted": 7,
  "plusMinus": 6
}
```

Percentages are 0–100. Minutes are decimal (38.57 = 38:34).

---

## How to use it

Give it match URLs, league URLs or team URLs, in any combination.

**One match with everything:**

```json
{ "matchUrls": ["https://www.flashscore.com/match/j52jHsN8/"],
  "include": ["statistics", "lineups", "playerStats", "missingPlayers",
              "momentum", "commentary", "headToHead"] }
```

**The latest 10 Premier League matches with player stats** (the default):

```json
{ "leagueUrls": ["https://www.flashscore.com/football/england/premier-league/"] }
```

**A whole past season for a model:**

```json
{ "leagueUrls": ["https://www.flashscore.com/football/england/premier-league-2024-2025/"],
  "maxMatchesPerSource": 0 }
```

**A team's matches in a date range, across all competitions:**

```json
{ "teamUrls": ["https://www.flashscore.com/team/new-york-knicks/WCNO4nbt/"],
  "maxMatchesPerSource": 0, "dateFrom": "2026-03-01", "dateTo": "2026-03-31" }
```

**Team statistics only, no player rows:**

```json
{ "leagueUrls": ["https://www.flashscore.com/basketball/usa/nba-2025-2026/"],
  "include": ["statistics"], "maxMatchesPerSource": 50 }
```

### Tips

- **Any Flashscore URL form works.** That includes `/match/j52jHsN8/`, the
  long `/match/football/brighton-.../arsenal-.../?mid=j52jHsN8` form, any
  Flashscore country site or a bare 8-character id. A URL pasted into the
  wrong field is routed by what it is.
- **Leagues and teams give finished matches only**, newest first.
  `maxMatchesPerSource` (default 10) caps each URL. Set it to `0` for every
  match, or use `dateFrom`/`dateTo`. A league URL without a season is the
  current season. Between seasons, use a past season's URL such as
  `.../nba-2025-2026/`.
- **Player rows** are the lineup merged with the stats. Unused substitutes
  are left out (and not charged) unless you turn on
  `includeUnusedSubstitutes`.
- **`include` decides what you pay for.** Without `lineups` and
  `playerStats` there are no player rows, only match rows.
- **Head-to-head is today's view.** For an old match, Flashscore's "last
  matches" are the teams' latest matches, not their form before that game.
- An unknown match or page returns a free `MATCH_NOT_FOUND` /
  `SOURCE_NOT_FOUND` row.

---

## Pricing

Pay per event. You are charged only for rows you receive:

| Row | Price |
| --- | ---: |
| Match (score, incidents, team stats, officials and whatever else you include) | $0.003 |
| Player (one player's lineup entry and stats in one match) | $0.0002 |

Some examples:

- A football match with player stats (1 match + ~32 players) costs about
  **$0.009**.
- An NBA game with box scores (1 match + ~21 players) costs about
  **$0.007**.
- A whole Premier League season (380 matches, ~12,000 player rows) costs
  about **$3.50**. With team statistics only, it costs **$1.14**.

Invalid input and unknown matches or pages are never charged. The run stops
cleanly when it reaches your maximum charge.

---

## FAQ

**Is it legal to scrape Flashscore?** This Actor only collects publicly
visible sports data, without logging in. You are responsible for how you use
the data. Check Flashscore's terms and your local laws before using it
commercially.

**Why do some matches have no player stats or lineups?** Flashscore only
has them for competitions it covers in depth. Every match still gets its
score, period scores, incidents and whatever team statistics exist.

**Can I get live matches?** Yes. A live match URL returns the current
state, with `status: "live"`. League and team URLs return finished matches
only.

**Why is a late substitute's rating empty?** Flashscore doesn't rate
players who were on for only a few minutes.

**Can I get odds, standings or whole player careers?** These are separate
Actors on this account: Flashscore Odds, Flashscore League Archive and
Flashscore Teams & Players.

<!-- flashscore-links -->

---

## Ready-made examples

Open one, press **Try for free**, and change the input to your own:

- [Get Premier League player stats with xG](https://apify.com/incognito_mode/flashscore-match-stats-scraper/examples/premier-league-player-xg-stats)
- [Get Champions League match statistics](https://apify.com/incognito_mode/flashscore-match-stats-scraper/examples/champions-league-match-statistics)
- [Get NBA box scores for every player](https://apify.com/incognito_mode/flashscore-match-stats-scraper/examples/nba-box-scores)
- [Get full match stats for a team's last 5 games](https://apify.com/incognito_mode/flashscore-match-stats-scraper/examples/team-last-matches-full-stats)

## More Flashscore Actors

Same data source, same flat rows and pay-per-result pricing:

- [Flashscore Betting Odds Scraper](https://apify.com/incognito_mode/flashscore-odds-scraper) — pre-match odds from 100+ bookmakers with opening prices, plus outright winner odds
- [Flashscore Odds Movement Tracker](https://apify.com/incognito_mode/flashscore-odds-tracker) — line movement and exact closing lines on a schedule
- [Flashscore League Archive](https://apify.com/incognito_mode/flashscore-league-archive-scraper) — every season's results, tables and top scorers, back to 1901
- [Flashscore Teams & Players](https://apify.com/incognito_mode/flashscore-team-player-scraper) — squads, transfers with fees, market values and player careers
- [Flashscore Tennis Scraper](https://apify.com/incognito_mode/flashscore-tennis-scraper) — ATP/WTA results, serve stats, point-by-point, draws and rankings

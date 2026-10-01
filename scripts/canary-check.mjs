/**
 * Asserts that a canary run actually pulled complete Flashscore match data.
 *
 * The unit tests run against captured pages, feeds and GraphQL responses, so
 * they stay green through a Flashscore change -- the failure that matters
 * most, because every field depends on an inline JSON object on the match
 * page, undocumented `¬`/`÷` text feeds, persisted GraphQL query hashes and
 * the `x-fsign` header staying put. This script reads a real run's dataset and
 * fails when coverage collapses.
 *
 * The canary input is Brighton 3-0 Arsenal (every football source: summary,
 * statistics, lineups, player stats, momentum, commentary, missing players,
 * head-to-head), the 2026 NBA final (basketball box score) and the Knicks'
 * matches of 2026-03-01..10 (team page, `pr_` paging, date filter). All are
 * finished, so the expected values never change.
 *
 * Usage:  apify datasets get-items <id> --format json | node scripts/canary-check.mjs
 */

const num = (v) => typeof v === 'number';
const id8 = (v) => /^[A-Za-z0-9]{8}$/.test(v ?? '');
const match = (i) => i.recordType === 'match';
const player = (i) => i.recordType === 'player';
const footballPlayer = (i) => player(i) && i.sport === 'football';
const basketballPlayer = (i) => player(i) && i.sport === 'basketball';
const len = (v) => (Array.isArray(v) ? v.length : 0);

const CHECKS = [
    { name: 'match ids / teams / score', scope: match, min: 1, test: (i) => id8(i.eventId) && Boolean(i.homeTeam && i.awayTeam) && num(i.homeScore) && num(i.awayScore) },
    { name: 'match competition / start', scope: match, min: 1, test: (i) => Boolean(i.competition) && /^\d{4}-\d{2}-\d{2}T/.test(i.startTime ?? '') },
    { name: 'match period scores', scope: match, min: 1, test: (i) => len(i.periodScores) >= 2 },
    { name: 'match venue / referee', scope: match, min: 1, test: (i) => Boolean(i.venue && i.referee) },
    { name: 'match team statistics', scope: match, min: 1, test: (i) => len(i.statistics) >= 20 },
    { name: 'match coaches (lineups)', scope: match, min: 1, test: (i) => Boolean(i.homeCoach && i.awayCoach) },
    { name: 'match head-to-head', scope: match, min: 1, test: (i) => len(i.headToHead?.meetings) > 0 },
    { name: 'player id / url / team', scope: player, min: 1, test: (i) => id8(i.playerId) && (i.playerUrl ?? '').includes('/player/') && ['home', 'away'].includes(i.side) },
    { name: 'player shirt number', scope: player, min: 0.95, test: (i) => num(i.shirtNumber) },
    { name: 'football xG', scope: footballPlayer, min: 0.95, test: (i) => num(i.expectedGoals) },
    // Flashscore rates nobody who played under ~10 minutes.
    { name: 'football rating (15+ minutes)', scope: (i) => footballPlayer(i) && i.minutesPlayed >= 15, min: 1, test: (i) => num(i.rating) },
    { name: 'football minutes', scope: footballPlayer, min: 0.95, test: (i) => num(i.minutesPlayed) && i.minutesPlayed > 0 },
    { name: 'basketball points / minutes', scope: basketballPlayer, min: 0.95, test: (i) => num(i.points) && num(i.minutesPlayed) },
    { name: 'no error rows', min: 1, test: (i) => !i.error },
];

const bha = (all) => all.find((r) => match(r) && r.eventId === 'j52jHsN8') ?? {};

const RUN_CHECKS = [
    {
        name: 'Brighton 3-0 Arsenal header',
        test: (all) => {
            const m = bha(all);
            return m.homeScore === 3 && m.awayScore === 0 && m.halfTimeScore === '2-0' && m.venue === 'Amex Stadium' && m.attendance === 31944;
        },
        why: 'the match page window.environment or the df_sui_ info block changed',
    },
    {
        name: 'three goals with assists',
        test: (all) => {
            const goals = (bha(all).incidents ?? []).filter((i) => i.type === 'Goal');
            return goals.length === 3 && goals.every((g) => g.player && g.relatedPlayer && num(g.homeScoreAfter));
        },
        why: 'df_sui_ incident records (III/IE/IF/IK) changed',
    },
    {
        name: 'xG in team statistics',
        test: (all) => (bha(all).statistics ?? []).some((s) => s.stat === 'Expected goals (xG)' && s.home === 1.31 && s.away === 1.63),
        why: 'df_st_ (SE/SG/SH/SI) changed',
    },
    {
        name: 'formations, momentum, commentary, missing',
        test: (all) => {
            const m = bha(all);
            return m.homeFormation === '4-2-3-1' && len(m.momentum) > 80 && len(m.commentary) > 50 && len(m.missingPlayers) > 0;
        },
        why: 'the dlie2 or mmts GraphQL queries, df_lc_ or df_scr_ changed',
    },
    {
        name: '30+ football player rows with 80+ stats',
        test: (all) => {
            const rows = all.filter(footballPlayer);
            return rows.length >= 30 && rows.some((r) => Object.keys(r).length > 100);
        },
        why: 'the epmsd/epmsse player-stats GraphQL queries changed',
    },
    {
        name: 'NBA final box score',
        test: (all) => all.filter((r) => basketballPlayer(r) && r.eventId === 'pnOhtTOH').length >= 18,
        why: 'df_psn_ (box score) changed',
    },
    {
        name: 'Knicks matches 1-10 March (pr_ paging)',
        test: (all) => {
            const ms = all.filter((r) => match(r) && r.eventId !== 'j52jHsN8' && r.eventId !== 'pnOhtTOH');
            const inRange = ms.every((r) => r.startTime >= '2026-03-01' && r.startTime < '2026-03-11');
            return ms.length >= 4 && inRange && new Set(ms.map((r) => r.eventId)).size === ms.length;
        },
        why: 'the team page results list, the pr_ continuation feed or the date filter broke',
    },
];

function readStdin() {
    return new Promise((resolve, reject) => {
        let raw = '';
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', (chunk) => { raw += chunk; });
        process.stdin.on('end', () => resolve(raw));
        process.stdin.on('error', reject);
    });
}

const raw = await readStdin();

// `apify datasets get-items` prints its content type on stderr today, but a
// future version putting it on stdout would otherwise turn every canary red
// for the wrong reason.
const firstBracket = raw.indexOf('[');
const payload = firstBracket > 0 ? raw.slice(firstBracket) : raw;

let items;
try {
    items = JSON.parse(payload);
} catch (error) {
    console.error(`Could not parse the dataset as JSON: ${error.message}`);
    console.error(`First 200 characters received: ${raw.slice(0, 200)}`);
    process.exit(1);
}

if (!Array.isArray(items)) {
    console.error('Expected a JSON array of dataset items.');
    process.exit(1);
}

const failures = [];
const rows = [];

if (items.length === 0) {
    failures.push('Scraped 0 items.');
}

for (const check of items.length === 0 ? [] : CHECKS) {
    const scoped = check.scope ? items.filter(check.scope) : items;
    if (scoped.length === 0) {
        rows.push({ name: check.name, hits: 0, total: 0, min: check.min, ok: false });
        failures.push(`${check.name}: no rows of that kind were scraped at all.`);
        continue;
    }
    const hits = scoped.filter((item) => {
        try {
            return check.test(item);
        } catch {
            return false;
        }
    }).length;
    const ratio = hits / scoped.length;
    const ok = ratio >= check.min;
    rows.push({ name: check.name, hits, total: scoped.length, min: check.min, ok });
    if (!ok) {
        failures.push(
            `${check.name}: ${hits}/${scoped.length} items populated `
            + `(${Math.round(ratio * 100)}%), below the ${Math.round(check.min * 100)}% floor.`,
        );
    }
}

for (const check of items.length === 0 ? [] : RUN_CHECKS) {
    let ok = false;
    try {
        ok = check.test(items);
    } catch {
        ok = false;
    }
    rows.push({ name: check.name, hits: ok ? 1 : 0, total: 1, min: 1, ok });
    if (!ok) failures.push(`${check.name}: ${check.why}.`);
}

const table = rows
    .map((r) => `  ${r.ok ? 'ok  ' : 'FAIL'} ${r.name.padEnd(42)} ${r.hits}/${r.total}`
        + ` (floor ${Math.round(r.min * 100)}%)`)
    .join('\n');

console.log(`Canary dataset: ${items.length} item(s)\n${table}`);

if (process.env.GITHUB_STEP_SUMMARY) {
    const { appendFileSync } = await import('node:fs');
    const md = [
        `### Canary — ${items.length} item(s), ${failures.length ? '❌ failed' : '✅ healthy'}`,
        '',
        '| Check | Passed | Floor |',
        '|---|---|---|',
        ...rows.map((r) => `| ${r.ok ? '✅' : '❌'} \`${r.name}\` | ${r.hits}/${r.total} |`
            + ` ${Math.round(r.min * 100)}% |`),
        '',
    ].join('\n');
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, md);
}

if (failures.length) {
    console.error('\nCanary failed — Flashscore has probably changed the match page, a feed key, '
        + 'a GraphQL query hash or the feed sign:\n'
        + failures.map((f) => `  - ${f}`).join('\n'));
    process.exit(1);
}

console.log('\nCanary passed: the deployed build still pulls complete Flashscore match data.');

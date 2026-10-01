# CI/CD

| Trigger | Workflow | Result |
| --- | --- | --- |
| Pull request to `main` / `production` | `ci.yml` | tests + schema validation |
| Push to `main` | `beta.yml` | tests, then Apify build tagged `beta` |
| Push to `production` | `deploy.yml` | tests, then Apify build tagged `latest` (what users run) |
| Wednesdays 08:27 UTC | `canary.yml` | runs `latest` on live Flashscore and checks three finished matches plus a team's March matches |

All four workflows need one repository secret, `APIFY_TOKEN`. Any step that
drives the CLI logs in with `apify/setup-apify-cli-action@v1`, because the
CLI ignores the environment variable.

## Tests

`python -m pytest -q` runs against captured responses in `test/fixtures/`
(gzipped, recorded by `scripts/capture-fixtures.py`):

- four match pages with every feed and GraphQL response a full run makes:
  Brighton 3-0 Arsenal (football, every tab), Philadelphia 0-7 Pittsburgh
  (NHL box score and lines), the 2026 NBA final (basketball box score) and
  the 2026 US Open final (tennis: no lineups, tiebreaks, match duration);
- the Premier League page and the Knicks team page, plus the Knicks' first
  `pr_` continuation page.

They stay green through a Flashscore change. The canary is the check that
catches one.

`test_schemas.py` and `test_main.py` push every row shape the Actor can emit
through the dataset schema. The platform rejects a `null` in a non-nullable
field or a float in an integer field, and local runs never validate against
that schema. `scripts/make-dataset-schema.py` writes the schema; edit the
field list there, not the JSON.

## Canary

`scripts/canary-input.json` scrapes Brighton 3-0 Arsenal and the NBA final
with every `include`, and the Knicks' matches of 1-10 March 2026 from the
team page (which needs `pr_` paging and the date filter). Every match is
finished, so `scripts/canary-check.mjs` asserts exact values (3-0, 2-0 at
half time, 31,944 at the Amex, xG 1.31 v 1.63, three goals with assists) as
well as coverage floors. On failure, the workflow opens (or comments on) a
`canary` issue.

| Symptom | Likely cause |
| --- | --- |
| header / score checks red | the match page's `window.environment` JSON changed |
| incident or venue checks red | `df_sui_` changed (III/IE/IK incidents, MIT/MIV info block) |
| team statistics red | `df_st_` changed (SE/SG/SH/SI) |
| football player rows red | the `epmsd` / `epmsse` GraphQL hashes or fields changed |
| formations, coaches, momentum red | the `dlie2` / `mmts` GraphQL hashes changed |
| NBA box score red | `df_psn_` changed |
| Knicks March matches red | the team page results list or the `pr_` feed name changed |
| everything red, 401s in the log | `x-fsign` rotated and the refresh failed |

## The vendored push action

`.github/actions/push-actor/` wraps `apify push --force`. Without `--force`,
a `main` build followed by a `production` build refuses with "modified there
since modified locally". The action's header explains this in full.

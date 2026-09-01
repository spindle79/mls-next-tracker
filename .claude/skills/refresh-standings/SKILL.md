---
name: refresh-standings
description: Pull the latest MLS NEXT Academy standings and schedule from the MLS Assist league viewer, rebuild data.json with predictions, and re-shard for the Next.js app. Use when the user says refresh, update standings, pull latest scores, re-scrape, or rebuild the tracker data.
---

# Refresh Standings

Runs the full data pipeline: fetch the season feeds, rebuild the week-by-week JSON with
predictions, re-embed the standalone page, and write the per-division shards the app reads.

Working directory: `/Users/adam.harris/Documents/repos/mls`

## The source

The season lives on the **MLS Assist league viewer**
(`https://mls-assist.theintelligenceplatform.com`), a static-JSON SPA. The whole season
ships in two unfiltered files:

| Feed                                | Contents                                         |
| ----------------------------------- | ------------------------------------------------ |
| `/data/schedule/<season-key>.json`  | every match, whole season (~12.7 MB)             |
| `/data/standings/<season-key>.json` | position + tiebreaker values per squad (~1.3 MB) |

Current season key: `mls-next-2-academy-division-26-27`.

**There is no browser automation and no pagination.** A viewer URL's `squads` / `clubs` /
`from` / `to` params and its pager are client-side filters only — they do not narrow what the
feed returns. Never drive this with Playwright; it is two HTTP GETs.

Coverage: 6 age groups (U13, U14, U15, U16, U17, U19) × 20 regional divisions = **120
divisions, ~1,612 teams, ~13,705 matches**.

> modular11.com is retired. It still answers on the old URLs but every standings endpoint
> renders "There are no teams" with zero rows. `scrape.py` and `parse_standings.py` target it
> and are dead code kept for reference — do not use them.

## Step 1: Fetch and build

Use the venv Python — `scrape_academy.py` needs `requests`:

```bash
cd /Users/adam.harris/Documents/repos/mls
.venv/bin/python scrape_academy.py                 # all six age groups, seconds
```

Narrow to one age group with `--ages U14` (or `--ages U13,U14`) when iterating. Writes
`scraped_academy.json`. Override the season with `--season-key` at season rollover.

Then rebuild and re-shard in one shot:

```bash
./refresh.sh --from-academy-scrape
```

That runs `build_data.py --from-academy-scrape` → `data.json`, re-embeds the default
division into `public/index.html`, and runs `scripts/export-divisions.mjs` to write
`public/data.json` + `public/divisions/<id>.json`.

`build_data.py` only needs the standard library, so `refresh.sh` calling plain `python3` is
fine. Only the scrape step needs the venv.

## Step 2: Verify

Check all three numbers — a mismatch means something silently dropped:

```bash
# expect: 6 age groups, 120 divisions, 1612 team rows (scrape summary)
# expect: Divisions: 120 (build output)
ls public/divisions | wc -l          # expect 120
```

**`export-divisions.mjs` does not prune stale shards.** If division ids change (a season
rollover, or an id-format change), old files linger and the app can serve outdated data.
After any id change, delete shards not in the catalog:

```bash
.venv/bin/python - <<'PY'
import json, os, pathlib
keep = {e["id"] + ".json" for e in json.load(open("public/data.json"))["division_catalog"]}
d = pathlib.Path("public/divisions")
for f in sorted(set(os.listdir(d)) - keep):
    (d / f).unlink(); print("removed stale", f)
PY
```

## Step 3: Report

- Age groups, divisions, and team rows from the scrape summary
- Total matches and how many are played vs unplayed
- Any squads skipped for having no standings row (the scraper prints them by name)
- Any stat-mismatch warnings (should be zero)
- **San Francisco Glens SC** — current rank, points, record. They are in **Northern
  California Redwood** at all six age groups. The default division is
  `academy-u13-northern-california-redwood`.

## Early-season caveat

`predict_single_match` returns nothing when either club has `MP == 0`, so a division
produces **no predictions until its teams have played**. Early in a season most divisions
project as their current table and the Predictions tab is empty. This is by design, not a
scrape failure — check played-match counts before investigating.

## Troubleshooting

**A feed returns ~631 bytes of HTML instead of JSON.** The SPA serves `index.html` for any
unknown path rather than a 404, so this means the season key is wrong. The scraper detects
this and tells you to check `--season-key`.

**Division names look wrong.** Take names from the _standings_ feed, never the schedule feed.
The schedule feed's own `division` field disagrees with it — it says "South California" for
"Southern California" and files a block of "North" fixtures under "Great Lakes North". The
scraper joins the two feeds on `squad_id` (stable, no collisions) and ignores that field.

**A club's stats look short.** Interleague fixtures — both clubs in different brackets — are
excluded on purpose, matching what the published standings do. Including them would break
agreement with the feed's own MP and goal totals.

**Stat-mismatch warnings appear.** The scraper cross-checks each squad's feed `matches_played`
against the played matches it found. Warnings mean the feeds disagree with each other; report
them rather than ignoring, since the derived GF/GA/GD may be off.

**A team name changed.** Names drift between platforms and seasons — the focus club is
`San Francisco Glens SC` here and was `San Francisco Glens` on modular11. A renamed focus team
silently stops matching. Grep for the old name in `build_data.py` (the `GLENS` constant) and
`lib/tracker/logic.ts` (`GLENS_FOCUS`).

## Related

- `.claude/skills/game-predictions` — analyzing the data once it is built
- `docs/plans/last-season-prior.md` — plan for weighting prior-season results

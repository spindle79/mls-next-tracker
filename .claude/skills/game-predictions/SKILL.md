---
name: game-predictions
description: Analyze MLS NEXT Academy division data to answer prediction questions — paths to top 6, must-win games, opponent strength, best/worst case scenarios — and tune the prediction model. Use when the user asks about game predictions, chances of making top 6, which games matter most, what record a team needs, comparing teams, adjusting prediction weights, or any strategic "what do we need to do" question about the season. Also trigger for scenario analysis beyond what the What If tab provides.
---

# Game Predictions & Season Analysis

Strategic questions about an MLS NEXT Academy division — predictions, paths to top 6,
must-win games, and tuning the prediction model.

Working directory: `/Users/adam.harris/Documents/repos/mls`

## Context

The tracker covers **120 divisions** (6 age groups × 20 regional divisions, ~1,612 teams),
not a single division. Always establish _which_ division a question is about before
analyzing.

The focus club is **`San Francisco Glens SC`** — match this string exactly; the trailing `SC`
is part of the name in the current feeds. They are in **Northern California Redwood** at all
six age groups. The goal is a **top 6** finish (`target_rank: 6` in each division bundle).

Key files:

| Path                         | What it is                                             |
| ---------------------------- | ------------------------------------------------------ |
| `public/divisions/<id>.json` | **Read this** — one division's full bundle             |
| `public/data.json`           | Full multi-division file (~19 MB) + `division_catalog` |
| `data.json`                  | Same, repo root, pre-shard (gitignored)                |
| `build_data.py`              | Prediction engine + `DEFAULT_PREDICTION_PARAMS`        |
| `scraped_academy.json`       | Raw scrape bundle (gitignored)                         |
| `public/index.html`          | Legacy standalone page with one embedded division      |

Division ids are `academy-<age>-<division>`, e.g. `academy-u14-northern-california-redwood`.
List them from `public/data.json`'s `division_catalog` (id, age_label, division, league).

## Reading the data — do not read data.json whole

`data.json` is ~19 MB. Read the **shard** for the division in question instead:

```bash
.venv/bin/python -c "
import json
d = json.load(open('public/divisions/academy-u14-northern-california-redwood.json'))
print(d['age_label'], d['division'], '| teams:', len(d['team_names']), '| preds:', len(d['predictions']))
"
```

Each shard contains:

- `current_standings` — `rank`, `team`, `PTS`, `PPM`, `MP`, `W`/`L`/`T`, `GF`/`GA`/`GD`.
  **No home/away splits** — these rows come straight from the standings feed.
- `predictions` — remaining unplayed games. Keys: `match_id`, `date`, `venue`, `home`,
  `away`, `home_win_prob`, `draw_prob`, `away_win_prob`, `predicted_outcome`,
  `est_home_goals`, `est_away_goals`, `home_strength`, `away_strength`
- `projected_final_standings` — where each team lands if predictions hold. Same keys as
  above **plus** `home_MP`/`home_GF`/`home_GA` and `away_MP`/`away_GF`/`away_GA`.
- `head_to_head` — `h2h[teamA][teamB]` = {W, L, T, GF, GA}
- `weekly` — per-week snapshots: `week_start`, `week_end`, `games`, `standings` (the table
  after that week, with the home/away splits)
- `retro_predictions` — walk-forward predictions for weeks already played
- `id`, `league`, `age_label`, `division`, `highlight_team`, `target_rank`, `team_names`

Two shape gotchas:

- The probability keys are `home_win_prob` / `draw_prob` / `away_win_prob` — **not**
  `p_home_win`.
- The full MLS NEXT tiebreaker chain needs away/home GD and GF per match, which
  `current_standings` does not carry. To break ties as the league does, use the latest
  `weekly[-1].standings` or `projected_final_standings`, which do.

## Early-season caveat — check this first

`predict_single_match` returns `None` when **either** club has `MP == 0`:

```python
if home_s['MP'] == 0 or away_s['MP'] == 0:
    return None
```

So a division has **no predictions until its teams have played**, and `projected_final_standings`
equals the current table. Early in a season most divisions are in exactly this state — as of
the 26/27 opening, 37 of 13,705 matches were complete.

Before answering any "what do we need" question, check `len(predictions)` and the teams' `MP`.
If predictions are empty, say so plainly and answer from the schedule and current table rather
than inventing projections. Do not report a projection as a model output when it is just the
current standings.

`docs/plans/last-season-prior.md` is the plan to fix this by seeding a prior from last season.

## How the prediction model works

`predict_single_match()` builds a **composite strength** per team:

1. **PPM and GD/match** — shrunk toward league averages with pseudo-count
   `shrink_pseudo_mp` (damps early-season noise).
2. **Weights** — with common opponents: 40% PPM, 25% GD (+3 shift), 20% H2H, 15%
   common-opponent PPM; without: 50% / 30% / 20%.
3. **Head-to-head** — scaled by `min(1, meetings / h2h_full_games)` so one fluke game cannot
   dominate.
4. **Home edge** — `home_strength_bonus` added before comparing sides.

Probabilities: draw mass is `draw_floor` + (`draw_cap` − `draw_floor`) × exp(−`draw_decay` ×
margin²); non-draw mass splits by a sigmoid on strength margin (`margin_split_scale`). Raw
expected goals drive a closeness blend toward a higher-draw symmetric mix
(`scoreline_blend_max`, `scoreline_target_draw`) using the gap on the half-goal grid
(`SCORELINE_BLEND_GAP_UNITS`). Displayed/simulated goals go through
`round_predicted_scoreline`: nearest 0.5, then nearest whole goal, half-up (2.1 vs 2.4 → 2 vs
3). A `prob_floor` on all three outcomes improves calibration. The reported pick is the argmax
of the final triple.

Goal model: opponent-adjusted Maher-style attack × defense ratings (`opp_adj_iters`,
`opp_adj_blend`) blended with shrunk GF/GA lambdas (`goal_shrink_pseudo_mp`,
`home_goal_mult`).

## Answering prediction questions

### "Can we make top 6?" / "What do we need?"

1. Load the division shard; find the focus team's rank and the 6th-place team's points.
2. Filter `predictions` where `home` or `away` is the focus team → remaining games.
3. Max possible points = current PTS + 3 × remaining games.
4. Compare against `projected_final_standings` for teams currently ranked 4–8.
5. State how many wins are needed and which opponents are realistically beatable.

Ranking is by **PPM**, not raw points, with MLS NEXT tiebreakers (`rank_teams` in
`build_data.py`: H2H only when exactly two clubs are tied on PPM, then wins/MP, GD/MP, GF/MP,
away GD/MP, away GF/MP, home GD/MP, home GF/MP). Teams can have different MP, so raw-points
comparisons mislead — use PPM.

### "Which games matter most?"

Rank the focus team's remaining games by opponent proximity in the table: opponents ranked
just above and below are worth the most, bottom-table games are must-not-lose, top-3 games are
upside. Cite each opponent's current and projected rank.

### "What's our best/worst case?"

Use the What If simulation helpers rather than re-deriving: `whatifOptimizeForFocus` in
`lib/tracker/logic.ts` does exactly this in the UI. For analysis, set every focus-team game to
a win (then a loss) and re-rank with the same tiebreakers. Report the range and flag which end
is realistic.

### Presenting results

```
## Glens Path to Top 6 — U14 Northern California Redwood

**Current:** #9, 0 PTS (0W-0L-0T), 3 scheduled games
**6th place:** <team>, <pts> PTS
**Predictions available:** 0 of 3 (no team has played yet)

| Date | Opponent | Opp Rank | Prediction | Win Prob |
| ---- | -------- | -------- | ---------- | -------- |
```

Always name the division and age group — "#9" is meaningless across 120 divisions.

## Backtesting and tuning — currently broken

`backtest_predictions.py` and `tune_prediction_params.py` **do not run against the current
pipeline.** They read legacy single-division inputs that nothing writes any more:

- `--from-scrape` → `scraped_matches.json` + `scraped_standings.json`
- no flag → `page1.html` / `page2.html`

Running it today fails with `Missing input file: .../scraped_matches.json`.

Do not hand the user one of these commands as if it works. Wiring them to
`scraped_academy.json` (per-division, or pooled across divisions) is a real task worth doing
before any tuning claim is made — see P5 in `docs/plans/last-season-prior.md`, which also
notes that with only tens of completed matches there is nothing meaningful to tune against
yet.

## Tuning the prediction model

Once the backtest is wired up:

1. Prefer editing `DEFAULT_PREDICTION_PARAMS` in `build_data.py` (documented keys) over
   changing structure.
2. For new factors, edit `predict_single_match()`; keep the composite weights summing to 1.0.
3. Explain the tradeoffs: higher shrink → more regression to the mean early; higher
   `home_strength_bonus` → more home wins; higher draw params → more draws, which often
   improves log loss when draws are undercalled.
4. Rebuild and re-shard with `./refresh.sh --from-academy-scrape`, then report the
   before/after impact on the focus team's projected rank.

Never edit `data.json`, `public/data.json`, or `public/divisions/*` by hand — they are
generated. Change the model and rebuild.

## Notes

- Points: win 3, draw 1, loss 0. Ranking is on PPM (see tiebreakers above).
- `MANUAL_RESULTS` in `build_data.py` is currently empty. It injects a match even if the
  scrape did not contain it, so a stale entry would create a phantom fixture in whichever
  division holds those team names — keep it empty unless deliberately patching a missing score.
- `EXCLUDED_TEAMS = {'Breakers FC'}` is a leftover from the single-division era and now
  applies across all 120 divisions. It currently matches nothing in the feed, so it is a
  harmless no-op — but it would silently drop that club and its matches if the name reappeared.

## Related

- `.claude/skills/refresh-standings` — pulling fresh data
- `docs/plans/last-season-prior.md` — prior-season weighting plan

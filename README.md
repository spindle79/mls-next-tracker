# mls-next-tracker

> Standings, predictions, and a what-if game explorer for every MLS NEXT Academy division. Pulls the season feeds from the [MLS Assist league viewer](https://mls-assist.theintelligenceplatform.com), simulates the rest of the season, and renders an interactive Next.js dashboard.

[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **At a glance** — A 120-division MLS NEXT Academy season tracker (6 age groups × 20 regional divisions, 1,612 teams). A single Python scraper pulls two static JSON feeds from the MLS Assist league viewer, a prediction model walks the schedule game-by-game using only standings + H2H _prior to each week_ (no lookahead), and a Next.js 15 / React 19 app renders weekly evolution, current vs projected standings, head-to-head, and a "what-if" panel for re-projecting a division on hypothetical results.
>
> **What this repo demonstrates**
>
> - **End-to-end data product** — fetch → join → simulate → ship. Four Python entry points (`scrape_academy.py`, `build_data.py`, `backtest_predictions.py`, `tune_prediction_params.py`) plus a Next.js front end.
> - **A real prediction model** — Bayesian-flavored win probabilities with shrinkage to a pseudo-prior, home-strength bonus, H2H weighting, draw cap/floor with decay, and scoreline blending. Hyperparameters are tuned by random search against a calibration backtest (`tune_prediction_params.py`).
> - **Honest evaluation** — `backtest_predictions.py` walks the season week by week, predicting only with information available _before_ that week. The same backtest is what the tuner optimizes against.
> - **Multi-division architecture at the schema level** — `data.json` ships in `schema_version: 2` with a `division_catalog` + per-division shards. The Next.js app loads one division at a time but the dropdown sees all 120.
> - **Sensible separation of input vs output** — `data.json`, `scraped_*.json`, and the rendered division shards are all gitignored; the repo ships only the source code that produces them.
>
> **Quickstart (data + app)**
>
> ```bash
> # 1. Set up the Python side for scraping + prediction
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
>
> # 2. Pull a fresh dataset (two HTTP requests, all 120 divisions, seconds)
> python3 scrape_academy.py                    # or --ages U14 for one age group
>
> # 3. Build data.json from the scrape + render division shards
> ./refresh.sh --from-academy-scrape
>
> # 4. Run the Next.js app
> pnpm install
> pnpm dev   # http://localhost:3000
> ```

---

## Project layout

```
mls-next-tracker/
├── app/                          # Next.js 15 App Router
│   ├── layout.tsx
│   ├── page.tsx                  # mounts <TrackerApp />
│   └── globals.css
├── components/tracker/           # React UI
│   ├── TrackerApp.tsx            # division picker + tab shell
│   ├── TrackerUi.tsx             # shared layout primitives
│   ├── WeeklyPanel.tsx           # week-by-week standings evolution
│   ├── ProjectedPanel.tsx        # current vs projected final
│   ├── PredictionsPanel.tsx      # remaining-game predictions
│   ├── H2HPanel.tsx              # head-to-head matrix
│   └── WhatIfPanel.tsx           # re-project on hypothetical results
├── lib/tracker/                  # client-side logic
│   ├── loadDivision.ts           # fetch a division shard from public/
│   ├── logic.ts                  # standings math + simulation helpers
│   └── types.ts
├── scripts/
│   └── export-divisions.mjs      # split data.json → public/divisions/<id>.json + public/data.json
├── scrape_academy.py             # all MLS NEXT Academy divisions, all age groups
├── build_data.py                 # builds the schema-v2 data.json with predictions
├── scrape.py                     # legacy modular11 single-division scraper (retired source)
├── parse_standings.py            # legacy modular11 HTML parser (retired source)
├── backtest_predictions.py       # walk-forward calibration backtest
├── tune_prediction_params.py     # random search over PREDICTION_PARAMS
├── refresh.sh                    # one-shot: rebuild data.json + re-embed + re-shard
└── requirements.txt              # Python deps for the scraping + prediction side
```

## Pipeline

```
MLS Assist league viewer
  /data/standings/<season-key>.json   position + tiebreaker values per squad
  /data/schedule/<season-key>.json    every match, whole season
      │
      ▼
scrape_academy.py
      │  (plain HTTP; the two feeds are joined on squad_id)
      ▼
scraped_academy.json
      │
      ▼
build_data.py --from-academy-scrape
      │  (week-by-week standings evolution + season-end projection
      │   via the prediction model in PREDICTION_PARAMS)
      ▼
data.json (schema_version 2, multi-division)
      │
      ▼
scripts/export-divisions.mjs
      │  (splits into public/divisions/<id>.json + public/data.json)
      ▼
Next.js app fetches one division shard at a time
```

## The prediction model

`build_data.py` predicts each remaining match with a probability over win/draw/loss + a scoreline distribution. Inputs are only standings + H2H **prior to the week being predicted** — no lookahead. Hyperparameters live in `DEFAULT_PREDICTION_PARAMS`:

| Param                                           | Effect                                                                                                           |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `shrink_pseudo_mp`                              | How many "fake" matches of average strength to add when a team has played few games (early-season noise control) |
| `home_strength_bonus`                           | Home-team boost in the strength-difference calc                                                                  |
| `h2h_full_games`                                | How many recent head-to-head meetings to weight at full strength                                                 |
| `draw_floor` / `draw_cap` / `draw_decay`        | Floor and cap on draw probability; how quickly draw share decays as strength gap grows                           |
| `margin_split_scale`                            | Maps strength gap → win-margin distribution                                                                      |
| `scoreline_blend_max` / `scoreline_target_draw` | Mix of model scoreline distribution vs Poisson-style baseline                                                    |
| `prob_floor`                                    | Minimum probability for any outcome (avoids zeros from sparse data)                                              |

`tune_prediction_params.py` runs a random search over these parameters and reports the best configuration against the same walk-forward backtest the model is honestly evaluated on.

## What's in the UI

- **Weekly** — for each completed week, the standings as they stood at end-of-week, plus a delta column vs the prior week.
- **Projected** — current standings against the model's full-season projection. Sortable by current rank, projected rank, or delta.
- **Predictions** — every remaining game with win / draw / loss probabilities and the model's most likely scoreline.
- **H2H** — a 1v1 matrix showing how every team has fared against every other team this season.
- **What-If** — fix the result of one or more remaining games and watch the projected final standings re-shuffle.

## Customizing the focus team

A few places highlight a "focus team" by name (default: `San Francisco Glens SC`, the team this project was built for). To track a different team, edit:

- `lib/tracker/logic.ts` — change the `GLENS_FOCUS` constant
- `build_data.py` — change the `GLENS = 'San Francisco Glens SC'` constant in `main()`

Use the club name exactly as the standings feed spells it (the feed says `San Francisco Glens SC`, not `San Francisco Glens`).

The rest of the app works for every one of the 120 divisions without any focus-team configuration.

## Deployment

Configured for Vercel (`vercel.json`, `pnpm vercel-build`). The `prebuild` step runs `scripts/export-divisions.mjs`, which splits the latest `data.json` into per-division shards under `public/divisions/`. If `data.json` isn't present at deploy time, the script no-ops and the app falls back to its embedded default division.

## Notes

- The whole season is two unfiltered static JSON files, so a full refresh is two HTTP requests and no browser. The `squads` / `clubs` / `from` / `to` params in a league-viewer URL are client-side filters only, and its pagination is a UI control — none of it narrows what the feed returns.
- The standings feed is authoritative for team and division names. The schedule feed carries its own `division` field that disagrees with it (it says "South California" for "Southern California", and files a block of "North" fixtures under "Great Lakes North"), so the scraper joins the feeds on `squad_id` and ignores it.
- Interleague fixtures (both clubs in different brackets) are excluded, which is what the standings feed does too — matching it reproduces the published `MP` and goal totals exactly.
- A handful of squads appear in the schedule with no standings row; the scraper reports them by name and skips them.
- Predictions need prior results: `predict_single_match` returns nothing when either club has `MP == 0`, so a division produces no predictions until its teams have played. Early in a season most divisions project as their current table.
- Predictions are calibrated on completed games only — early-season weeks are inherently noisy, which `shrink_pseudo_mp` softens.
- `page1.html` / `page2.html` were saved modular11 standings snapshots used to bootstrap the original parser. They're gitignored, and that source is retired.

## License

[MIT](LICENSE) © Adam Harris

## Acknowledgments

- The [MLS Assist league viewer](https://mls-assist.theintelligenceplatform.com) publishes the MLS NEXT Academy standings and schedule feeds this project reads
- [Next.js](https://nextjs.org/) + [React 19](https://react.dev/) for the dashboard

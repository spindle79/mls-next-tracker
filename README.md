# mls-next-tracker

> Standings, predictions, and a what-if game explorer for every MLS NEXT Academy + Homegrown division. Scrapes [modular11.com](https://www.modular11.com), simulates the rest of the season, and renders an interactive Next.js dashboard.

[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **At a glance** — A 162-division MLS NEXT season tracker. Python scrapers (`requests` + Playwright) pull every Academy (U13–U19) and Homegrown division from modular11.com, a prediction model walks the schedule game-by-game using only standings + H2H *prior to each week* (no lookahead), and a Next.js 15 / React 19 app renders weekly evolution, current vs projected standings, head-to-head, and a "what-if" panel for re-projecting a division on hypothetical results.
>
> **What this repo demonstrates**
>
> - **End-to-end data product** — scrape → parse → simulate → ship. Six Python entry points (`scrape.py`, `scrape_academy.py`, `scrape_homegrown.py`, `build_data.py`, `backtest_predictions.py`, `tune_prediction_params.py`) plus a Next.js front end.
> - **A real prediction model** — Bayesian-flavored win probabilities with shrinkage to a pseudo-prior, home-strength bonus, H2H weighting, draw cap/floor with decay, and scoreline blending. Hyperparameters are tuned by random search against a calibration backtest (`tune_prediction_params.py`).
> - **Honest evaluation** — `backtest_predictions.py` walks the season week by week, predicting only with information available *before* that week. The same backtest is what the tuner optimizes against.
> - **Multi-division architecture at the schema level** — `data.json` ships in `schema_version: 2` with a `division_catalog` + per-division shards. The Next.js app loads one division at a time but the dropdown sees all 162.
> - **Sensible separation of input vs output** — `data.json`, `scraped_*.json`, and the rendered division shards are all gitignored; the repo ships only the source code that produces them.
>
> **Quickstart (data + app)**
>
> ```bash
> # 1. Set up the Python side for scraping + prediction
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> playwright install chromium
>
> # 2. Pull a fresh dataset from modular11.com (one age group at a time is fastest)
> python3 scrape_academy.py --ages 21          # U13 only — ~5 min
> python3 scrape_homegrown.py --ages 21
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
├── scrape.py                     # legacy single-division (U13 NorCal) scraper
├── scrape_academy.py             # all MLS NEXT Academy divisions, all age groups
├── scrape_homegrown.py           # all MLS NEXT Homegrown divisions, all age groups
├── build_data.py                 # builds the schema-v2 data.json with predictions
├── parse_standings.py            # legacy HTML parser (used to read saved standings pages)
├── backtest_predictions.py       # walk-forward calibration backtest
├── tune_prediction_params.py     # random search over PREDICTION_PARAMS
├── refresh.sh                    # one-shot: rebuild data.json + re-embed + re-shard
└── requirements.txt              # Python deps for the scraping + prediction side
```

## Pipeline

```
modular11.com
      │
      ▼
scrape_academy.py / scrape_homegrown.py
      │  (Playwright + in-page fetch for match lists)
      ▼
scraped_academy.json
scraped_homegrown.json
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

| Param | Effect |
|---|---|
| `shrink_pseudo_mp` | How many "fake" matches of average strength to add when a team has played few games (early-season noise control) |
| `home_strength_bonus` | Home-team boost in the strength-difference calc |
| `h2h_full_games` | How many recent head-to-head meetings to weight at full strength |
| `draw_floor` / `draw_cap` / `draw_decay` | Floor and cap on draw probability; how quickly draw share decays as strength gap grows |
| `margin_split_scale` | Maps strength gap → win-margin distribution |
| `scoreline_blend_max` / `scoreline_target_draw` | Mix of model scoreline distribution vs Poisson-style baseline |
| `prob_floor` | Minimum probability for any outcome (avoids zeros from sparse data) |

`tune_prediction_params.py` runs a random search over these parameters and reports the best configuration against the same walk-forward backtest the model is honestly evaluated on.

## What's in the UI

- **Weekly** — for each completed week, the standings as they stood at end-of-week, plus a delta column vs the prior week.
- **Projected** — current standings against the model's full-season projection. Sortable by current rank, projected rank, or delta.
- **Predictions** — every remaining game with win / draw / loss probabilities and the model's most likely scoreline.
- **H2H** — a 1v1 matrix showing how every team has fared against every other team this season.
- **What-If** — fix the result of one or more remaining games and watch the projected final standings re-shuffle.

## Customizing the focus team

A few places highlight a "focus team" by name (default: `San Francisco Glens`, the team this project was built for). To track a different team, edit:

- `lib/tracker/logic.ts` — change the `GLENS_FOCUS` constant
- `build_data.py` — change the `GLENS = 'San Francisco Glens'` constant in `main()` (around L1103)

The rest of the app works for every one of the 162 divisions without any focus-team configuration.

## Deployment

Configured for Vercel (`vercel.json`, `pnpm vercel-build`). The `prebuild` step runs `scripts/export-divisions.mjs`, which splits the latest `data.json` into per-division shards under `public/divisions/`. If `data.json` isn't present at deploy time, the script no-ops and the app falls back to its embedded default division.

## Notes

- The scrape is rate-limit-friendly: scripts sleep between requests and per-team match-list fetches go through the in-page fetch (already authenticated against modular11's CSRF) rather than hammering the public endpoints.
- `page1.html` / `page2.html` were saved standings snapshots used to bootstrap the parser before the Playwright-based scrape was working. They're gitignored — if you want to use the legacy `parse_standings.py` path, save the standings page from modular11 yourself.
- Predictions are calibrated on completed games only — early-season weeks are inherently noisy, which `shrink_pseudo_mp` softens.

## License

[MIT](LICENSE) © Adam Harris

## Acknowledgments

- [modular11.com](https://www.modular11.com/) hosts the MLS NEXT division standings this project scrapes
- [Next.js](https://nextjs.org/) + [React 19](https://react.dev/) for the dashboard
- [Playwright](https://playwright.dev/) for the JS-rendered scrape

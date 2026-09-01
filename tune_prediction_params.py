#!/usr/bin/env python3
"""
Random search over DEFAULT_PREDICTION_PARAMS, scored by the same walk-forward
backtest as backtest_predictions.py.

Reads `scraped_academy.json`. Weeks are parsed once and replayed per trial, so
trial cost is the prediction work itself.

Cost scales with divisions x played matches x trials. A full-season 20-division
age group backtests in roughly 2s, so ~11s per trial across all 120 divisions —
a 140-trial sweep is ~25 minutes. Narrow with --ages / --divisions while
iterating.

Usage:
  python3 tune_prediction_params.py --ages U14 --trials 60
  python3 tune_prediction_params.py --trials 200 --json-out tuning.json
"""

import argparse
import json
import random
import sys

from build_data import DEFAULT_PREDICTION_PARAMS
from backtest_predictions import DEFAULT_INPUT, load_divisions, run_backtest, summarize

# Below this many scored games, a "best" configuration is noise. The 26/27
# season opened with 37 completed matches league-wide, which is nowhere near
# enough — see docs/plans/last-season-prior.md.
MIN_GAMES_TO_RECOMMEND = 200


def random_params(rng):
    """Sample the tunable space.

    Ranges bracket the current defaults deliberately: the previous version
    searched shrink_pseudo_mp in [3.0, 6.5] while the default was 2.93 and
    draw_cap in [0.26, 0.34] while the default was 0.252, so it could not
    reproduce — let alone beat — its own baseline.
    """
    return {
        # Composite strength
        'shrink_pseudo_mp': rng.uniform(1.5, 6.5),
        'home_strength_bonus': rng.uniform(0.02, 0.16),
        'h2h_full_games': rng.choice([2, 3, 4, 5]),
        # Outcome probabilities
        'draw_floor': rng.uniform(0.10, 0.20),
        'draw_cap': rng.uniform(0.20, 0.34),
        'draw_decay': rng.uniform(0.25, 0.70),
        'margin_split_scale': rng.uniform(0.70, 1.40),
        'scoreline_blend_max': rng.uniform(0.15, 0.48),
        'scoreline_target_draw': rng.uniform(0.18, 0.32),
        'prob_floor': rng.uniform(0.04, 0.11),
        # Goal model — absent from the old search space entirely
        'goal_shrink_pseudo_mp': rng.uniform(1.5, 6.0),
        'home_goal_mult': rng.uniform(0.98, 1.18),
        'opp_adj_blend': rng.uniform(0.0, 0.7),
        'venue_split_blend_max': rng.uniform(0.0, 0.5),
    }


def clamp_params(p):
    """Enforce the ordering the model assumes."""
    if p['draw_cap'] <= p['draw_floor']:
        p['draw_cap'] = p['draw_floor'] + 0.08
    return p


def main():
    parser = argparse.ArgumentParser(description='Random search over prediction params')
    parser.add_argument('--input', default=DEFAULT_INPUT, help='Scrape bundle to tune against')
    parser.add_argument('--ages', default='', help='Comma-separated age labels, e.g. U14')
    parser.add_argument('--divisions', default='', help='Comma-separated division names')
    parser.add_argument('--trials', type=int, default=140)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--top', type=int, default=8)
    parser.add_argument('--json-out', default='', help='Write all trial results here')
    parser.add_argument(
        '--allow-small-sample',
        action='store_true',
        help=f'Emit a recommendation even under {MIN_GAMES_TO_RECOMMEND} scored games',
    )
    args = parser.parse_args()

    ages = [a for a in args.ages.split(',') if a.strip()]
    divs = [d for d in args.divisions.split(',') if d.strip()]

    try:
        divisions = load_divisions(args.input, ages or None, divs or None)
    except FileNotFoundError as e:
        print(f'Missing input file: {e}', file=sys.stderr)
        print('Run: python3 scrape_academy.py', file=sys.stderr)
        sys.exit(1)

    if not divisions:
        print('No divisions matched the filters.', file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)

    base_rows, _ = run_backtest(divisions, None)
    base = summarize(base_rows)
    if not base_rows:
        print(
            f'Loaded {len(divisions)} divisions but scored 0 games.\n'
            'predict_single_match needs both clubs to have played before the match it '
            'predicts, so there is nothing to tune against yet.',
            file=sys.stderr,
        )
        sys.exit(1)

    n = base['total_games']
    print(f'Divisions: {len(divisions)}  |  scored games: {n}')
    print('\nBaseline (DEFAULT_PREDICTION_PARAMS):')
    print(f"  log_loss={base['mean_log_loss']}  acc={base['accuracy_pick_max_prob']}  n={n}")
    print(f"  by MP bucket: {json.dumps({k: v['mean_log_loss'] for k, v in base['by_mp_bucket'].items()})}")
    print()

    results = []
    for t in range(args.trials):
        p = clamp_params(random_params(rng))
        rows, _ = run_backtest(divisions, p)
        s = summarize(rows)
        results.append({'params': p, 'summary': s})
        if (t + 1) % 20 == 0:
            print(f'  ...{t + 1}/{args.trials} trials', file=sys.stderr)

    results.sort(
        key=lambda r: (r['summary']['mean_log_loss'], -r['summary']['accuracy_pick_max_prob'])
    )

    print(f'Best {args.top} by mean log loss (then accuracy):\n')
    for i, r in enumerate(results[: args.top], 1):
        s = r['summary']
        delta = s['mean_log_loss'] - base['mean_log_loss']
        print(
            f"#{i}  log_loss={s['mean_log_loss']} ({delta:+.4f} vs baseline)  "
            f"acc={s['accuracy_pick_max_prob']}  favorite_wrong={s['favorite_pick_wrong_count']}"
        )
        print(f"    by MP bucket: {json.dumps({k: v['mean_log_loss'] for k, v in s['by_mp_bucket'].items()})}")
        print(json.dumps(r['params'], indent=2))
        print()

    best = results[0]
    improved = best['summary']['mean_log_loss'] < base['mean_log_loss']

    if args.json_out:
        with open(args.json_out, 'w') as f:
            json.dump({'baseline': base, 'trials': results}, f, indent=2)
        print(f'Wrote {args.json_out}\n')

    if n < MIN_GAMES_TO_RECOMMEND and not args.allow_small_sample:
        print(
            f'NO RECOMMENDATION — only {n} scored games (want >= {MIN_GAMES_TO_RECOMMEND}).\n'
            'A "best" configuration from this few games is fitting noise, and the top\n'
            'trials above are shown for inspection only. Re-run once more of the season\n'
            'has been played, or pass --allow-small-sample if you understand the risk.'
        )
        return

    if not improved:
        print(
            'NO RECOMMENDATION — no sampled configuration beat the baseline.\n'
            'Keep DEFAULT_PREDICTION_PARAMS as it is, or widen the search space.'
        )
        return

    print('RECOMMENDED merge into DEFAULT_PREDICTION_PARAMS:\n')
    print(json.dumps(best['params'], indent=2))
    print(
        '\nBefore merging, check the by-MP-bucket line above: a config that buys a small\n'
        'overall gain by regressing the high-MP buckets is usually a bad trade.'
    )


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Random search over PREDICTION_PARAMS using the same backtest as backtest_predictions.py.
Run: python3 tune_prediction_params.py --from-scrape
"""

import argparse
import json
import random
import sys

from build_data import DEFAULT_PREDICTION_PARAMS
from backtest_predictions import load_team_names_and_matches, run_backtest, summarize


def random_params(rng):
    return {
        'shrink_pseudo_mp': rng.uniform(3.0, 6.5),
        'home_strength_bonus': rng.uniform(0.06, 0.16),
        'h2h_full_games': rng.choice([2, 3, 4]),
        'draw_floor': rng.uniform(0.13, 0.20),
        'draw_cap': rng.uniform(0.26, 0.34),
        'draw_decay': rng.uniform(0.30, 0.55),
        'margin_split_scale': rng.uniform(0.75, 1.15),
        'scoreline_blend_max': rng.uniform(0.22, 0.48),
        'scoreline_target_draw': rng.uniform(0.22, 0.32),
        'prob_floor': rng.uniform(0.068, 0.11),
    }


def clamp_params(p):
    """Keep draw_cap >= draw_floor + small gap."""
    if p['draw_cap'] <= p['draw_floor']:
        p['draw_cap'] = p['draw_floor'] + 0.08
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-scrape', action='store_true')
    parser.add_argument('--trials', type=int, default=140)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--top', type=int, default=8)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    try:
        team_names, all_matches = load_team_names_and_matches(args.from_scrape)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    # Baseline: baked-in defaults in build_data
    base_rows, _ = run_backtest(team_names, all_matches, None)
    base = summarize(base_rows)
    print('Baseline (DEFAULT_PREDICTION_PARAMS):')
    print(f"  log_loss={base['mean_log_loss']} acc={base['accuracy_pick_max_prob']} n={base['total_games']}")
    print(json.dumps(DEFAULT_PREDICTION_PARAMS, indent=2))
    print()

    results = []
    for t in range(args.trials):
        p = clamp_params(random_params(rng))
        rows, _ = run_backtest(team_names, all_matches, p)
        s = summarize(rows)
        results.append((s['mean_log_loss'], s['accuracy_pick_max_prob'], s['favorite_pick_wrong_count'], p, s))

    results.sort(key=lambda x: (x[0], -x[1]))

    print(f'Best {args.top} by mean log loss (then accuracy):\n')
    for i, (ll, acc, fav_wrong, p, s) in enumerate(results[: args.top], 1):
        print(f"#{i}  log_loss={ll}  acc={acc}  favorite_wrong={fav_wrong}")
        print(json.dumps(p, indent=2))
        print()

    best = results[0][3]
    print('RECOMMENDED merge into DEFAULT_PREDICTION_PARAMS:\n')
    print(json.dumps(best, indent=2))


if __name__ == '__main__':
    main()

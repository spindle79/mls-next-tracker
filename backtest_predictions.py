#!/usr/bin/env python3
"""
Walk the season week-by-week: for each finished match, predict using only
standings + H2H *before that week* (no lookahead within the week), then compare
to the actual result. Use this to judge calibration and form hypotheses about
systematic misses (upsets, blowouts, early-season noise, etc.).
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

from build_data import (
    apply_match_result,
    deduplicate_matches,
    filter_excluded_teams,
    get_week_start,
    load_from_scrape,
    parse_date,
    parse_score,
    parse_standings_file,
    predict_single_match,
)


def actual_outcome(hg, ag):
    if hg > ag:
        return 'home_win'
    if ag > hg:
        return 'away_win'
    return 'draw'


def prob_for_outcome(pred, outcome):
    return {
        'home_win': pred['home_win_prob'],
        'away_win': pred['away_win_prob'],
        'draw': pred['draw_prob'],
    }[outcome]


def load_team_names_and_matches(use_scrape):
    repo_root = os.path.dirname(os.path.abspath(__file__))
    if use_scrape:
        scraped_path = os.path.join(repo_root, 'scraped_matches.json')
        standings_path = os.path.join(repo_root, 'scraped_standings.json')
        standings_data = None
        try:
            with open(standings_path) as f:
                standings_data = json.load(f)
        except FileNotFoundError:
            pass
        team_names, all_matches, _ = load_from_scrape(scraped_path, standings_data)
        all_matches = list(all_matches)
    else:
        teams1 = parse_standings_file(os.path.join(repo_root, 'page1.html'))
        teams2 = parse_standings_file(os.path.join(repo_root, 'page2.html'))
        team_names = list({t['name'] for t in teams1} | {t['name'] for t in teams2})
        team_names.sort()
        all_matches = deduplicate_matches(teams1, teams2)

    team_names, all_matches, _ = filter_excluded_teams(team_names, all_matches, [])
    return sorted(team_names), all_matches


def run_backtest(team_names, all_matches, params=None):
    parsed = []
    for m in all_matches:
        dt = parse_date(m['date'])
        if dt:
            parsed.append({**m, '_dt': dt})
    parsed.sort(key=lambda x: x['_dt'])

    weeks = defaultdict(list)
    for m in parsed:
        wk = get_week_start(m['_dt']).strftime('%Y-%m-%d')
        weeks[wk].append(m)

    standings = {
        name: {
            'PTS': 0, 'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0, 'GD': 0, 'MP': 0,
            'home_MP': 0, 'away_MP': 0,
            'home_GF': 0, 'home_GA': 0, 'away_GF': 0, 'away_GA': 0,
        }
        for name in team_names
    }
    h2h = defaultdict(
        lambda: defaultdict(lambda: {'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0})
    )

    rows = []
    by_week = []

    for week_key in sorted(weeks.keys()):
        week_matches = weeks[week_key]
        played = [(m, parse_score(m['score'])) for m in week_matches]
        played = [(m, s) for m, s in played if s is not None]

        week_rows = []
        for m, score in played:
            hg, ag = score
            pred = predict_single_match(m, standings, h2h, team_names, params)
            actual = actual_outcome(hg, ag)
            if pred is None:
                apply_match_result(m['home'], m['away'], hg, ag, standings, h2h)
                continue

            p_act = prob_for_outcome(pred, actual)
            correct = pred['predicted_outcome'] == actual
            strength_gap = pred['home_strength'] - pred['away_strength']
            upset = False
            if actual == 'home_win' and pred['predicted_outcome'] == 'away_win':
                upset = True
            elif actual == 'away_win' and pred['predicted_outcome'] == 'home_win':
                upset = True

            row = {
                'week_start': week_key,
                'match_id': m['match_id'],
                'date': m['date'],
                'home': m['home'],
                'away': m['away'],
                'score': m['score'],
                'actual_outcome': actual,
                'predicted_outcome': pred['predicted_outcome'],
                'correct': correct,
                'home_win_prob': pred['home_win_prob'],
                'away_win_prob': pred['away_win_prob'],
                'draw_prob': pred['draw_prob'],
                'prob_actual': round(p_act, 4),
                'log_loss': round(-math.log(max(p_act, 1e-12)), 4),
                'home_strength': pred['home_strength'],
                'away_strength': pred['away_strength'],
                'strength_gap_home_minus_away': round(strength_gap, 3),
                'favorite_wrong': upset,
                'est_home_goals': pred['est_home_goals'],
                'est_away_goals': pred['est_away_goals'],
            }
            rows.append(row)
            week_rows.append(row)

        for m, score in played:
            hg, ag = score
            apply_match_result(m['home'], m['away'], hg, ag, standings, h2h)

        if week_rows:
            n = len(week_rows)
            acc = sum(1 for r in week_rows if r['correct']) / n
            ll = sum(r['log_loss'] for r in week_rows) / n
            by_week.append({
                'week_start': week_key,
                'games': n,
                'accuracy': round(acc, 3),
                'mean_log_loss': round(ll, 4),
            })

    return rows, by_week


def summarize(rows):
    if not rows:
        return {}
    n = len(rows)
    acc = sum(1 for r in rows if r['correct']) / n
    ll_mean = sum(r['log_loss'] for r in rows) / n
    upsets = [r for r in rows if r['favorite_wrong']]
    worst = sorted(rows, key=lambda r: r['log_loss'], reverse=True)[:12]
    return {
        'total_games': n,
        'accuracy_pick_max_prob': round(acc, 3),
        'mean_log_loss': round(ll_mean, 4),
        'favorite_pick_wrong_count': len(upsets),
        'hardest_predictions_log_loss': worst,
    }


def main():
    parser = argparse.ArgumentParser(description='Backtest predict_single_match week-by-week')
    parser.add_argument('--from-scrape', action='store_true', help='Load from scraped JSON like build_data.py')
    parser.add_argument('--json-out', type=str, default='', help='Write full rows + summary to this path')
    parser.add_argument(
        '--params-json',
        type=str,
        default='',
        help='Optional JSON object overriding DEFAULT_PREDICTION_PARAMS from build_data.py',
    )
    args = parser.parse_args()

    try:
        team_names, all_matches = load_team_names_and_matches(args.from_scrape)
    except FileNotFoundError as e:
        print(f'Missing input file: {e}', file=sys.stderr)
        sys.exit(1)

    override = json.loads(args.params_json) if args.params_json.strip() else None
    rows, by_week = run_backtest(team_names, all_matches, override)
    summary = summarize(rows)

    print('## Prediction backtest (no lookahead within week)\n')
    print(f"Games evaluated: {summary.get('total_games', 0)}")
    print(f"Accuracy (predicted class vs actual): {summary.get('accuracy_pick_max_prob', 0):.1%}")
    print(f"Mean log loss (lower is better): {summary.get('mean_log_loss', 0):.4f}")
    print(f"Times favorite pick was wrong: {summary.get('favorite_pick_wrong_count', 0)}")

    print('\n### Week-by-week')
    for w in by_week:
        print(f"  {w['week_start']}: {w['games']} games, acc {w['accuracy']:.0%}, mean log loss {w['mean_log_loss']}")

    print('\n### Highest log-loss games (model was most surprised)')
    for r in summary.get('hardest_predictions_log_loss', []):
        print(
            f"  {r['date'][:16]} | {r['home'][:22]} vs {r['away'][:22]} | "
            f"{r['score']} actual={r['actual_outcome']} pred={r['predicted_outcome']} "
            f"P(actual)={r['prob_actual']} gap={r['strength_gap_home_minus_away']}"
        )

    print(
        '\n### How to read this for hypotheses\n'
        '- **Early weeks**: high log loss often means few MP — PPM/GD are noisy.\n'
        '- **Large strength_gap but wrong favorite**: H2H or common-opponent signal may be misleading, or single-game variance.\n'
        '- **Draws**: if many misses are draws, the draw branch / scoreline margin may be miscalibrated.\n'
        '- **Blowouts** (check score): averaging goals underestimates variance; model has no “form” window.\n'
    )

    if args.json_out:
        out = {'summary': summary, 'by_week': by_week, 'rows': rows}
        with open(args.json_out, 'w') as f:
            json.dump(out, f, indent=2)
        print(f"\nWrote {args.json_out}")


if __name__ == '__main__':
    main()

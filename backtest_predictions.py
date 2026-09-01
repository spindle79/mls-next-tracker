#!/usr/bin/env python3
"""
Walk each division's season week-by-week: for every finished match, predict using
only standings + H2H *before that week* (no lookahead within the week), then
compare to the actual result. Use this to judge calibration and form hypotheses
about systematic misses (upsets, blowouts, early-season noise, etc.).

Reads `scraped_academy.json` — the multi-division bundle written by
scrape_academy.py. Each division is walked independently: standings, league
averages and H2H are only meaningful within a division, since teams from
different divisions never meet. Per-game rows are pooled afterwards for the
summary.

Usage:
  python3 backtest_predictions.py                        # every division
  python3 backtest_predictions.py --ages U14             # one age group
  python3 backtest_predictions.py --divisions Pioneer    # one division, all ages
  python3 backtest_predictions.py --json-out bt.json     # full rows + aggregates
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

from build_data import (
    apply_match_result,
    filter_excluded_teams,
    get_week_start,
    load_from_scrape_rows,
    make_division_id,
    parse_date,
    parse_score,
    predict_single_match,
)

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(REPO_ROOT, 'scraped_academy.json')

# Matches-played buckets, keyed on min(home_MP, away_MP) at prediction time —
# the binding constraint, since predict_single_match needs both sides to have
# played. The whole point of a prior-season prior is the low buckets, so a
# single pooled average would hide the effect (see docs/plans/last-season-prior.md).
MP_BUCKETS = (
    ('1-3', 1, 3),
    ('4-7', 4, 7),
    ('8-11', 8, 11),
    ('12+', 12, 10**6),
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


def mp_bucket(min_mp):
    for label, lo, hi in MP_BUCKETS:
        if lo <= min_mp <= hi:
            return label
    return 'other'


def load_divisions(input_path=DEFAULT_INPUT, ages=None, divisions=None):
    """Load the scrape bundle into per-division datasets with dates pre-parsed.

    Parsing once here (rather than inside run_backtest) matters for the tuner,
    which replays the same weeks hundreds of times.
    """
    with open(input_path) as f:
        bundle = json.load(f)

    league_slug = (bundle.get('league') or 'academy').replace('/', '-')
    want_ages = {a.strip().upper() for a in ages} if ages else None
    want_divs = {d.strip().lower() for d in divisions} if divisions else None

    out = []
    for age_group in bundle.get('age_groups') or []:
        age_label = age_group.get('age_label') or ''
        if want_ages and age_label.upper() not in want_ages:
            continue

        for div_block in age_group.get('divisions') or []:
            div_title = div_block.get('division') or 'Unknown Division'
            if want_divs and div_title.lower() not in want_divs:
                continue

            teams_raw = div_block.get('teams') or []
            scraped_teams = [
                {'name': t['name'], 'matches': t.get('matches') or []} for t in teams_raw
            ]
            standings_rows = [
                {'rank': t['rank'], 'name': t['name'], 'stats': t.get('stats') or {}}
                for t in teams_raw
            ]

            team_names, all_matches, _ = load_from_scrape_rows(scraped_teams, standings_rows)
            team_names, all_matches, _ = filter_excluded_teams(team_names, all_matches, [])

            # Group into Monday-keyed weeks once.
            parsed = []
            for m in all_matches:
                dt = parse_date(m['date'])
                if dt:
                    parsed.append({**m, '_dt': dt})
            parsed.sort(key=lambda x: x['_dt'])

            by_week = defaultdict(list)
            for m in parsed:
                by_week[get_week_start(m['_dt']).strftime('%Y-%m-%d')].append(m)

            played = sum(1 for m in parsed if parse_score(m['score']) is not None)
            out.append(
                {
                    'division_id': make_division_id(league_slug, div_title, age_label),
                    'age_label': age_label,
                    'division': div_title,
                    'team_names': sorted(team_names),
                    'weeks': [(k, by_week[k]) for k in sorted(by_week)],
                    'played_matches': played,
                }
            )

    return out


def run_division_backtest(div, params=None):
    """Walk one division week by week. Returns per-game rows."""
    standings = {
        name: {
            'PTS': 0, 'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0, 'GD': 0, 'MP': 0,
            'home_MP': 0, 'away_MP': 0,
            'home_GF': 0, 'home_GA': 0, 'away_GF': 0, 'away_GA': 0,
        }
        for name in div['team_names']
    }
    h2h = defaultdict(lambda: defaultdict(lambda: {'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0}))

    rows = []
    for week_key, week_matches in div['weeks']:
        played = [(m, parse_score(m['score'])) for m in week_matches]
        played = [(m, s) for m, s in played if s is not None]

        # Predict every match in the week before applying any of that week's
        # results — no lookahead within the week.
        for m, score in played:
            hg, ag = score
            home_s = standings.get(m['home'])
            away_s = standings.get(m['away'])
            min_mp = min(home_s['MP'], away_s['MP']) if home_s and away_s else 0

            pred = predict_single_match(m, standings, h2h, div['team_names'], params)
            if pred is None:
                continue

            actual = actual_outcome(hg, ag)
            p_act = prob_for_outcome(pred, actual)
            upset = (
                (actual == 'home_win' and pred['predicted_outcome'] == 'away_win')
                or (actual == 'away_win' and pred['predicted_outcome'] == 'home_win')
            )

            rows.append(
                {
                    'division_id': div['division_id'],
                    'age_label': div['age_label'],
                    'division': div['division'],
                    'week_start': week_key,
                    'match_id': m['match_id'],
                    'date': m['date'],
                    'home': m['home'],
                    'away': m['away'],
                    'score': m['score'],
                    'home_MP_before': home_s['MP'],
                    'away_MP_before': away_s['MP'],
                    'min_MP_before': min_mp,
                    'mp_bucket': mp_bucket(min_mp),
                    'actual_outcome': actual,
                    'predicted_outcome': pred['predicted_outcome'],
                    'correct': pred['predicted_outcome'] == actual,
                    'home_win_prob': pred['home_win_prob'],
                    'away_win_prob': pred['away_win_prob'],
                    'draw_prob': pred['draw_prob'],
                    'prob_actual': round(p_act, 4),
                    'log_loss': round(-math.log(max(p_act, 1e-12)), 4),
                    'home_strength': pred['home_strength'],
                    'away_strength': pred['away_strength'],
                    'strength_gap_home_minus_away': round(
                        pred['home_strength'] - pred['away_strength'], 3
                    ),
                    'favorite_wrong': upset,
                    'est_home_goals': pred['est_home_goals'],
                    'est_away_goals': pred['est_away_goals'],
                }
            )

        for m, score in played:
            hg, ag = score
            apply_match_result(m['home'], m['away'], hg, ag, standings, h2h)

    return rows


def run_backtest(divisions, params=None):
    """Walk every division; pool the rows. Returns (rows, by_week)."""
    rows = []
    for div in divisions:
        rows.extend(run_division_backtest(div, params))

    weeks = defaultdict(list)
    for r in rows:
        weeks[r['week_start']].append(r)

    by_week = [
        {
            'week_start': wk,
            'games': len(rs),
            'accuracy': round(sum(1 for r in rs if r['correct']) / len(rs), 3),
            'mean_log_loss': round(sum(r['log_loss'] for r in rs) / len(rs), 4),
        }
        for wk, rs in sorted(weeks.items())
    ]
    return rows, by_week


def _agg(rs):
    n = len(rs)
    return {
        'games': n,
        'accuracy': round(sum(1 for r in rs if r['correct']) / n, 3),
        'mean_log_loss': round(sum(r['log_loss'] for r in rs) / n, 4),
    }


def summarize(rows):
    if not rows:
        return {}
    by_bucket = defaultdict(list)
    for r in rows:
        by_bucket[r['mp_bucket']].append(r)
    by_div = defaultdict(list)
    for r in rows:
        by_div[r['division_id']].append(r)

    overall = _agg(rows)
    return {
        'total_games': overall['games'],
        'accuracy_pick_max_prob': overall['accuracy'],
        'mean_log_loss': overall['mean_log_loss'],
        'favorite_pick_wrong_count': sum(1 for r in rows if r['favorite_wrong']),
        'divisions_evaluated': len(by_div),
        'by_mp_bucket': {
            label: _agg(by_bucket[label]) for label, _, _ in MP_BUCKETS if by_bucket[label]
        },
        'by_division': {k: _agg(v) for k, v in sorted(by_div.items())},
        'hardest_predictions_log_loss': sorted(
            rows, key=lambda r: r['log_loss'], reverse=True
        )[:12],
    }


def main():
    parser = argparse.ArgumentParser(
        description='Backtest predict_single_match week-by-week across divisions'
    )
    parser.add_argument('--input', default=DEFAULT_INPUT, help=f'Scrape bundle (default: {DEFAULT_INPUT})')
    parser.add_argument('--ages', default='', help='Comma-separated age labels, e.g. U14 or U13,U14')
    parser.add_argument('--divisions', default='', help='Comma-separated division names, e.g. Pioneer')
    parser.add_argument('--json-out', default='', help='Write full rows + aggregates to this path')
    parser.add_argument(
        '--params-json',
        default='',
        help='JSON object overriding DEFAULT_PREDICTION_PARAMS from build_data.py',
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

    total_played = sum(d['played_matches'] for d in divisions)
    print('## Prediction backtest (no lookahead within week)\n')
    print(f'Divisions loaded: {len(divisions)}  |  played matches available: {total_played}')

    override = json.loads(args.params_json) if args.params_json.strip() else None
    rows, by_week = run_backtest(divisions, override)
    summary = summarize(rows)

    if not rows:
        print(
            '\nNo games could be evaluated.\n'
            'predict_single_match needs both clubs to have played before the match it '
            'predicts, so the first result for each team is never scored. Early in a '
            'season that leaves nothing to measure — come back once teams have a few '
            'matches each.'
        )
        return

    print(f"Games evaluated: {summary['total_games']} (of {total_played} played)")
    print(f"Divisions contributing: {summary['divisions_evaluated']}")
    print(f"Accuracy (predicted class vs actual): {summary['accuracy_pick_max_prob']:.1%}")
    print(f"Mean log loss (lower is better): {summary['mean_log_loss']:.4f}")
    print(f"Times favorite pick was wrong: {summary['favorite_pick_wrong_count']}")

    print('\n### By matches played (min of the two sides, before the match)')
    print('    Low buckets are where a prior-season prior would help; high buckets must not regress.')
    for label, agg in summary['by_mp_bucket'].items():
        print(f"  MP {label:<5} {agg['games']:>5} games   acc {agg['accuracy']:>6.1%}   log loss {agg['mean_log_loss']}")

    print('\n### Week-by-week')
    for w in by_week:
        print(f"  {w['week_start']}: {w['games']} games, acc {w['accuracy']:.0%}, mean log loss {w['mean_log_loss']}")

    print('\n### Highest log-loss games (model was most surprised)')
    for r in summary['hardest_predictions_log_loss']:
        print(
            f"  {r['date'][:16]} | {r['age_label']} {r['division'][:18]} | "
            f"{r['home'][:20]} vs {r['away'][:20]} | {r['score']} "
            f"actual={r['actual_outcome']} pred={r['predicted_outcome']} "
            f"P(actual)={r['prob_actual']} minMP={r['min_MP_before']}"
        )

    print(
        '\n### How to read this for hypotheses\n'
        '- **Low MP buckets**: high log loss there means PPM/GD are still noisy — that is what\n'
        '  a prior-season prior is meant to fix (docs/plans/last-season-prior.md).\n'
        '- **Large strength_gap but wrong favorite**: H2H or common-opponent signal may be\n'
        '  misleading, or it is single-game variance.\n'
        '- **Draws**: many missed draws means the draw branch / scoreline margin is miscalibrated.\n'
        '- **Blowouts**: averaging goals underestimates variance; the model has no form window.\n'
        '- **One division much worse than the rest**: check it for a data problem before the model.\n'
    )

    if args.json_out:
        with open(args.json_out, 'w') as f:
            json.dump({'summary': summary, 'by_week': by_week, 'rows': rows}, f, indent=2)
        print(f'\nWrote {args.json_out}')


if __name__ == '__main__':
    main()

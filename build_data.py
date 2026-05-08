#!/usr/bin/env python3
"""
Parse U13 NorCal Division standings from HTML, build week-by-week JSON
with evolving standings, and predict remaining game outcomes.
"""

import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

def parse_standings_file(filepath):
    """Parse a single HTML standings file and return teams + matches."""
    # Lazy import so backtests that use scraped JSON don't require bs4 installed.
    from bs4 import BeautifulSoup

    with open(filepath, 'r') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    teams = []
    division_rows = soup.find_all('div', class_='container-division-row')

    for div_row in division_rows:
        main_row = div_row.find('div', class_='main_row')
        if not main_row:
            continue

        rank_div = main_row.find('div', class_='container-rank')
        rank = int(rank_div.get_text(strip=True)) if rank_div else 0

        team_p = main_row.find('div', class_='container-team-info')
        team_name = ''
        if team_p:
            p_tag = team_p.find('p', attrs={'data-title': True})
            if p_tag:
                team_name = p_tag['data-title'].strip()

        stats_div = main_row.find('div', class_='pad-left')
        stats = []
        if stats_div:
            stat_divs = stats_div.find_all('div', recursive=False)
            for sd in stat_divs:
                val = sd.get_text(strip=True)
                if val:
                    stats.append(val)

        stat_names = ['PTS', 'PPM', 'MP', 'W', 'L', 'T', 'GF', 'GA', 'GD']
        team_stats = {}
        for i, name in enumerate(stat_names):
            raw = stats[i] if i < len(stats) else '0'
            try:
                team_stats[name] = float(raw) if '.' in raw else int(raw)
            except ValueError:
                team_stats[name] = 0

        # Parse matches
        matches = []
        evt_matches = div_row.find('div', class_='evt-matches')
        if evt_matches:
            match_rows = evt_matches.find_all('div', class_='table-content-row')
            for mr in match_rows:
                if 'hidden-xs' not in mr.get('class', []):
                    continue

                match_id_div = mr.find('div', class_='col-sm-1')
                match_id = ''
                if match_id_div:
                    match_id = match_id_div.get_text(strip=True).split('\n')[0].strip().replace('MALE', '').strip()

                details_div = mr.find('div', class_='col-sm-2')
                date_str = ''
                venue = ''
                if details_div:
                    text = details_div.get_text(separator='|', strip=True)
                    parts = text.split('|')
                    if parts:
                        date_str = parts[0].strip()
                    venue_p = details_div.find('p', attrs={'data-title': True})
                    if venue_p:
                        venue = venue_p['data-title'].strip()

                home_div = mr.find('div', class_='container-first-team')
                away_div = mr.find('div', class_='container-second-team')
                home_team = ''
                away_team = ''
                if home_div:
                    hp = home_div.find('p', attrs={'data-title': True})
                    if hp:
                        home_team = hp['data-title'].strip()
                if away_div:
                    ap = away_div.find('p', attrs={'data-title': True})
                    if ap:
                        away_team = ap['data-title'].strip()

                score_span = mr.find('span', class_='score-match-table')
                score = ''
                if score_span:
                    raw = score_span.get_text(strip=True).replace('\xa0', ' ').strip()
                    score = raw

                matches.append({
                    'match_id': match_id,
                    'date': date_str,
                    'venue': venue,
                    'home': home_team,
                    'away': away_team,
                    'score': score,
                })

        teams.append({
            'rank': rank,
            'name': team_name,
            'stats': team_stats,
            'matches': matches,
        })

    return teams


# Teams to exclude (not participating in the season)
EXCLUDED_TEAMS = {
    'Breakers FC',
}

# Scoreline blend: "close" uses gap on the half-goal grid (see round_predicted_scoreline).
SCORELINE_BLEND_GAP_UNITS = 1.0  # full blend at gap 0, none at gap >= this (in goals on .5 grid)

# Tunable via tune_prediction_params.py + backtest_predictions.py; optional override per call.
DEFAULT_PREDICTION_PARAMS = {
    # Bayesian shrinkage of PPM and GD/match toward league average (pseudo games).
    'shrink_pseudo_mp': 2.93,
    # Additive boost to home composite strength before margin (home edge).
    'home_strength_bonus': 0.073,
    # Head-to-head only reaches full weight after this many meetings.
    'h2h_full_games': 4,
    # Draw probability: floor, ceiling when teams are even, Gaussian decay on strength margin.
    'draw_floor': 0.143,
    'draw_cap': 0.252,
    'draw_decay': 0.501,
    # Steepness of home/away split of non-draw mass (sigmoid on margin).
    'margin_split_scale': 1.106,
    # When estimated goals are close, blend this fraction (max) toward symmetric + higher draw.
    'scoreline_blend_max': 0.261,
    'scoreline_target_draw': 0.244,
    # Minimum mass on any outcome (calibration; limits log-loss spikes).
    'prob_floor': 0.07,
    # Goal model: shrink per-team GF/GA per match toward league average (pseudo games).
    'goal_shrink_pseudo_mp': 3.5,
    # Home scoring multiplier (>1 means home teams score more on average).
    'home_goal_mult': 1.06,
    # Max goals per side to enumerate when turning expected goals into W/D/L probs.
    'poisson_max_goals': 8,
    # Opponent-adjusted Maher-style attack × defense_weakness ratings from h2h matrix.
    'opp_adj_iters': 12,
    # Blend toward simple shrunk GF/GA lambdas: h2h aggregates home+away legs, so full opponent-adj only (~1.0)
    # hurts backtest calibration; retune after venue splits (see backtest_predictions).
    # Retuned together with venue helpers (backtest_predictions.py --from-scrape).
    'opp_adj_blend': 0.31,
    # Max fraction of venue split when blending simple λ (home GF/match vs away GA/match, etc.).
    # On our historical backtest, >0 slightly raises mean log loss vs overall GF/GA; leave 0 for best fit,
    # or raise (e.g. 0.12–0.22) if you want sharper home/away scoring at the cost of calibration.
    'venue_split_blend_max': 0.0,
    # After this many combined home_MP + away_MP for the pair, venue weight reaches blend_max.
    'venue_conf_games': 14,
}


def merge_prediction_params(params):
    out = dict(DEFAULT_PREDICTION_PARAMS)
    if params:
        out.update(params)
    return out


def _league_rate_priors(standings, team_names):
    """Mean PPM and GD/match across teams with games played."""
    ppms, gds = [], []
    for n in team_names:
        s = standings[n]
        mp = s['MP']
        if mp > 0:
            ppms.append(s['PTS'] / mp)
            gds.append(s['GD'] / mp)
    if not ppms:
        return 1.35, 0.0
    return sum(ppms) / len(ppms), sum(gds) / len(gds)


def _shrunk_ppm_gdpm(team_row, mu_ppm, mu_gd, pseudo_mp):
    mp = team_row['MP']
    if mp <= 0:
        return mu_ppm, mu_gd
    w = mp / (mp + pseudo_mp)
    w0 = pseudo_mp / (mp + pseudo_mp)
    ppm = (team_row['PTS'] / mp) * w + mu_ppm * w0
    gdpm = (team_row['GD'] / mp) * w + mu_gd * w0
    return ppm, gdpm


def _league_goal_priors(standings, team_names):
    """League-average goals for/against per team-match (GF/MP and GA/MP)."""
    gfs, gas = [], []
    for n in team_names:
        s = standings[n]
        mp = s['MP']
        if mp > 0:
            gfs.append(s['GF'] / mp)
            gas.append(s['GA'] / mp)
    if not gfs:
        return 2.0, 2.0
    return sum(gfs) / len(gfs), sum(gas) / len(gas)


def _shrunk_gf_ga_per_match(team_row, mu_gfpm, mu_gapm, pseudo_mp):
    mp = team_row['MP']
    if mp <= 0:
        return mu_gfpm, mu_gapm
    w = mp / (mp + pseudo_mp)
    w0 = pseudo_mp / (mp + pseudo_mp)
    gfpm = (team_row['GF'] / mp) * w + mu_gfpm * w0
    gapm = (team_row['GA'] / mp) * w + mu_gapm * w0
    return gfpm, gapm


def _shrunk_rate(raw, eff_mp, mu, pseudo_mp):
    """Shrink per-match rate toward league prior using effective games played."""
    eps = 1e-9
    eff_mp = max(0.0, float(eff_mp))
    if eff_mp <= 0:
        return mu
    w = eff_mp / (eff_mp + pseudo_mp)
    return raw * w + mu * (1.0 - w)


def _league_home_away_priors(standings, team_names):
    """League-average goals for/against per match when home vs when away."""
    mu_gf_overall, mu_ga_overall = _league_goal_priors(standings, team_names)
    mu_h_gf, mu_h_ga, mu_a_gf, mu_a_ga = [], [], [], []
    for n in team_names:
        s = standings[n]
        hmp = max(s.get('home_MP', 0), 0)
        amp = max(s.get('away_MP', 0), 0)
        if hmp > 0:
            mu_h_gf.append(s['home_GF'] / hmp)
            mu_h_ga.append(s['home_GA'] / hmp)
        if amp > 0:
            mu_a_gf.append(s['away_GF'] / amp)
            mu_a_ga.append(s['away_GA'] / amp)
    def avg(xs, fallback):
        return sum(xs) / len(xs) if xs else fallback

    # Fallback if no venue splits yet: use overall GF/GA per match.
    return (
        avg(mu_h_gf, mu_gf_overall),
        avg(mu_h_ga, mu_ga_overall),
        avg(mu_a_gf, mu_gf_overall),
        avg(mu_a_ga, mu_ga_overall),
    )


def _shrunk_venue_goal_rates(team_row, mu_h_gf, mu_h_ga, mu_a_gf, mu_a_ga, pseudo_mp):
    """Shrunk home/away GF and GA per match (attack + defensive leak by venue)."""
    mp = max(team_row['MP'], 1e-9)
    hmp = max(team_row.get('home_MP', 0), 0)
    amp = max(team_row.get('away_MP', 0), 0)

    raw_home_gf = team_row['home_GF'] / hmp if hmp > 0 else team_row['GF'] / mp
    raw_home_ga = team_row['home_GA'] / hmp if hmp > 0 else team_row['GA'] / mp
    raw_away_gf = team_row['away_GF'] / amp if amp > 0 else team_row['GF'] / mp
    raw_away_ga = team_row['away_GA'] / amp if amp > 0 else team_row['GA'] / mp

    eff_home = hmp if hmp > 0 else mp
    eff_away = amp if amp > 0 else mp

    return {
        'home_gfpm': _shrunk_rate(raw_home_gf, eff_home, mu_h_gf, pseudo_mp),
        'home_gapm': _shrunk_rate(raw_home_ga, eff_home, mu_h_ga, pseudo_mp),
        'away_gfpm': _shrunk_rate(raw_away_gf, eff_away, mu_a_gf, pseudo_mp),
        'away_gapm': _shrunk_rate(raw_away_ga, eff_away, mu_a_ga, pseudo_mp),
    }


def _poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _geom_mean(vals, eps=1e-9):
    """Geometric mean of positive numbers."""
    if not vals:
        return 1.0
    xs = [max(float(v), eps) for v in vals]
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def _iterative_attack_defense_ratings(h2h, standings, team_names, mu, max_iters):
    """Attack/defense_weakness ratings from pairwise goals (GF_i = Σ_j goals_ij, GA_j = Σ_i goals_ij).

    Expected goals i scores vs j per match ≈ mu * attack[i] * defense[j], with geometric means ~1 after each
    iteration (attack scaled down, defense scaled up so products attack[i]*defense[j] stay unchanged).

    Uses only information already in standings + h2h (same as rest of predictor).
    """
    eps = 1e-9
    teams = [n for n in team_names if n in standings]
    atk = {}
    df = {}
    for i in teams:
        s = standings[i]
        mp = max(s['MP'], eps)
        atk[i] = max(s['GF'] / mp / mu, eps)
        df[i] = max(s['GA'] / mp / mu, eps)

    def games_ij(i, j):
        if i not in h2h or j not in h2h[i]:
            return 0
        x = h2h[i][j]
        return x['W'] + x['L'] + x['T']

    for _ in range(max(1, int(max_iters))):
        atk_new = {}
        for i in teams:
            den = eps
            for j in teams:
                if j == i:
                    continue
                nij = games_ij(i, j)
                if nij > 0:
                    den += nij * df[j]
            atk_new[i] = standings[i]['GF'] / (mu * den)

        df_new = {}
        for j in teams:
            den = eps
            for i in teams:
                if i == j:
                    continue
                nij = games_ij(i, j)
                if nij > 0:
                    den += nij * atk_new[i]
            df_new[j] = standings[j]['GA'] / (mu * den)

        atk = atk_new
        df = df_new

        g = _geom_mean(atk.values())
        if g <= eps:
            break
        for i in teams:
            atk[i] /= g
            df[i] *= g

    return atk, df


def _outcome_probs_from_poisson(lam_home, lam_away, max_goals):
    """Compute P(home/draw/away) by enumerating scorelines up to max_goals (with tail bucket)."""
    # Precompute pmfs up to max_goals-1; last bucket is tail probability.
    h = [_poisson_pmf(k, lam_home) for k in range(max_goals)]
    a = [_poisson_pmf(k, lam_away) for k in range(max_goals)]
    h_tail = max(0.0, 1.0 - sum(h))
    a_tail = max(0.0, 1.0 - sum(a))
    h.append(h_tail)
    a.append(a_tail)

    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = h[i] * a[j]
            if i == j:
                p_draw += p
            elif i > j:
                p_home += p
            else:
                p_away += p
    tot = p_home + p_draw + p_away
    if tot <= 0:
        return 1 / 3, 1 / 3, 1 / 3
    return p_home / tot, p_draw / tot, p_away / tot


def round_predicted_scoreline(raw_home, raw_away):
    """Round each raw estimate to nearest 0.5 goals, then to nearest whole goal (half-up).

    Example: 2.1 and 2.4 -> 2.0 and 2.5 on the half grid -> integer 2 and 3.
    """
    h_half = round(raw_home * 2) / 2
    a_half = round(raw_away * 2) / 2
    hi = int(h_half + 0.5)
    ai = int(a_half + 0.5)
    return float(hi), float(ai)

# Manual results not yet reflected on modular11 (empty when site is current)
MANUAL_RESULTS = {
}


def deduplicate_matches(teams1, teams2):
    """Merge matches from both pages, deduplicating by match_id."""
    all_matches = {}

    for teams in [teams1, teams2]:
        for team in teams:
            for m in team['matches']:
                mid = m['match_id']
                if not mid:
                    continue
                if mid not in all_matches:
                    all_matches[mid] = m
                elif m['score'] and not all_matches[mid]['score']:
                    all_matches[mid] = m

    # Apply manual results
    for mid, override in MANUAL_RESULTS.items():
        if mid in all_matches:
            all_matches[mid]['score'] = override['score']
            if 'home' in override:
                all_matches[mid]['home'] = override['home']
            if 'away' in override:
                all_matches[mid]['away'] = override['away']
            if 'date' in override:
                all_matches[mid]['date'] = override['date']
            if 'venue' in override:
                all_matches[mid]['venue'] = override['venue']
        else:
            # Match not found in HTML at all — add it
            all_matches[mid] = {
                'match_id': mid,
                'date': override.get('date', ''),
                'venue': override.get('venue', ''),
                'home': override['home'],
                'away': override['away'],
                'score': override['score'],
            }

    return list(all_matches.values())


def parse_date(date_str):
    """Parse date string like '09/14/25 06:30pm' into datetime."""
    if not date_str:
        return None
    try:
        # Try with time
        dt = datetime.strptime(date_str, '%m/%d/%y %I:%M%p')
        return dt
    except ValueError:
        try:
            dt = datetime.strptime(date_str.split()[0], '%m/%d/%y')
            return dt
        except ValueError:
            return None


def parse_score(score_str):
    """Parse score like '3 : 1' into (home_goals, away_goals) or None."""
    if not score_str or score_str.strip() in ('', 'TBD', '-'):
        return None
    match = re.match(r'(\d+)\s*:\s*(\d+)', score_str.strip())
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def get_week_start(dt):
    """Get the Monday of the week containing dt."""
    return dt - timedelta(days=dt.weekday())


def rank_teams(ranked, h2h=None):
    """Rank teams using MLS NEXT Regular Season tiebreakers (Division Standings).

    Per league rules (PPM tie): H2H only when exactly two clubs are tied on PPM,
    then wins/MP, GD/MP, GF/MP, away GD/MP, away GF/MP, home GD/MP, home GF/MP.
    Not modeled: disciplinary points, coin toss / drawing of lots.
    """
    from functools import cmp_to_key

    def per_match(val, mp):
        return val / mp if mp > 0 else 0

    def compare_non_h2h(a, b):
        """Negative = a ranks higher. Call only when PPM is already equal."""
        a_wpm = per_match(a['W'], a['MP'])
        b_wpm = per_match(b['W'], b['MP'])
        if abs(a_wpm - b_wpm) > 1e-9:
            return b_wpm - a_wpm

        a_gdpm = per_match(a['GD'], a['MP'])
        b_gdpm = per_match(b['GD'], b['MP'])
        if abs(a_gdpm - b_gdpm) > 1e-9:
            return b_gdpm - a_gdpm

        a_gfpm = per_match(a['GF'], a['MP'])
        b_gfpm = per_match(b['GF'], b['MP'])
        if abs(a_gfpm - b_gfpm) > 1e-9:
            return b_gfpm - a_gfpm

        a_agd = per_match(a.get('away_GF', 0) - a.get('away_GA', 0), a['MP'])
        b_agd = per_match(b.get('away_GF', 0) - b.get('away_GA', 0), b['MP'])
        if abs(a_agd - b_agd) > 1e-9:
            return b_agd - a_agd

        a_agf = per_match(a.get('away_GF', 0), a['MP'])
        b_agf = per_match(b.get('away_GF', 0), b['MP'])
        if abs(a_agf - b_agf) > 1e-9:
            return b_agf - a_agf

        a_hgd = per_match(a.get('home_GF', 0) - a.get('home_GA', 0), a['MP'])
        b_hgd = per_match(b.get('home_GF', 0) - b.get('home_GA', 0), b['MP'])
        if abs(a_hgd - b_hgd) > 1e-9:
            return b_hgd - a_hgd

        a_hgf = per_match(a.get('home_GF', 0), a['MP'])
        b_hgf = per_match(b.get('home_GF', 0), b['MP'])
        if abs(a_hgf - b_hgf) > 1e-9:
            return b_hgf - a_hgf

        return 0

    def compare_two_club_same_ppm(a, b):
        """PPM already equal; H2H applies before wins/GD chain (MLS NEXT)."""
        if h2h and a['team'] in h2h and b['team'] in h2h[a['team']]:
            rec = h2h[a['team']][b['team']]
            a_h2h = rec['W'] * 3 + rec['T']
            b_h2h = rec['L'] * 3 + rec['T']
            if a_h2h != b_h2h:
                return b_h2h - a_h2h
        return compare_non_h2h(a, b)

    ranked.sort(key=lambda r: -r['PPM'])

    out = []
    i = 0
    n = len(ranked)
    while i < n:
        j = i + 1
        while j < n and abs(ranked[j]['PPM'] - ranked[i]['PPM']) < 1e-9:
            j += 1
        group = ranked[i:j]
        if len(group) == 2 and h2h:
            group.sort(key=cmp_to_key(compare_two_club_same_ppm))
        else:
            group.sort(key=cmp_to_key(compare_non_h2h))
        out.extend(group)
        i = j

    ranked[:] = out

    for i, r in enumerate(ranked):
        r['rank'] = i + 1
    return ranked


def build_week_by_week(all_matches, team_names):
    """Build week-by-week data with cumulative standings after each week."""

    # Parse and sort matches by date
    parsed_matches = []
    for m in all_matches:
        dt = parse_date(m['date'])
        if dt:
            parsed_matches.append({**m, '_dt': dt})

    parsed_matches.sort(key=lambda x: x['_dt'])

    # Group by week
    weeks = defaultdict(list)
    for m in parsed_matches:
        week_start = get_week_start(m['_dt'])
        week_key = week_start.strftime('%Y-%m-%d')
        weeks[week_key].append(m)

    # Build cumulative standings week by week
    standings = {name: {
        'PTS': 0, 'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0, 'GD': 0, 'MP': 0,
        'home_MP': 0, 'away_MP': 0,
        'home_GF': 0, 'home_GA': 0, 'away_GF': 0, 'away_GA': 0,
    } for name in team_names}
    # Track head-to-head results
    h2h = defaultdict(lambda: defaultdict(lambda: {'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0}))

    weekly_data = []
    sorted_weeks = sorted(weeks.keys())

    for week_key in sorted_weeks:
        week_matches = weeks[week_key]
        week_end = datetime.strptime(week_key, '%Y-%m-%d') + timedelta(days=6)

        games_this_week = []
        for m in week_matches:
            score = parse_score(m['score'])
            game = {
                'match_id': m['match_id'],
                'date': m['date'],
                'venue': m['venue'],
                'home': m['home'],
                'away': m['away'],
                'score': m['score'],
                'played': score is not None,
            }

            if score is not None:
                hg, ag = score
                home, away = m['home'], m['away']
                game['home_goals'] = hg
                game['away_goals'] = ag
                apply_match_result(home, away, hg, ag, standings, h2h)

            games_this_week.append(game)

        # Build ranked standings snapshot
        ranked = []
        for name in team_names:
            s = standings[name].copy()
            s['PPM'] = round(s['PTS'] / s['MP'], 2) if s['MP'] > 0 else 0
            ranked.append({'team': name, **s})

        rank_teams(ranked, h2h)

        weekly_data.append({
            'week_start': week_key,
            'week_end': week_end.strftime('%Y-%m-%d'),
            'games': games_this_week,
            'standings': ranked,
        })

    return weekly_data, h2h, standings


def apply_match_result(home, away, hg, ag, standings, h2h):
    """Update standings and head-to-head after a finished match (home/away are team names)."""
    if home not in standings or away not in standings:
        return

    standings[home]['MP'] += 1
    standings[home]['home_MP'] += 1
    standings[home]['GF'] += hg
    standings[home]['GA'] += ag
    standings[home]['GD'] = standings[home]['GF'] - standings[home]['GA']
    standings[home]['home_GF'] += hg
    standings[home]['home_GA'] += ag
    if hg > ag:
        standings[home]['W'] += 1
        standings[home]['PTS'] += 3
    elif hg < ag:
        standings[home]['L'] += 1
    else:
        standings[home]['T'] += 1
        standings[home]['PTS'] += 1

    standings[away]['MP'] += 1
    standings[away]['away_MP'] += 1
    standings[away]['GF'] += ag
    standings[away]['GA'] += hg
    standings[away]['GD'] = standings[away]['GF'] - standings[away]['GA']
    standings[away]['away_GF'] += ag
    standings[away]['away_GA'] += hg
    if ag > hg:
        standings[away]['W'] += 1
        standings[away]['PTS'] += 3
    elif ag < hg:
        standings[away]['L'] += 1
    else:
        standings[away]['T'] += 1
        standings[away]['PTS'] += 1

    if hg > ag:
        h2h[home][away]['W'] += 1
        h2h[away][home]['L'] += 1
    elif hg < ag:
        h2h[home][away]['L'] += 1
        h2h[away][home]['W'] += 1
    else:
        h2h[home][away]['T'] += 1
        h2h[away][home]['T'] += 1
    h2h[home][away]['GF'] += hg
    h2h[home][away]['GA'] += ag
    h2h[away][home]['GF'] += ag
    h2h[away][home]['GA'] += hg


def predict_single_match(m, standings, h2h, team_names, params=None):
    """Predict one match from current standings and H2H (no lookahead). Returns None if not predictable."""
    P = merge_prediction_params(params)

    home = m['home']
    away = m['away']
    if home not in standings or away not in standings:
        return None

    home_s = standings[home]
    away_s = standings[away]
    if home_s['MP'] == 0 or away_s['MP'] == 0:
        return None

    mu_ppm, mu_gd = _league_rate_priors(standings, team_names)
    home_ppm, home_gdpm = _shrunk_ppm_gdpm(home_s, mu_ppm, mu_gd, P['shrink_pseudo_mp'])
    away_ppm, away_gdpm = _shrunk_ppm_gdpm(away_s, mu_ppm, mu_gd, P['shrink_pseudo_mp'])

    h2h_home = h2h[home][away]
    h2h_away = h2h[away][home]

    common_home_scores = []
    common_away_scores = []
    for opp in team_names:
        if opp == home or opp == away:
            continue
        home_vs_opp = h2h[home][opp]
        away_vs_opp = h2h[away][opp]
        home_games = home_vs_opp['W'] + home_vs_opp['L'] + home_vs_opp['T']
        away_games = away_vs_opp['W'] + away_vs_opp['L'] + away_vs_opp['T']
        if home_games > 0 and away_games > 0:
            common_home_scores.append((home_vs_opp['W'] * 3 + home_vs_opp['T']) / home_games)
            common_away_scores.append((away_vs_opp['W'] * 3 + away_vs_opp['T']) / away_games)

    has_common_opps = len(common_home_scores) > 0

    if has_common_opps:
        w_ppm, w_gd, w_h2h, w_common = 0.40, 0.25, 0.20, 0.15
    else:
        w_ppm, w_gd, w_h2h, w_common = 0.50, 0.30, 0.20, 0.0

    home_strength = home_ppm * w_ppm + (home_gdpm + 3) * w_gd
    away_strength = away_ppm * w_ppm + (away_gdpm + 3) * w_gd

    h2h_games = h2h_home['W'] + h2h_home['L'] + h2h_home['T']
    h2h_scale = min(1.0, h2h_games / P['h2h_full_games']) if h2h_games > 0 else 0.0
    if h2h_games > 0:
        h2h_home_score = (h2h_home['W'] * 3 + h2h_home['T']) / h2h_games
        h2h_away_score = (h2h_away['W'] * 3 + h2h_away['T']) / h2h_games
        home_strength += h2h_home_score * w_h2h * h2h_scale
        away_strength += h2h_away_score * w_h2h * h2h_scale

    if has_common_opps:
        home_strength += (sum(common_home_scores) / len(common_home_scores)) * w_common
        away_strength += (sum(common_away_scores) / len(common_away_scores)) * w_common

    margin = (home_strength + P['home_strength_bonus']) - away_strength

    # --- Offense/Defense goal model ---
    # Build expected goals from (shrunk) GF/MP of scoring team and GA/MP of conceding team.
    # This is intentionally simple but (a) uses opponent defense, and (b) ties scorelines to W/D/L probs.
    mu_gfpm, mu_gapm = _league_goal_priors(standings, team_names)
    mu_h_gf, mu_h_ga, mu_a_gf, mu_a_ga = _league_home_away_priors(standings, team_names)
    gs = P['goal_shrink_pseudo_mp']
    home_gfpm, home_gapm = _shrunk_gf_ga_per_match(home_s, mu_gfpm, mu_gapm, gs)
    away_gfpm, away_gapm = _shrunk_gf_ga_per_match(away_s, mu_gfpm, mu_gapm, gs)
    v_home = _shrunk_venue_goal_rates(home_s, mu_h_gf, mu_h_ga, mu_a_gf, mu_a_ga, gs)
    v_away = _shrunk_venue_goal_rates(away_s, mu_h_gf, mu_h_ga, mu_a_gf, mu_a_ga, gs)

    over_home = ((home_gfpm + away_gapm) / 2.0) * P['home_goal_mult']
    over_away = (away_gfpm + home_gapm) / 2.0
    ven_home = ((v_home['home_gfpm'] + v_away['away_gapm']) / 2.0) * P['home_goal_mult']
    ven_away = (v_away['away_gfpm'] + v_home['home_gapm']) / 2.0
    conf_g = max(0.0, float(P.get('venue_conf_games', 14)))
    vmax = max(0.0, min(1.0, float(P.get('venue_split_blend_max', 0.38))))
    mp_pair = max(0.0, float(home_s.get('home_MP', 0)) + float(away_s.get('away_MP', 0)))
    vsb = vmax * (min(mp_pair / conf_g, 1.0) if conf_g > 0 else 0.0)
    simple_home = round(vsb * ven_home + (1.0 - vsb) * over_home, 4)
    simple_away = round(vsb * ven_away + (1.0 - vsb) * over_away, 4)

    atk, defw = _iterative_attack_defense_ratings(
        h2h, standings, team_names, mu_gfpm, int(P.get('opp_adj_iters', 12))
    )
    ah = atk.get(home, 1.0)
    aa = atk.get(away, 1.0)
    dh = defw.get(home, 1.0)
    da = defw.get(away, 1.0)
    adj_home = mu_gfpm * ah * da * P['home_goal_mult']
    adj_away = mu_gfpm * aa * dh

    blend = float(P.get('opp_adj_blend', 1.0))
    blend = max(0.0, min(1.0, blend))
    raw_home = round(blend * adj_home + (1.0 - blend) * simple_home, 2)
    raw_away = round(blend * adj_away + (1.0 - blend) * simple_away, 2)

    max_g = int(P.get('poisson_max_goals', 8))
    p_home, p_draw, p_away = _outcome_probs_from_poisson(raw_home, raw_away, max_g)

    h_half = round(raw_home * 2) / 2
    a_half = round(raw_away * 2) / 2
    goal_gap = abs(h_half - a_half)
    blend_denom = max(SCORELINE_BLEND_GAP_UNITS, 0.01)
    blend_w = P['scoreline_blend_max'] * max(0.0, 1.0 - goal_gap / blend_denom)
    td = P['scoreline_target_draw']
    rem_t = 1.0 - td
    t_home = rem_t * 0.5
    t_away = rem_t * 0.5
    p_home = (1.0 - blend_w) * p_home + blend_w * t_home
    p_draw = (1.0 - blend_w) * p_draw + blend_w * td
    p_away = (1.0 - blend_w) * p_away + blend_w * t_away

    pf = P['prob_floor']
    p_home = max(pf, p_home)
    p_draw = max(pf, p_draw)
    p_away = max(pf, p_away)
    tot = p_home + p_draw + p_away
    p_home /= tot
    p_draw /= tot
    p_away /= tot

    if p_home >= p_away and p_home >= p_draw:
        predicted = 'home_win'
    elif p_away >= p_home and p_away >= p_draw:
        predicted = 'away_win'
    else:
        predicted = 'draw'

    est_home_goals, est_away_goals = round_predicted_scoreline(raw_home, raw_away)

    home_strength_report = round(home_strength + P['home_strength_bonus'], 3)
    away_strength_report = round(away_strength, 3)

    return {
        'match_id': m['match_id'],
        'date': m['date'],
        'venue': m.get('venue', ''),
        'home': home,
        'away': away,
        'home_win_prob': round(p_home, 3),
        'away_win_prob': round(p_away, 3),
        'draw_prob': round(p_draw, 3),
        'predicted_outcome': predicted,
        'est_home_goals': est_home_goals,
        'est_away_goals': est_away_goals,
        'home_strength': home_strength_report,
        'away_strength': away_strength_report,
    }


def build_retro_predictions(all_matches, team_names):
    """For each finished match, run predict_single_match on state *before* that result (chronological).

    Used by the frontend weekly table Pred. column for games that already have scores.
    """
    standings = {name: {
        'PTS': 0, 'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0, 'GD': 0, 'MP': 0,
        'home_MP': 0, 'away_MP': 0,
        'home_GF': 0, 'home_GA': 0, 'away_GF': 0, 'away_GA': 0,
    } for name in team_names}
    h2h = defaultdict(lambda: defaultdict(lambda: {'W': 0, 'L': 0, 'T': 0, 'GF': 0, 'GA': 0}))

    parsed = []
    for m in all_matches:
        dt = parse_date(m['date'])
        if dt:
            parsed.append({**m, '_dt': dt})
    parsed.sort(key=lambda x: x['_dt'])

    retro = {}
    for m in parsed:
        score = parse_score(m['score'])
        if score is None:
            continue
        mid = m.get('match_id')
        if not mid:
            continue
        p = predict_single_match(m, standings, h2h, team_names)
        if p:
            retro[str(mid)] = p
        hg, ag = score
        apply_match_result(m['home'], m['away'], hg, ag, standings, h2h)
    return retro


def predict_remaining(all_matches, standings, h2h, team_names):
    """Predict remaining (unplayed) games using goal differential + head-to-head."""

    predictions = []
    for m in all_matches:
        score = parse_score(m['score'])
        if score is not None:
            continue  # already played
        dt = parse_date(m['date'])
        if not dt:
            continue

        p = predict_single_match(m, standings, h2h, team_names)
        if p:
            predictions.append(p)

    return predictions


def simulate_season(predictions, standings, team_names, h2h=None):
    """Simulate rest of season and produce projected final standings."""
    projected = {name: standings[name].copy() for name in team_names}

    for p in predictions:
        home = p['home']
        away = p['away']
        if home not in projected or away not in projected:
            continue

        projected[home]['MP'] += 1
        projected[away]['MP'] += 1
        projected[home]['home_MP'] += 1
        projected[away]['away_MP'] += 1

        if p['predicted_outcome'] == 'home_win':
            projected[home]['W'] += 1
            projected[home]['PTS'] += 3
            projected[away]['L'] += 1
            projected[home]['GF'] += p['est_home_goals']
            projected[home]['GA'] += p['est_away_goals']
            projected[home]['home_GF'] = projected[home].get('home_GF', 0) + p['est_home_goals']
            projected[home]['home_GA'] = projected[home].get('home_GA', 0) + p['est_away_goals']
            projected[away]['GF'] += p['est_away_goals']
            projected[away]['GA'] += p['est_home_goals']
            projected[away]['away_GF'] = projected[away].get('away_GF', 0) + p['est_away_goals']
            projected[away]['away_GA'] = projected[away].get('away_GA', 0) + p['est_home_goals']
        elif p['predicted_outcome'] == 'away_win':
            projected[away]['W'] += 1
            projected[away]['PTS'] += 3
            projected[home]['L'] += 1
            projected[home]['GF'] += p['est_home_goals']
            projected[home]['GA'] += p['est_away_goals']
            projected[home]['home_GF'] = projected[home].get('home_GF', 0) + p['est_home_goals']
            projected[home]['home_GA'] = projected[home].get('home_GA', 0) + p['est_away_goals']
            projected[away]['GF'] += p['est_away_goals']
            projected[away]['GA'] += p['est_home_goals']
            projected[away]['away_GF'] = projected[away].get('away_GF', 0) + p['est_away_goals']
            projected[away]['away_GA'] = projected[away].get('away_GA', 0) + p['est_home_goals']
        else:
            projected[home]['T'] += 1
            projected[away]['T'] += 1
            projected[home]['PTS'] += 1
            projected[away]['PTS'] += 1
            avg = (p['est_home_goals'] + p['est_away_goals']) / 2
            projected[home]['GF'] += avg
            projected[home]['GA'] += avg
            projected[home]['home_GF'] = projected[home].get('home_GF', 0) + avg
            projected[home]['home_GA'] = projected[home].get('home_GA', 0) + avg
            projected[away]['GF'] += avg
            projected[away]['GA'] += avg
            projected[away]['away_GF'] = projected[away].get('away_GF', 0) + avg
            projected[away]['away_GA'] = projected[away].get('away_GA', 0) + avg

    ranked = []
    for name in team_names:
        s = projected[name]
        s['GD'] = round(s['GF'] - s['GA'], 1)
        s['GF'] = round(s['GF'], 1)
        s['GA'] = round(s['GA'], 1)
        s['PPM'] = round(s['PTS'] / s['MP'], 2) if s['MP'] > 0 else 0
        s['home_GF'] = round(s.get('home_GF', 0), 1)
        s['home_GA'] = round(s.get('home_GA', 0), 1)
        s['away_GF'] = round(s.get('away_GF', 0), 1)
        s['away_GA'] = round(s.get('away_GA', 0), 1)
        ranked.append({'team': name, **s})

    rank_teams(ranked, h2h)

    return ranked


def load_from_scrape_rows(scraped_teams, standings_data=None):
    """Load merged matches + standings from scraped team rows (same shape as scraped_matches.json)."""
    all_matches = {}
    team_names = set()
    for t in scraped_teams:
        team_names.add(t['name'])
        for m in t['matches']:
            mid = m['match_id']
            if not mid:
                continue
            if mid not in all_matches:
                all_matches[mid] = m
            elif m['score'] and m['score'].strip() not in ('', 'TBD') and (
                    not all_matches[mid]['score'] or all_matches[mid]['score'].strip() in ('', 'TBD')):
                all_matches[mid] = m

    # Apply manual results
    for mid, override in MANUAL_RESULTS.items():
        if mid in all_matches:
            all_matches[mid]['score'] = override['score']
            for key in ('home', 'away', 'date', 'venue'):
                if key in override:
                    all_matches[mid][key] = override[key]
        else:
            all_matches[mid] = {
                'match_id': mid,
                'date': override.get('date', ''),
                'venue': override.get('venue', ''),
                'home': override['home'],
                'away': override['away'],
                'score': override['score'],
            }

    # Build current standings from standings_data or scraped team order
    current_standings = []
    if standings_data:
        for t in standings_data:
            current_standings.append({
                'team': t['name'],
                'rank': t['rank'],
                **{k: (float(v) if '.' in str(v) else int(v))
                   if str(v).replace('.', '').replace('-', '').isdigit() else 0
                   for k, v in t['stats'].items()},
            })
    else:
        for t in scraped_teams:
            current_standings.append({
                'team': t.get('name', ''),
                'rank': t.get('rank', 0),
            })

    return sorted(team_names), list(all_matches.values()), current_standings


def load_from_scrape(scraped_path, standings_data=None):
    """Load data from scraped_matches.json + optional live standings."""
    with open(scraped_path) as f:
        scraped_teams = json.load(f)
    return load_from_scrape_rows(scraped_teams, standings_data)


def filter_excluded_teams(team_names, all_matches, current_standings):
    """Remove excluded teams and any matches involving them."""
    team_names = [t for t in team_names if t not in EXCLUDED_TEAMS]
    all_matches = [m for m in all_matches if m['home'] not in EXCLUDED_TEAMS and m['away'] not in EXCLUDED_TEAMS]
    current_standings = [s for s in current_standings if s['team'] not in EXCLUDED_TEAMS]
    return team_names, all_matches, current_standings


def make_division_id(league_slug, division_title: str) -> str:
    """URL-safe id, e.g. academy / u13-northern-california-division."""
    s = division_title.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return f"{league_slug}-{s}" if s else league_slug


def build_division_output(
    team_names, all_matches, current_standings, *,
    division, highlight_team, target_rank, division_id=None,
    age_label=None, league=None,
):
    """Run predictions + projections for one division and return the client bundle."""
    weekly_data, h2h, final_standings = build_week_by_week(all_matches, team_names)

    retro_predictions = build_retro_predictions(all_matches, team_names)

    predictions = predict_remaining(all_matches, final_standings, h2h, team_names)

    projected_final = simulate_season(predictions, final_standings, team_names, h2h)

    ht = highlight_team
    glens_current = None
    glens_projected = None
    if ht:
        glens_current = next((s for s in weekly_data[-1]['standings'] if s['team'] == ht), None)
        glens_projected = next((s for s in projected_final if s['team'] == ht), None)

    if glens_current:
        print(
            f"\n  {ht} current: Rank {glens_current['rank']}, {glens_current['PTS']} PTS "
            f"({glens_current['W']}W-{glens_current['L']}L-{glens_current['T']}T)"
        )
    if glens_projected:
        print(
            f"  {ht} projected: Rank {glens_projected['rank']}, {glens_projected['PTS']} PTS "
            f"({glens_projected['W']}W-{glens_projected['L']}L-{glens_projected['T']}T)"
        )

    h2h_serializable = {}
    for t1 in h2h:
        h2h_serializable[t1] = {}
        for t2 in h2h[t1]:
            h2h_serializable[t1][t2] = dict(h2h[t1][t2])

    out = {
        'division': division,
        'highlight_team': highlight_team,
        'target_rank': target_rank,
        'team_names': sorted(team_names),
        'current_standings': current_standings,
        'weekly': weekly_data,
        'predictions': predictions,
        'retro_predictions': retro_predictions,
        'projected_final_standings': projected_final,
        'head_to_head': h2h_serializable,
    }
    if division_id:
        out['id'] = division_id
    if age_label:
        out['age_label'] = age_label
    if league:
        out['league'] = league
    return out


def main():
    import sys
    GLENS = 'San Francisco Glens'
    academy_scrape = '--from-academy-scrape' in sys.argv
    use_scrape = '--from-scrape' in sys.argv and not academy_scrape

    outpath = os.path.join(REPO_ROOT, 'data.json')

    if academy_scrape:
        scrape_bundles = (
            os.path.join(REPO_ROOT, 'scraped_academy.json'),
            os.path.join(REPO_ROOT, 'scraped_homegrown.json'),
        )

        divisions_out = []
        loaded_bundle = False

        for academy_path in scrape_bundles:
            if not os.path.isfile(academy_path):
                print(f"Skipping (missing): {academy_path}")
                continue
            loaded_bundle = True
            print(f"\nLoading scrape bundle: {academy_path}")
            with open(academy_path) as f:
                academy = json.load(f)

            league_slug = (academy.get('league') or 'academy').replace('/', '-')

            for ag in academy.get('age_groups') or []:
                age_label = ag.get('age_label') or ''
                for div_block in ag.get('divisions') or []:
                    div_title = div_block.get('division') or 'Unknown Division'
                    teams_raw = div_block.get('teams') or []
                    scraped_teams = []
                    standings_rows = []
                    for t in teams_raw:
                        scraped_teams.append({
                            'name': t['name'],
                            'matches': t.get('matches') or [],
                        })
                        standings_rows.append({
                            'rank': t['rank'],
                            'name': t['name'],
                            'stats': t.get('stats') or {},
                        })

                    team_names, all_matches, current_standings = load_from_scrape_rows(scraped_teams, standings_rows)

                    if EXCLUDED_TEAMS:
                        team_names, all_matches, current_standings = filter_excluded_teams(
                            team_names, all_matches, current_standings
                        )

                    print(f"\n--- [{league_slug}] {age_label} / {div_title} — {len(team_names)} teams, {len(all_matches)} matches ---")

                    highlight = GLENS if GLENS in team_names else None
                    div_id = make_division_id(league_slug, div_title)

                    print("  Building week-by-week standings...")
                    bundle = build_division_output(
                        team_names, all_matches, current_standings,
                        division=div_title,
                        highlight_team=highlight,
                        target_rank=6,
                        division_id=div_id,
                        age_label=age_label,
                        league=league_slug,
                    )
                    print(f"  {len(bundle['weekly'])} weeks of data")
                    print(f"  {len(bundle['retro_predictions'])} retro predictions; {len(bundle['predictions'])} remaining preds")

                    divisions_out.append(bundle)

        if not loaded_bundle:
            raise SystemExit(
                'No scrape bundles found. Expected at least one of:\n'
                f'  {scrape_bundles[0]}\n'
                f'  {scrape_bundles[1]}\n'
                'Run: python3 scrape_academy.py  and/or  python3 scrape_homegrown.py'
            )

        default_id = None
        for d in divisions_out:
            ht = d.get('highlight_team')
            if ht and ht in (d.get('team_names') or []):
                default_id = d['id']
                break
        if not default_id and divisions_out:
            default_id = divisions_out[0]['id']

        division_catalog = [
            {
                'id': d['id'],
                'age_label': d.get('age_label'),
                'division': d.get('division'),
                'league': d.get('league'),
            }
            for d in divisions_out
        ]

        unique_leagues = sorted({d.get('league') or 'unknown' for d in divisions_out})
        root_league = unique_leagues[0] if len(unique_leagues) == 1 else 'multi'

        root = {
            'schema_version': 2,
            'league': root_league,
            'default_division_id': default_id,
            'division_catalog': division_catalog,
            'divisions': divisions_out,
        }

        with open(outpath, 'w') as f:
            json.dump(root, f, indent=2, default=str)
        print(f"\nJSON written to {outpath}")
        print(f"  Divisions: {len(divisions_out)}, file size: {len(json.dumps(root, default=str)):,} chars")
        return

    if use_scrape:
        print("Loading from scraped data...")
        scraped_path = os.path.join(REPO_ROOT, 'scraped_matches.json')
        standings_path = os.path.join(REPO_ROOT, 'scraped_standings.json')

        standings_data = None
        try:
            with open(standings_path) as f:
                standings_data = json.load(f)
        except FileNotFoundError:
            pass

        team_names, all_matches_list, current_standings = load_from_scrape(scraped_path, standings_data)
        all_matches = all_matches_list
        print(f"  {len(team_names)} teams, {len(all_matches)} unique matches")
        division_label = 'U13 Northern California Division'
    else:
        print("Parsing HTML files...")
        teams1 = parse_standings_file(os.path.join(REPO_ROOT, 'page1.html'))
        teams2 = parse_standings_file(os.path.join(REPO_ROOT, 'page2.html'))
        print(f"  Page 1: {len(teams1)} teams, Page 2: {len(teams2)} teams")

        team_names = list({t['name'] for t in teams1} | {t['name'] for t in teams2})
        team_names.sort()

        all_matches = deduplicate_matches(teams1, teams2)

        current_standings = []
        for t in teams1:
            current_standings.append({
                'team': t['name'],
                'rank': t['rank'],
                **t['stats'],
            })
        division_label = 'U13 Northern California Division'

    if EXCLUDED_TEAMS:
        before = len(team_names)
        team_names, all_matches, current_standings = filter_excluded_teams(team_names, all_matches, current_standings)
        excluded = before - len(team_names)
        if excluded:
            print(f"  Excluded {excluded} team(s): {', '.join(EXCLUDED_TEAMS)}")

    print(f"  Total unique matches: {len(all_matches)}")

    print("Building week-by-week standings...")
    output = build_division_output(
        team_names, all_matches, current_standings,
        division=division_label,
        highlight_team=GLENS,
        target_rank=6,
    )
    print(f"  {len(output['weekly'])} weeks of data")
    print(f"  {len(output['retro_predictions'])} retro predictions; {len(output['predictions'])} remaining preds")

    with open(outpath, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nJSON written to {outpath}")
    print(f"  File size: {len(json.dumps(output, default=str)):,} chars")


if __name__ == '__main__':
    main()

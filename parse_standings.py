#!/usr/bin/env python3
"""Parse U13 Northern California Division soccer standings from HTML files."""

import os
import re

from bs4 import BeautifulSoup


def parse_standings_file(filepath):
    """Parse a single HTML standings file and return teams + matches."""
    with open(filepath, 'r') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    teams = []
    division_rows = soup.find_all('div', class_='container-division-row')

    for div_row in division_rows:
        # Find the main_row for the team
        main_row = div_row.find('div', class_='main_row')
        if not main_row:
            continue

        # Rank
        rank_div = main_row.find('div', class_='container-rank')
        rank = rank_div.get_text(strip=True) if rank_div else ''

        # Team name
        team_p = main_row.find('div', class_='container-team-info')
        team_name = ''
        if team_p:
            p_tag = team_p.find('p', attrs={'data-title': True})
            if p_tag:
                team_name = p_tag['data-title'].strip()

        # Stats - get the desktop stats row (pad-left)
        stats_div = main_row.find('div', class_='pad-left')
        stats = []
        if stats_div:
            stat_divs = stats_div.find_all('div', recursive=False)
            for sd in stat_divs:
                val = sd.get_text(strip=True)
                if val:
                    stats.append(val)

        # Map stats: PTS, PPM, MP, W, L, T, GF, GA, GD
        stat_names = ['PTS', 'PPM', 'MP', 'W', 'L', 'T', 'GF', 'GA', 'GD']
        team_stats = {}
        for i, name in enumerate(stat_names):
            team_stats[name] = stats[i] if i < len(stats) else ''

        # Parse matches (desktop version only - hidden-xs rows)
        matches = []
        evt_matches = div_row.find('div', class_='evt-matches')
        if evt_matches:
            match_rows = evt_matches.find_all('div', class_='table-content-row')
            for mr in match_rows:
                if 'hidden-xs' not in mr.get('class', []):
                    continue

                # Match ID
                match_id_div = mr.find('div', class_='col-sm-1')
                match_id = ''
                if match_id_div:
                    match_id = match_id_div.get_text(strip=True).split('\n')[0].strip()
                    # Remove "MALE" suffix
                    match_id = match_id.replace('MALE', '').strip()

                # Details (date + venue)
                details_div = mr.find('div', class_='col-sm-2')
                date = ''
                venue = ''
                if details_div:
                    # Date is first text node
                    text = details_div.get_text(separator='|', strip=True)
                    parts = text.split('|')
                    if parts:
                        date = parts[0].strip()
                    # Venue from p with data-title
                    venue_p = details_div.find('p', attrs={'data-title': True})
                    if venue_p:
                        venue = venue_p['data-title'].strip()

                # Teams
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

                # Score
                score_span = mr.find('span', class_='score-match-table')
                score = ''
                if score_span:
                    raw = score_span.get_text(strip=True)
                    # Replace &nbsp; encoded as \xa0
                    raw = raw.replace('\xa0', ' ').strip()
                    score = raw

                matches.append({
                    'match_id': match_id,
                    'date': date,
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


def print_standings(teams, label):
    """Print standings table."""
    print(f"\n{'='*100}")
    print(f"  {label}")
    print(f"{'='*100}")
    header = f"{'Rank':>4}  {'Team':<30}  {'PTS':>4}  {'PPM':>5}  {'MP':>3}  {'W':>3}  {'L':>3}  {'T':>3}  {'GF':>3}  {'GA':>3}  {'GD':>4}"
    print(header)
    print('-' * len(header))
    for t in teams:
        s = t['stats']
        print(f"{t['rank']:>4}  {t['name']:<30}  {s['PTS']:>4}  {s['PPM']:>5}  {s['MP']:>3}  {s['W']:>3}  {s['L']:>3}  {s['T']:>3}  {s['GF']:>3}  {s['GA']:>3}  {s['GD']:>4}")


def print_matches(teams, label):
    """Print match results for each team."""
    print(f"\n{'='*100}")
    print(f"  MATCH RESULTS - {label}")
    print(f"{'='*100}")
    for t in teams:
        print(f"\n  [{t['rank']}] {t['name']} ({len(t['matches'])} matches)")
        print(f"  {'-'*90}")
        if not t['matches']:
            print("    No matches found.")
            continue
        for m in t['matches']:
            score_display = m['score'] if m['score'] else 'TBD'
            print(f"    {m['date']:<18}  {m['home']:<25} {score_display:^10} {m['away']:<25}  @ {m['venue']}")


def compare_files(teams1, teams2):
    """Compare two sets of standings and report differences."""
    print(f"\n{'='*100}")
    print(f"  COMPARISON: page1.html vs page2.html")
    print(f"{'='*100}")

    # Compare rankings
    print("\n--- Ranking / Stats Differences ---")
    ranking_diffs = False
    for t1 in teams1:
        t2_match = next((t for t in teams2 if t['name'] == t1['name']), None)
        if not t2_match:
            print(f"  Team '{t1['name']}' only in page1")
            ranking_diffs = True
            continue
        if t1['rank'] != t2_match['rank'] or t1['stats'] != t2_match['stats']:
            ranking_diffs = True
            print(f"\n  {t1['name']}:")
            if t1['rank'] != t2_match['rank']:
                print(f"    Rank: {t1['rank']} -> {t2_match['rank']}")
            for key in t1['stats']:
                if t1['stats'][key] != t2_match['stats'][key]:
                    print(f"    {key}: {t1['stats'][key]} -> {t2_match['stats'][key]}")

    for t2 in teams2:
        t1_match = next((t for t in teams1 if t['name'] == t2['name']), None)
        if not t1_match:
            print(f"  Team '{t2['name']}' only in page2")
            ranking_diffs = True

    if not ranking_diffs:
        print("  Rankings and stats are IDENTICAL between both files.")

    # Compare matches
    print("\n--- Match Differences ---")
    match_diffs = False

    for t1 in teams1:
        t2_match = next((t for t in teams2 if t['name'] == t1['name']), None)
        if not t2_match:
            continue

        matches1_ids = {m['match_id'] for m in t1['matches']}
        matches2_ids = {m['match_id'] for m in t2_match['matches']}

        only_in_1 = matches1_ids - matches2_ids
        only_in_2 = matches2_ids - matches1_ids
        common = matches1_ids & matches2_ids

        if only_in_1 or only_in_2:
            match_diffs = True
            if only_in_1:
                print(f"\n  {t1['name']} - matches only in page1: {only_in_1}")
            if only_in_2:
                print(f"\n  {t1['name']} - matches only in page2: {only_in_2}")

        # Check for score changes in common matches
        for mid in common:
            m1 = next(m for m in t1['matches'] if m['match_id'] == mid)
            m2 = next(m for m in t2_match['matches'] if m['match_id'] == mid)
            if m1['score'] != m2['score']:
                match_diffs = True
                print(f"  {t1['name']} match {mid}: score changed '{m1['score']}' -> '{m2['score']}'")

    if not match_diffs:
        print("  Match lists are identical between both files.")

    # Summary stats
    total_matches_1 = sum(len(t['matches']) for t in teams1)
    total_matches_2 = sum(len(t['matches']) for t in teams2)
    scored_1 = sum(1 for t in teams1 for m in t['matches'] if m['score'] and m['score'] != 'TBD')
    scored_2 = sum(1 for t in teams2 for m in t['matches'] if m['score'] and m['score'] != 'TBD')
    tbd_1 = sum(1 for t in teams1 for m in t['matches'] if m['score'] == 'TBD' or not m['score'])
    tbd_2 = sum(1 for t in teams2 for m in t['matches'] if m['score'] == 'TBD' or not m['score'])

    # Date ranges
    dates1 = [m['date'] for t in teams1 for m in t['matches'] if m['date']]
    dates2 = [m['date'] for t in teams2 for m in t['matches'] if m['date']]

    print(f"\n--- Summary ---")
    print(f"  Page1: {len(teams1)} teams, {total_matches_1} match entries ({scored_1} with scores, {tbd_1} TBD)")
    print(f"  Page2: {len(teams2)} teams, {total_matches_2} match entries ({scored_2} with scores, {tbd_2} TBD)")
    if dates1:
        print(f"  Page1 date range: {min(dates1)} to {max(dates1)}")
    if dates2:
        print(f"  Page2 date range: {min(dates2)} to {max(dates2)}")


def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    print("Parsing page1.html ...")
    teams1 = parse_standings_file(os.path.join(repo_root, 'page1.html'))
    print(f"  Found {len(teams1)} teams")

    print("Parsing page2.html ...")
    teams2 = parse_standings_file(os.path.join(repo_root, 'page2.html'))
    print(f"  Found {len(teams2)} teams")

    # Print standings
    print_standings(teams1, "STANDINGS - page1.html")
    print_standings(teams2, "STANDINGS - page2.html")

    # Print matches
    print_matches(teams1, "page1.html")
    print_matches(teams2, "page2.html")

    # Compare
    compare_files(teams1, teams2)


if __name__ == '__main__':
    main()

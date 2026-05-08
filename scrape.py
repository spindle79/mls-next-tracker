#!/usr/bin/env python3
"""
Scrape U13 NorCal Division standings and all match data from modular11.com,
then rebuild the JSON data and re-embed into index.html.
"""

import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.modular11.com"
STANDINGS_URL = f"{BASE_URL}/league-standings/mls-next-academy-division/21"
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# API params discovered from the site's JS
AGE = 21
TOURNAMENT = 35
LIST_TYPE = "71"
MATCH_ENDPOINT = f"{BASE_URL}/public_schedule/league/get_partial_matches_by_team"


def fetch_standings_page():
    """Fetch the main standings page and extract team info + page 1 matches."""
    print("Fetching standings page...")
    resp = requests.get(STANDINGS_URL)
    resp.raise_for_status()
    return resp.text


def find_norcal_division(html):
    """Find the Northern California Division section and extract team data."""
    soup = BeautifulSoup(html, 'html.parser')

    # Find all standing containers
    containers = soup.find_all('div', class_='container-table-standing')
    norcal = None
    for c in containers:
        title_el = c.find('p', attrs={'data-title': True})
        if title_el and 'Northern California' in title_el.get('data-title', ''):
            norcal = c
            break

    if not norcal:
        raise ValueError("Could not find Northern California Division!")

    teams = []
    div_rows = norcal.find_all('div', class_='container-division-row')

    for div_row in div_rows:
        main_row = div_row.find('div', class_='main_row')
        if not main_row:
            continue

        rank_div = main_row.find('div', class_='container-rank')
        rank = int(rank_div.get_text(strip=True)) if rank_div else 0

        team_info = main_row.find('div', class_='container-team-info')
        team_name = ''
        if team_info:
            p_tag = team_info.find('p', attrs={'data-title': True})
            if p_tag:
                team_name = p_tag['data-title'].strip()

        # Stats: PTS, PPM, MP, W, L, T, GF, GA, GD
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

        # Get row attribute and group for API calls
        row_attr = main_row.get('row', '')
        group_attr = main_row.get('js-group', '')

        # Extract pagination data from the inline script
        pagination_data = []
        evt_matches = div_row.find('div', class_='evt-matches')
        if evt_matches:
            script_tag = evt_matches.find('script')
            if script_tag:
                script_text = script_tag.string or ''
                match = re.search(r'paginationData:\s*\[([\d,\s]+)\]', script_text)
                if match:
                    pagination_data = [int(x.strip()) for x in match.group(1).split(',') if x.strip()]

        # Parse page 1 matches already in the HTML
        page1_matches = parse_matches_from_element(evt_matches) if evt_matches else []

        teams.append({
            'rank': rank,
            'name': team_name,
            'stats': team_stats,
            'row_attr': row_attr,
            'group': group_attr,
            'pagination_data': pagination_data,
            'matches': page1_matches,
        })

    return teams


def parse_matches_from_element(element):
    """Parse match rows from an HTML element (works for both page HTML and AJAX response)."""
    matches = []
    match_rows = element.find_all('div', class_='table-content-row')

    for mr in match_rows:
        if 'hidden-xs' not in mr.get('class', []):
            continue

        # Match ID
        match_id_div = mr.find('div', class_='col-sm-1')
        match_id = ''
        if match_id_div:
            match_id = match_id_div.get_text(strip=True).split('\n')[0].strip().replace('MALE', '').strip()

        # Details (date + venue)
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

    return matches


def parse_matches_from_html(html_str):
    """Parse match rows from an HTML string (AJAX response)."""
    soup = BeautifulSoup(html_str, 'html.parser')
    return parse_matches_from_element(soup)


def fetch_team_matches_page(team, page_num):
    """Fetch a specific page of matches for a team via the API."""
    params = {
        'open_page': page_num,
        'pagination_data': json.dumps(team['pagination_data']),
        'bracket': '',
        'age': AGE,
        'tournament': TOURNAMENT,
        'group': team['group'],
        'list_type': LIST_TYPE,
    }

    resp = requests.get(MATCH_ENDPOINT, params=params)
    resp.raise_for_status()
    return resp.text


def scrape_all_data():
    """Main scraping function — fetch standings + all match pages for all teams."""
    html = fetch_standings_page()

    teams = find_norcal_division(html)
    print(f"Found {len(teams)} teams in NorCal Division")

    for team in teams:
        print(f"  [{team['rank']:>2}] {team['name']:<30} - {len(team['matches'])} page 1 matches, pagination: {team['pagination_data']}")

    # Now fetch page 2 (and beyond) for each team
    for team in teams:
        if not team['pagination_data']:
            print(f"  Skipping {team['name']} - no pagination data")
            continue

        page = 2
        while True:
            print(f"  Fetching page {page} for {team['name']}...")
            try:
                html = fetch_team_matches_page(team, page)
                new_matches = parse_matches_from_html(html)

                if not new_matches:
                    print(f"    No more matches on page {page}")
                    break

                # Check if we got the same matches (end of pagination)
                existing_ids = {m['match_id'] for m in team['matches']}
                truly_new = [m for m in new_matches if m['match_id'] not in existing_ids]

                if not truly_new:
                    print(f"    Page {page} returned duplicate matches, stopping")
                    break

                team['matches'].extend(truly_new)
                print(f"    Got {len(truly_new)} new matches (total: {len(team['matches'])})")

                # Check if there might be more pages
                if len(new_matches) < 10:
                    break

                page += 1
                time.sleep(0.3)  # Be polite

            except Exception as e:
                print(f"    Error fetching page {page}: {e}")
                break

        time.sleep(0.3)

    return teams


def save_scraped_html(teams):
    """Save the scraped data in a format compatible with build_data.py."""
    # Deduplicate all matches across teams
    all_matches = {}
    for team in teams:
        for m in team['matches']:
            mid = m['match_id']
            if not mid:
                continue
            if mid not in all_matches:
                all_matches[mid] = m
            elif m['score'] and not all_matches[mid]['score']:
                all_matches[mid] = m

    # Save raw scraped data
    output = {
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'teams': [{
            'rank': t['rank'],
            'name': t['name'],
            'stats': t['stats'],
            'matches': t['matches'],
        } for t in teams],
        'all_matches': list(all_matches.values()),
    }

    with open(f'{REPO_ROOT}/scraped_data.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nScraped data saved to scraped_data.json")
    print(f"  {len(teams)} teams, {len(all_matches)} unique matches")

    # Count played vs TBD
    played = sum(1 for m in all_matches.values() if m['score'] and m['score'].strip() not in ('', 'TBD'))
    tbd = len(all_matches) - played
    print(f"  {played} played, {tbd} TBD/upcoming")

    # build_data.py --from-scrape expects these filenames
    standings_for_build = []
    matches_for_build = []
    for t in teams:
        standings_for_build.append({
            'rank': t['rank'],
            'name': t['name'],
            'rowAttr': t.get('row_attr', ''),
            'group': t.get('group', ''),
            'paginationData': t.get('pagination_data', []),
            'stats': {k: str(v) for k, v in t['stats'].items()},
        })
        matches_for_build.append({
            'name': t['name'],
            'matchCount': len(t['matches']),
            'matches': t['matches'],
        })

    with open(f'{REPO_ROOT}/scraped_standings.json', 'w') as f:
        json.dump(standings_for_build, f, indent=2)
    with open(f'{REPO_ROOT}/scraped_matches.json', 'w') as f:
        json.dump(matches_for_build, f, indent=2)
    print("  Also wrote scraped_standings.json and scraped_matches.json for build_data.py")

    return output


def _parse_stat_val(raw):
    try:
        return float(raw) if '.' in str(raw) else int(raw)
    except ValueError:
        return 0


def scrape_playwright():
    """Fetch standings + matches after JS render (required as of 2026 — static HTML has no tables)."""
    from playwright.sync_api import sync_playwright

    standings_js = r"""() => {
  const containers = document.querySelectorAll('.container-table-standing');
  for (const c of containers) {
    const title = c.querySelector('.container-group-text p[data-title]');
    if (!title || !title.getAttribute('data-title').includes('Northern California')) continue;

    const teams = [];
    for (const row of c.querySelectorAll('.container-division-row')) {
      const mainRow = row.querySelector('.main_row');
      if (!mainRow) continue;
      const rank = parseInt(mainRow.querySelector('.container-rank')?.textContent?.trim() || '0');
      const name = mainRow.querySelector('.container-team-info p[data-title]')?.getAttribute('data-title')?.trim() || '';
      const statsDiv = mainRow.querySelector('.pad-left');
      const vals = statsDiv ? Array.from(statsDiv.querySelectorAll(':scope > div')).map(d => d.textContent.trim()).filter(Boolean) : [];
      const rowAttr = mainRow.getAttribute('row');
      let paginationData = [];
      if (window.matchLists && window.matchLists[rowAttr]) {
        paginationData = window.matchLists[rowAttr].paginationData;
      }
      teams.push({
        rank, name, rowAttr,
        group: mainRow.getAttribute('js-group'),
        paginationData,
        stats: {
          PTS: vals[0]||'0', PPM: vals[1]||'0', MP: vals[2]||'0', W: vals[3]||'0',
          L: vals[4]||'0', T: vals[5]||'0', GF: vals[6]||'0', GA: vals[7]||'0', GD: vals[8]||'0'
        }
      });
    }
    return JSON.stringify(teams);
  }
  return '[]';
}"""

    matches_js = r"""async () => {
  const scr = [...document.scripts].map(s => s.textContent || '').join('\n');
  const parseIntSafe = (re, def) => {
    const m = scr.match(re);
    return m ? parseInt(m[1], 10) : def;
  };
  const age = parseIntSafe(/\bage\s*=\s*(\d+)/, 21);
  const tournament = parseIntSafe(/\btournament\s*=\s*(\d+)/, 35);
  const lm = scr.match(/list_type\s*=\s*'(\d+)'/);
  const list_type = lm ? lm[1] : '71';

  const containers = document.querySelectorAll('.container-table-standing');
  let norcal = null;
  for (const c of containers) {
    const title = c.querySelector('.container-group-text p[data-title]');
    if (title && title.getAttribute('data-title').includes('Northern California')) { norcal = c; break; }
  }
  if (!norcal) return [];

  const teams = [];
  for (const row of norcal.querySelectorAll('.container-division-row')) {
    const mainRow = row.querySelector('.main_row');
    if (!mainRow) continue;
    const name = mainRow.querySelector('.container-team-info p[data-title]')?.getAttribute('data-title')?.trim() || '';
    const rowAttr = mainRow.getAttribute('row');
    const group = mainRow.getAttribute('js-group');
    let pagData = [];
    if (window.matchLists && window.matchLists[rowAttr]) {
      pagData = window.matchLists[rowAttr].paginationData;
    }
    teams.push({ name, pagData, group });
  }

  function parseMatches(html) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const rows = doc.querySelectorAll('.table-content-row.hidden-xs');
    const matches = [];
    for (const mr of rows) {
      const midDiv = mr.querySelector('.col-sm-1');
      const matchId = midDiv ? midDiv.textContent.trim().split('\n')[0].replace('MALE', '').trim() : '';
      const detailsDiv = mr.querySelector('.col-sm-2');
      let date = '', venue = '';
      if (detailsDiv) {
        const dateMatch = detailsDiv.textContent.trim().match(/(\d{2}\/\d{2}\/\d{2}\s+\d{1,2}:\d{2}[ap]m)/);
        if (dateMatch) date = dateMatch[1];
        const venueP = detailsDiv.querySelector('p[data-title]');
        if (venueP) venue = venueP.getAttribute('data-title').trim();
      }
      const home = mr.querySelector('.container-first-team p[data-title]')?.getAttribute('data-title')?.trim() || '';
      const away = mr.querySelector('.container-second-team p[data-title]')?.getAttribute('data-title')?.trim() || '';
      const scoreSpan = mr.querySelector('.score-match-table');
      const score = scoreSpan ? scoreSpan.textContent.trim().replace(/\u00a0/g, ' ') : '';
      if (matchId) matches.push({ match_id: matchId, date, venue, home, away, score });
    }
    return matches;
  }

  async function fetchPage(pagData, pageNum, group) {
    const params = new URLSearchParams({
      open_page: pageNum,
      pagination_data: JSON.stringify(pagData),
      bracket: '', age, tournament, group, list_type,
    });
    const resp = await fetch('/public_schedule/league/get_partial_matches_by_team?' + params.toString());
    return await resp.text();
  }

  const results = [];
  for (const team of teams) {
    const group = team.group;
    if (!team.pagData || team.pagData.length === 0) {
      results.push({ name: team.name, matchCount: 0, matches: [] });
      continue;
    }
    const allMatches = [];
    const seenIds = new Set();
    let page = 1;
    while (page <= 40) {
      const html = await fetchPage(team.pagData, page, group);
      const matches = parseMatches(html);
      const newMatches = matches.filter(m => !seenIds.has(m.match_id));
      if (newMatches.length === 0) break;
      newMatches.forEach(m => { seenIds.add(m.match_id); allMatches.push(m); });
      if (matches.length < 10) break;
      page++;
    }
    results.push({ name: team.name, matchCount: allMatches.length, matches: allMatches });
  }
  return results;
}"""

    # Project-local browsers (reliable on Apple Silicon; avoid wrong-arch temp cache)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', f'{REPO_ROOT}/.playwright-browsers')

    print("Loading standings page with Playwright (JS-rendered)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(STANDINGS_URL, wait_until='networkidle', timeout=120000)
            page.wait_for_selector('.container-table-standing', timeout=90000)
            page.wait_for_timeout(1500)

            standings_raw = page.evaluate(standings_js)
            standings = json.loads(standings_raw)
            if not standings:
                raise ValueError('No Northern California standings in DOM — page structure may have changed')

            print(f"Found {len(standings)} teams; fetching match pages...")
            match_results = page.evaluate(matches_js)
        finally:
            browser.close()

    matches_by_name = {m['name']: m['matches'] for m in match_results}
    teams = []
    for s in standings:
        name = s['name']
        stat_names = ['PTS', 'PPM', 'MP', 'W', 'L', 'T', 'GF', 'GA', 'GD']
        team_stats = {}
        for kn in stat_names:
            raw = s['stats'].get(kn, '0')
            team_stats[kn] = _parse_stat_val(raw)
        teams.append({
            'rank': s['rank'],
            'name': name,
            'stats': team_stats,
            'row_attr': s.get('rowAttr') or '',
            'group': s.get('group') or '',
            'pagination_data': s.get('paginationData') or [],
            'matches': matches_by_name.get(name, []),
        })

    print(f"Found {len(teams)} teams in NorCal Division")
    for team in teams:
        print(f"  [{team['rank']:>2}] {team['name']:<30} — {len(team['matches'])} matches")
    return teams


if __name__ == '__main__':
    teams = scrape_playwright()
    save_scraped_html(teams)
    print("\nDone! Now run: python3 build_data.py --from-scrape")

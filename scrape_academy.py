#!/usr/bin/env python3
"""
Scrape MLS Next Academy standings for every regional division on modular11.com,
for each age group (U13–U19). Uses Playwright after JS render + in-page fetch for match lists.

Usage:
  python3 scrape_academy.py              # all configured age groups (long run)
  python3 scrape_academy.py --ages 21    # U13 only
  python3 scrape_academy.py --ages 21,22 # U13 + U14
"""

from __future__ import annotations

import argparse
import json
import os
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://www.modular11.com"

# (path_suffix, display label) — IDs from modular11 age dropdown for MLS Next Academy Division
DEFAULT_ACADEMY_AGES = (
    ("21", "U13"),
    ("22", "U14"),
    ("33", "U15"),
    ("14", "U16"),
    ("15", "U17"),
    ("26", "U19"),
)

STANDINGS_JS = r"""() => {
  const divisions = [];
  document.querySelectorAll('.container-table-standing').forEach(container => {
    const titleEl = container.querySelector('.container-group-text p[data-title]');
    const divisionTitle = titleEl ? titleEl.getAttribute('data-title').trim() : '';
    const teams = [];
    container.querySelectorAll('.container-division-row').forEach(row => {
      const mainRow = row.querySelector('.main_row');
      if (!mainRow) return;
      const rank = parseInt(mainRow.querySelector('.container-rank')?.textContent?.trim() || '0', 10);
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
    });
    divisions.push({ divisionTitle, teams });
  });
  return JSON.stringify(divisions);
}"""

MATCHES_JS = r"""async () => {
  const scr = [...document.scripts].map(s => s.textContent || '').join('\n');
  const parseIntSafe = (re, def) => {
    const m = scr.match(re);
    return m ? parseInt(m[1], 10) : def;
  };
  const age = parseIntSafe(/\bage\s*=\s*(\d+)/, 21);
  const tournament = parseIntSafe(/\btournament\s*=\s*(\d+)/, 35);
  const lm = scr.match(/list_type\s*=\s*'(\d+)'/);
  const list_type = lm ? lm[1] : '71';

  const teams = [];
  document.querySelectorAll('.container-table-standing').forEach(container => {
    container.querySelectorAll('.container-division-row').forEach(row => {
      const mainRow = row.querySelector('.main_row');
      if (!mainRow) return;
      const name = mainRow.querySelector('.container-team-info p[data-title]')?.getAttribute('data-title')?.trim() || '';
      const rowAttr = mainRow.getAttribute('row');
      const group = mainRow.getAttribute('js-group');
      let pagData = [];
      if (window.matchLists && window.matchLists[rowAttr]) {
        pagData = window.matchLists[rowAttr].paginationData;
      }
      teams.push({ rowAttr, name, pagData, group });
    });
  });

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
      results.push({ rowAttr: team.rowAttr, name: team.name, matches: [] });
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
    results.push({ rowAttr: team.rowAttr, name: team.name, matches: allMatches });
  }
  return results;
}"""


def _parse_stat_val(raw):
    try:
        return float(raw) if '.' in str(raw) else int(raw)
    except ValueError:
        return 0


def scrape_age_group(
    page,
    age_id: str,
    age_label: str,
    *,
    standings_url: str | None = None,
) -> dict:
    """Return { age_id, age_label, divisions: [...] } for one age."""
    url = standings_url or f"{BASE_URL}/league-standings/mls-next-academy-division/{age_id}"
    print(f"\n=== Age {age_label} ({age_id}) ===\n  {url}")
    page.goto(url, wait_until="networkidle", timeout=120000)
    page.wait_for_selector(".container-table-standing", timeout=90000)
    page.wait_for_timeout(1500)

    divisions_raw = json.loads(page.evaluate(STANDINGS_JS))
    total_teams = sum(len(d.get("teams") or []) for d in divisions_raw)
    print(f"  Divisions: {len(divisions_raw)}, teams: {total_teams}")

    print("  Fetching match lists (per team)...")
    match_rows = page.evaluate(MATCHES_JS)
    by_row = {m["rowAttr"]: m["matches"] for m in match_rows}

    divisions_out = []
    for div in divisions_raw:
        title = div.get("divisionTitle") or ""
        teams_out = []
        for t in div.get("teams") or []:
            row_attr = t.get("rowAttr")
            matches = by_row.get(row_attr, [])
            teams_out.append({
                "rank": t["rank"],
                "name": t["name"],
                "rowAttr": row_attr,
                "group": t.get("group") or "",
                "paginationData": t.get("paginationData") or [],
                "stats": t.get("stats") or {},
                "matches": matches,
            })
        divisions_out.append({"division": title, "teams": teams_out})

    return {"age_id": age_id, "age_label": age_label, "divisions": divisions_out}


def scrape_academy(
    ages: list[tuple[str, str]],
    *,
    outfile: str,
) -> dict:
    from playwright.sync_api import sync_playwright

    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", f"{REPO_ROOT}/.playwright-browsers")

    bundle = {
        "league": "academy",
        "league_url_path": "mls-next-academy-division",
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "age_groups": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            for age_id, age_label in ages:
                ag = scrape_age_group(page, age_id, age_label)
                bundle["age_groups"].append(ag)
        finally:
            browser.close()

    path = outfile if os.path.isabs(outfile) else os.path.join(REPO_ROOT, outfile)
    with open(path, "w") as f:
        json.dump(bundle, f, indent=2)
    print(f"\nWrote {path}")

    total_divs = sum(len(ag["divisions"]) for ag in bundle["age_groups"])
    total_teams = sum(
        len(t["teams"])
        for ag in bundle["age_groups"]
        for t in ag["divisions"]
    )
    print(f"Summary: {len(bundle['age_groups'])} age groups, {total_divs} divisions, {total_teams} team rows")

    return bundle


def parse_args():
    p = argparse.ArgumentParser(description="Scrape full MLS Next Academy modular11 standings + matches.")
    p.add_argument(
        "--ages",
        type=str,
        default="",
        help="Comma-separated age path IDs (e.g. 21,22). Default: all U13–U19 academy ages.",
    )
    p.add_argument(
        "-o",
        "--output",
        default="scraped_academy.json",
        help="Output JSON path (default: scraped_academy.json)",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if args.ages.strip():
        wanted = {x.strip() for x in args.ages.split(",") if x.strip()}
        ages = [(aid, lab) for aid, lab in DEFAULT_ACADEMY_AGES if aid in wanted]
        missing = wanted - {aid for aid, _ in ages}
        if missing:
            raise SystemExit(f"Unknown age id(s): {missing}. Known: { [a for a,_ in DEFAULT_ACADEMY_AGES] }")
    else:
        ages = list(DEFAULT_ACADEMY_AGES)

    scrape_academy(ages, outfile=args.output)
    print("\nNext: python3 build_data.py --from-academy-scrape")


if __name__ == "__main__":
    main()

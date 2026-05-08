#!/usr/bin/env python3
"""
Scrape MLS Next Homegrown division standings on modular11.com (query-based URL, not /league-standings/...).
Same DOM + in-page match API as Academy; only the entry URL differs.

Base: https://www.modular11.com/standings?year=21&gender=1
  year  — same age path IDs as Academy (21=U13, 22=U14, ...)
  gender — modular11 gender filter (1 typical for MLS NEXT listings on this site)

Usage:
  python3 scrape_homegrown.py              # all configured age groups
  python3 scrape_homegrown.py --ages 21    # U13 only
  python3 scrape_homegrown.py --gender 2   # if site uses another gender code
"""

from __future__ import annotations

import argparse
import json
import os
import time

from scrape_academy import BASE_URL, DEFAULT_ACADEMY_AGES, scrape_age_group

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = "scraped_homegrown.json"


def scrape_homegrown(
    ages: list[tuple[str, str]],
    *,
    gender: str,
    outfile: str,
) -> dict:
    from playwright.sync_api import sync_playwright

    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", f"{REPO_ROOT}/.playwright-browsers")

    bundle = {
        "league": "homegrown",
        "standings_query": {"gender": gender},
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "age_groups": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            for age_id, age_label in ages:
                standings_url = f"{BASE_URL}/standings?year={age_id}&gender={gender}"
                ag = scrape_age_group(page, age_id, age_label, standings_url=standings_url)
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
    p = argparse.ArgumentParser(description="Scrape MLS Next Homegrown modular11 standings + matches.")
    p.add_argument(
        "--ages",
        type=str,
        default="",
        help="Comma-separated age path IDs (e.g. 21,22). Default: same set as Academy (U13–U19).",
    )
    p.add_argument(
        "--gender",
        type=str,
        default="1",
        help="Gender query parameter for /standings (default 1 — matches MLS NEXT standings URL).",
    )
    p.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if args.ages.strip():
        wanted = {x.strip() for x in args.ages.split(",") if x.strip()}
        ages = [(aid, lab) for aid, lab in DEFAULT_ACADEMY_AGES if aid in wanted]
        missing = wanted - {aid for aid, _ in ages}
        if missing:
            raise SystemExit(f"Unknown age id(s): {missing}. Known: {[a for a, _ in DEFAULT_ACADEMY_AGES]}")
    else:
        ages = list(DEFAULT_ACADEMY_AGES)

    scrape_homegrown(ages, gender=args.gender, outfile=args.output)
    print("\nNext: merge into data.json with:")
    print("  python3 build_data.py --from-academy-scrape")


if __name__ == "__main__":
    main()

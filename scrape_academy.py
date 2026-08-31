#!/usr/bin/env python3
"""
Scrape MLS NEXT Academy standings + schedule for every division and age group
from the MLS Assist league viewer (theintelligenceplatform.com).

The viewer is a static-JSON SPA: the whole season ships in two unfiltered
files, so there is no browser automation and no pagination to walk. The
squads/clubs/from/to query params in a viewer URL are client-side filters only.

  /data/schedule/<season-key>.json    every match, whole season
  /data/standings/<season-key>.json   position + tiebreaker values per squad

The two feeds are joined on `squad_id`. Team and division names are taken from
the standings feed, which is authoritative: the schedule feed's own `division`
field disagrees with it (e.g. "South California" vs "Southern California", and
it files a block of "North" games under "Great Lakes North").

Usage:
  python3 scrape_academy.py                  # all age groups (one HTTP fetch each feed)
  python3 scrape_academy.py --ages U14       # U14 only
  python3 scrape_academy.py --ages U13,U14   # U13 + U14
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://mls-assist.theintelligenceplatform.com"
DEFAULT_SEASON_KEY = "mls-next-2-academy-division-26-27"

# Age groups carried by the Academy Division feed, in display order.
DEFAULT_ACADEMY_AGES = ("U13", "U14", "U15", "U16", "U17", "U19")

# stats key -> tiebreaker key in the standings feed. GF/GA/GD are absent there
# (it publishes per-match rates instead) and are summed from the match results.
FEED_STAT_KEYS = {
    "PTS": "points",
    "PPM": "points_per_match_penalty_shootout",
    "MP": "matches_played",
    "W": "won",
    "L": "loss",
    "T": "tie",
}

REQUEST_TIMEOUT = 120


def fetch_json(url: str) -> dict:
    print(f"  GET {url}")
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": "application/json"})
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "json" not in ctype:
        # The SPA serves index.html for any unknown path rather than a 404.
        raise SystemExit(
            f"Expected JSON from {url} but got {ctype!r} ({len(resp.content)} bytes).\n"
            "The season key is probably wrong — check --season-key."
        )
    print(f"    {len(resp.content) / 1e6:.1f} MB")
    return resp.json()


def format_kickoff(event: dict) -> str:
    """UTC start_time -> local wall clock as 'MM/DD/YY HH:MMam' (build_data's format)."""
    raw = event.get("start_time")
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    tz = event.get("local_timezone")
    if tz:
        try:
            dt = dt.astimezone(ZoneInfo(tz))
        except Exception:
            pass
    return dt.strftime("%m/%d/%y %I:%M%p").lower()


def format_score(event: dict) -> str:
    """'3 : 1' for a played match, '' for one not yet played (build_data's format)."""
    home, away = event.get("home_score"), event.get("away_score")
    if not event.get("completed") or home is None or away is None:
        return ""
    return f"{home} : {away}"


def build_squad_index(standings: dict) -> tuple[dict, dict]:
    """Map squad_id -> bracket key, and bracket key -> ordered standings rows."""
    season = standings.get("competition_season") or {}
    brackets = season.get("competition_brackets") or []

    squad_to_bracket: dict[int, tuple[str, str]] = {}
    bracket_rows: dict[tuple[str, str], list[dict]] = {}

    for bracket in brackets:
        age_label = ((bracket.get("age_group") or {}).get("name") or "").strip()
        division = (bracket.get("name") or "").strip()
        if not age_label or not division:
            continue
        key = (age_label, division)
        rows = []
        for row in bracket.get("standings") or []:
            team = row.get("team") or {}
            squad_id = team.get("squad_id")
            name = (team.get("name") or "").strip()
            if squad_id is None or not name:
                continue
            squad_to_bracket[squad_id] = key
            rows.append(
                {
                    "squad_id": squad_id,
                    "name": name,
                    "position": row.get("position") or 0,
                    "tiebreaker_values": row.get("tiebreaker_values") or {},
                }
            )
        bracket_rows[key] = rows

    return squad_to_bracket, bracket_rows


def group_matches(events: list[dict], squad_to_bracket: dict) -> tuple[dict, list, int]:
    """Bucket events into brackets. Only games where both squads share a bracket count."""
    by_bracket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    unknown_squads: set[tuple] = set()
    cross_bracket = 0

    for event in events:
        home_key = squad_to_bracket.get(event.get("home_squad_id"))
        away_key = squad_to_bracket.get(event.get("away_squad_id"))

        for side in ("home", "away"):
            if squad_to_bracket.get(event.get(f"{side}_squad_id")) is None:
                unknown_squads.add(
                    (
                        event.get(f"{side}_squad_name") or "?",
                        (event.get(f"{side}_organisation") or {}).get("name") or "?",
                    )
                )

        if home_key is None or away_key is None:
            continue
        if home_key != away_key:
            # Interleague / showcase fixture. Excluded so a division's matches stay
            # self-consistent — and the standings feed excludes them too.
            cross_bracket += 1
            continue

        by_bracket[home_key].append(
            {
                "match_id": str(event.get("game_key") or event.get("id") or ""),
                "date": format_kickoff(event),
                "venue": ((event.get("event_location") or {}).get("name") or "").strip(),
                "home": ((event.get("home_organisation") or {}).get("name") or "").strip(),
                "away": ((event.get("away_organisation") or {}).get("name") or "").strip(),
                "score": format_score(event),
                "home_squad_id": event.get("home_squad_id"),
                "away_squad_id": event.get("away_squad_id"),
            }
        )

    return by_bracket, sorted(unknown_squads), cross_bracket


def goal_totals(matches: list[dict]) -> dict[int, dict[str, int]]:
    """Sum GF/GA/MP per squad_id from played matches."""
    totals: dict[int, dict[str, int]] = defaultdict(lambda: {"GF": 0, "GA": 0, "MP": 0})
    for m in matches:
        if not m["score"]:
            continue
        home_goals, away_goals = (int(x.strip()) for x in m["score"].split(":"))
        home, away = totals[m["home_squad_id"]], totals[m["away_squad_id"]]
        home["GF"] += home_goals
        home["GA"] += away_goals
        home["MP"] += 1
        away["GF"] += away_goals
        away["GA"] += home_goals
        away["MP"] += 1
    return totals


def build_division(division: str, rows: list[dict], matches: list[dict], warnings: list[str]) -> dict:
    """One division block in the scrape bundle: ranked teams with stats + match lists."""
    totals = goal_totals(matches)
    by_squad: dict[int, list[dict]] = defaultdict(list)
    for m in matches:
        by_squad[m["home_squad_id"]].append(m)
        by_squad[m["away_squad_id"]].append(m)

    teams = []
    for row in sorted(rows, key=lambda r: r["position"] or 0):
        squad_id = row["squad_id"]
        tb = row["tiebreaker_values"]
        stats = {}
        for abbr, feed_key in FEED_STAT_KEYS.items():
            stats[abbr] = str((tb.get(feed_key) or {}).get("value") or "0")

        goals = totals.get(squad_id, {"GF": 0, "GA": 0, "MP": 0})
        stats["GF"] = str(goals["GF"])
        stats["GA"] = str(goals["GA"])
        stats["GD"] = str(goals["GF"] - goals["GA"])

        # The feed's own matches_played should equal the played games we found.
        if stats["MP"].isdigit() and int(stats["MP"]) != goals["MP"]:
            warnings.append(
                f"{division} / {row['name']}: feed MP={stats['MP']} but "
                f"{goals['MP']} played matches found"
            )

        teams.append(
            {
                "rank": row["position"],
                "name": row["name"],
                "stats": stats,
                "matches": [
                    {k: v for k, v in m.items() if k not in ("home_squad_id", "away_squad_id")}
                    for m in sorted(by_squad.get(squad_id, []), key=lambda x: x["date"])
                ],
            }
        )

    return {"division": division, "teams": teams}


def scrape_academy(ages, season_key=DEFAULT_SEASON_KEY, outfile="scraped_academy.json"):
    print(f"Season: {season_key}")
    print("Fetching standings feed...")
    standings = fetch_json(f"{BASE_URL}/data/standings/{season_key}.json")
    print("Fetching schedule feed...")
    schedule = fetch_json(f"{BASE_URL}/data/schedule/{season_key}.json")

    events = schedule.get("events") or []
    squad_to_bracket, bracket_rows = build_squad_index(standings)
    print(f"\n{len(events)} events, {len(squad_to_bracket)} squads, {len(bracket_rows)} divisions in feed")

    by_bracket, unknown_squads, cross_bracket = group_matches(events, squad_to_bracket)
    if cross_bracket:
        print(f"Skipped {cross_bracket} cross-division fixtures")
    if unknown_squads:
        print(f"Skipped {len(unknown_squads)} squad(s) with no standings row:")
        for squad_name, club in unknown_squads:
            print(f"    {club} ({squad_name})")

    wanted = list(ages)
    warnings: list[str] = []
    bundle = {
        "league": "academy",
        "source": f"{BASE_URL}/data/schedule/{season_key}.json",
        "season_key": season_key,
        "synced_at": schedule.get("synced_at") or "",
        "age_groups": [],
    }

    for age_label in wanted:
        divisions = []
        for (bracket_age, division), rows in sorted(bracket_rows.items()):
            if bracket_age != age_label:
                continue
            block = build_division(division, rows, by_bracket.get((bracket_age, division), []), warnings)
            divisions.append(block)
            played = sum(1 for m in by_bracket.get((bracket_age, division), []) if m["score"])
            total = len(by_bracket.get((bracket_age, division), []))
            print(f"  {age_label:<4} {division:<30} {len(block['teams']):>3} teams  {total:>3} matches ({played} played)")
        if not divisions:
            print(f"  {age_label}: no divisions found")
        bundle["age_groups"].append({"age_label": age_label, "divisions": divisions})

    if warnings:
        print(f"\n{len(warnings)} stat mismatch warning(s):")
        for w in warnings[:20]:
            print(f"    {w}")

    path = outfile if os.path.isabs(outfile) else os.path.join(REPO_ROOT, outfile)
    with open(path, "w") as f:
        json.dump(bundle, f, indent=2)
    print(f"\nWrote {path}")

    total_divs = sum(len(ag["divisions"]) for ag in bundle["age_groups"])
    total_teams = sum(len(d["teams"]) for ag in bundle["age_groups"] for d in ag["divisions"])
    print(f"Summary: {len(bundle['age_groups'])} age groups, {total_divs} divisions, {total_teams} team rows")

    return bundle


def parse_args():
    p = argparse.ArgumentParser(
        description="Scrape MLS NEXT Academy standings + schedule from the MLS Assist league viewer."
    )
    p.add_argument(
        "--ages",
        type=str,
        default="",
        help=f"Comma-separated age labels (e.g. U14 or U13,U14). Default: all ({','.join(DEFAULT_ACADEMY_AGES)}).",
    )
    p.add_argument(
        "--season-key",
        default=DEFAULT_SEASON_KEY,
        help=f"Competition season key in the feed URL (default: {DEFAULT_SEASON_KEY}).",
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
        requested = [x.strip().upper() for x in args.ages.split(",") if x.strip()]
        requested = ["U" + x if x.isdigit() else x for x in requested]
        ages = [a for a in DEFAULT_ACADEMY_AGES if a in requested]
        missing = set(requested) - set(ages)
        if missing:
            raise SystemExit(
                f"Unknown age label(s): {sorted(missing)}. Known: {list(DEFAULT_ACADEMY_AGES)}"
            )
    else:
        ages = list(DEFAULT_ACADEMY_AGES)

    scrape_academy(ages, season_key=args.season_key, outfile=args.output)
    print("\nNext: python3 build_data.py --from-academy-scrape")


if __name__ == "__main__":
    main()

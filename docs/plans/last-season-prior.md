# Last Season as a Prior

How to fold prior-season results into the prediction model as a weak, self-erasing prior — one that
gives the model something to say in week one, and gets out of the way as this season's results
arrive.

> Shareable version: <https://claude.ai/code/artifact/6266bf13-5b12-4369-a91f-6b3635687486>

## The shape of it

The model already shrinks each team's rate toward the league mean by a pseudo-match count.
Prior-season data slots into that same weighted average as a _third_ term, so no new decay machinery
is needed: last season's weight is a fixed budget of pseudo-matches that this season's real matches
dilute automatically. With the recommended settings, last season carries **41% of the signal before a
ball is kicked, under 5% after eight matches, and 0.2% by season's end.**

Two things make or break it, and neither is the arithmetic: deciding **which** of last year's teams
counts as "the same team" when the players have all aged up, and **normalizing across divisions**
before any number is transferred.

## Before anything else

**We don't have last season's data, and it can't be re-scraped.** modular11 still answers on the old
URLs but has been emptied — every endpoint renders "There are no teams" with zero standings rows. The
new platform has no 25/26 feed either; every candidate season key returns the SPA's HTML fallback
instead of JSON. So Phase 0 is acquisition, and if 25/26 never turns up, everything below still pays
off for 26/27 → 27/28 — provided we start archiving now.

---

## P0 — Get a season of history, or start banking one

_Blocking · half a day_

Two independent tracks. The first may fail; the second cannot, and is worth doing regardless of
whether the first succeeds.

### Track A — recover 25/26

The only surviving copies would be artifacts that were never committed (`data.json` and
`scraped_academy.json` are both gitignored). Worth checking, in descending order of likelihood: a
previous local checkout or backup on the machine that ran last season's refreshes; a live Vercel
deployment, whose `public/divisions/*.json` shards are publicly fetchable and would reconstruct the
whole season; the Vercel build cache or a deployment rollback. A last-season shard is a complete
substitute for a re-scrape — it already contains the final standings and every result.

### Track B — start archiving 26/27 today

The current feeds are a complete season snapshot in two files, and they are cheap to keep: the
schedule feed is 12.7 MB and the standings feed 1.3 MB. A weekly archive of both, timestamped by the
feed's own `synced_at`, gives us next season's prior for free — and, as a bonus, a real week-by-week
history of how standings actually evolved rather than one reconstructed from final results.

```bash
# archive_feeds.sh — keep the raw feeds, compressed, keyed by sync time
KEY=mls-next-2-academy-division-26-27
BASE=https://mls-assist.theintelligenceplatform.com/data
STAMP=$(date -u +%Y-%m-%d)
for KIND in schedule standings; do
  curl -sf "$BASE/$KIND/$KEY.json" | gzip > "archive/$KIND-$KEY-$STAMP.json.gz"
done
```

Compressed, a full season of weekly captures runs well under a gigabyte. Store it outside the repo —
these are inputs, and the repo's convention is that inputs stay gitignored.

---

## P1 — Decide which team last year is "the same team"

_The real modeling question · one day_

This is where the plan earns or loses its value, and it's the direct consequence of the fact that the
players change year to year. For a club's U14 side in 26/27 there are three different things last
season could tell us, and they are _not_ the same signal:

| Predictor                                                  | What it actually measures                                                                    | Roster overlap               |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------- |
| **Cohort carry-up** — club's U13 in 25/26 → U14 in 26/27   | The same children, one year older. Tracks the playing group itself.                          | High — mostly the same names |
| **Same-age program** — club's U14 in 25/26 → U14 in 26/27  | How good this club's U14 team tends to be: coaching, facilities, local pipeline.             | Near zero — a fresh intake   |
| **Club-wide strength** — club's mean across all ages 25/26 | Institutional strength. Noisiest per-team signal but by far the most stable. **Start here.** | Partial, across six squads   |

The instinct is that cohort carry-up must be strongest — it follows the same players. Two things
argue for starting with club-wide strength instead. It averages six squads, so it is far less noisy
than any single team's 18-match record. And it degrades gracefully at exactly the points where the
age ladder breaks: **U13 has no predecessor at all** (it is the intake year), and **U17 → U19 is a
two-year jump** with no U18 division, so cohort carry-up is simply undefined for two of the six age
groups.

Build all three as separate columns and let the backtest weight them. The recommendation is about
which to ship first, not which to compute.

---

## P2 — Normalize before transferring anything

_Correctness prerequisite · half a day_

A raw rate cannot cross seasons. A team that took 2.4 points per match in Mountain (8 teams) is not
demonstrably better than one that took 2.0 in Pioneer (21 teams) — the schedules aren't comparable,
and divisions are realigned between seasons anyway. Transfer a _position relative to the division_,
then re-express it against this season's division:

```python
# last season, within that team's own division
z = (ppm_team_lastyr - mean_ppm_division_lastyr) / stdev_ppm_division_lastyr

# this season, re-expressed against the division the team is in NOW
hist_ppm = mean_ppm_division_thisyr + LAMBDA * z * stdev_ppm_division_thisyr
```

`LAMBDA` (λ) is a regression-to-the-mean factor applied at the source, and it is the second place the
"little weight" requirement gets encoded. Even a perfectly measured z-score from last year overstates
a new cohort's strength, so λ ≈ 0.3–0.5 deliberately pulls every historical estimate most of the way
back to average before it is ever used. λ = 0 makes the whole feature a no-op, which is a useful
ablation for the backtest.

Divisions with fewer than about six teams, or a near-zero spread, should skip the transfer and fall
back to the league mean rather than divide by a tiny standard deviation.

---

## P3 — One weighted average, three terms

_The mechanism · one day_

The model already does exactly this with two terms. Today, in `_shrunk_ppm_gdpm`:

```python
w  = mp / (mp + pseudo_mp)
w0 = pseudo_mp / (mp + pseudo_mp)
ppm = (team_row['PTS'] / mp) * w + mu_ppm * w0
```

That is a weighted average of the observed rate (weight `mp`) and the league mean (weight
`pseudo_mp`). Last season becomes a third term with its own pseudo-match budget φ, and the league
mean's budget is renamed κ:

```python
# phi_eff decays explicitly, so history does not merely thin out — it leaves
phi_eff = PHI * math.exp(-mp / TAU)          # PHI=2.0, TAU=6.0
total   = mp + phi_eff + KAPPA               # KAPPA=2.93 (was shrink_pseudo_mp)

ppm = (obs_ppm  * mp
     + hist_ppm * phi_eff                    # from P2, already λ-regressed
     + mu_ppm   * KAPPA) / total
```

Three properties fall out for free. Every weight is non-negative and they sum to one, so the result
stays a valid rate. At `mp = 0` the observed term vanishes and the team is described entirely by
history plus league mean — which is what lets us predict in week one. And history's share falls
monotonically as matches accumulate, with no schedule to maintain.

### Why the explicit decay term

Plain Bayesian dilution alone leaves a floor: with a fixed φ = 2, last season still holds **7.4%** of
the signal after 22 matches, because φ never shrinks relative to a finite season. The
`exp(-mp / TAU)` factor drives it to 0.2% instead. Given that this year's U14 team shares almost no
players with last year's, a hard fade is the honest choice.

### Weight schedule

Share of each team's strength estimate, at φ = 2.0, τ = 6.0, κ = 2.93:

| Matches played | This season | Last season | League mean |
| -------------: | ----------: | ----------: | ----------: |
|              0 |        0.0% |       40.6% |       59.4% |
|              1 |       17.8% |       30.1% |       52.1% |
|              2 |       31.4% |       22.5% |       46.0% |
|              3 |       42.0% |       17.0% |       41.0% |
|              4 |       50.3% |       12.9% |       36.8% |
|              6 |       62.1% |        7.6% |       30.3% |
|              8 |       69.8% |        4.6% |       25.6% |
|             10 |       75.1% |        2.8% |       22.0% |
|             14 |       81.8% |        1.1% |       17.1% |
|             18 |       85.6% |        0.5% |       13.9% |
|             22 |       88.1% |        0.2% |       11.7% |

Last season's share never rises: it is a fixed pseudo-match budget that real matches dilute,
multiplied by an explicit decay so it fades rather than merely thinning.

### Where it touches the code

| Location                                      | Change                                                                                                                                                                                                                                               |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DEFAULT_PREDICTION_PARAMS`                   | Add `hist_pseudo_mp` (φ), `hist_decay_tau` (τ), `hist_regress_lambda` (λ). All default to a no-op so behavior is unchanged until history is supplied.                                                                                                |
| `_shrunk_ppm_gdpm`, `_shrunk_gf_ga_per_match` | Accept an optional per-team historical estimate and apply the three-term average. These two functions are the only places rates are shrunk, so this is the whole mechanism.                                                                          |
| `predict_single_match`                        | Relax the `if home_s['MP'] == 0 or away_s['MP'] == 0: return None` gate to allow a prediction when a historical estimate exists. This is the visible payoff — 26/27 currently produces almost no predictions because nearly every team is at MP = 0. |
| `build_division_output`                       | Thread an optional `history` argument through to the predictor.                                                                                                                                                                                      |
| Scrape bundle schema                          | Add an optional top-level `history` block keyed by club identity. Absent history must remain valid — all 120 divisions build today with none.                                                                                                        |

---

## P4 — Match clubs across seasons without trusting names

_Plumbing · half a day_

Within the current platform this is easy: `organisation_id` is stable and already joins cleanly — the
Glens are `1425` in both the schedule and standings feeds. Key the history block on
`(organisation_id, age_group)` and the 26/27 → 27/28 case needs nothing else.

Bridging _to_ modular11 data is the hard case, because that source has no stable ids — only names,
and names drift. We already have a live example: the club is `San Francisco Glens` on modular11 and
`San Francisco Glens SC` on the new platform. That one rename silently broke the focus-team highlight
during the source migration, and it will silently drop history rows the same way.

So: normalize aggressively (casefold, strip `SC`/`FC`/`Soccer Club`/`Academy` suffixes, collapse
punctuation), match on the normalized form, and keep an explicit `CLUB_ALIASES` table for the rest.
Critically, make the loader **report unmatched clubs by name** rather than skipping them quietly —
the same convention the rewritten scraper uses for squads with no standings row. A silent 30% miss
rate would look exactly like a weak feature.

Never key on division. Divisions are realigned between seasons, and the division a team played in
last year tells us nothing about where its id lives this year.

---

## P5 — Prove it helps early without hurting later

_Proof · one to two days_

`backtest_predictions.py` already walks the season week by week using only information available
before each week, and reports `mean_log_loss` and `accuracy_pick_max_prob`. One change makes it able
to answer the question that matters here: **bucket the results by the matches-played count at
prediction time.** A single season-wide average will hide the effect entirely, because the whole
benefit is concentrated in the weeks when MP is small.

| Bucket                | Hist. share | Bar to clear                                                |
| --------------------- | ----------: | ----------------------------------------------------------- |
| MP 0 (no results yet) |         41% | Predictions exist at all — today there are none             |
| MP 1–3                |      30–17% | Log loss improves materially; this is the target            |
| MP 4–7                |       13–6% | Small improvement or neutral                                |
| MP 8+                 |        < 5% | **No regression.** A loss here means φ or τ is too generous |

Then extend `random_params` and `clamp_params` in `tune_prediction_params.py` to search φ, τ and λ
alongside the existing parameters, and always run λ = 0 as the ablation baseline — if tuned φ and τ
can't beat λ = 0, the feature isn't earning its complexity and should not ship.

Worth adding as a unit test rather than trusting the tuner: assert that the historical share is below
5% once MP ≥ 8, for whatever φ and τ the tuner lands on. The tuner optimizes average log loss and
would happily buy a small early-season gain with a late-season prior that overstays.

---

## Known failure modes

**Nothing to tune against yet** (high) — 26/27 has 37 completed matches out of 13,705. Tuning φ, τ and
λ on that would fit noise, and 25/26 is exactly the season we don't have. Build the mechanism now with
conservative hand-set defaults (φ = 2, τ = 6, λ = 0.4) and tune only once a few hundred matches exist.

**Silent identity misses** (high) — A name-matching bridge that quietly drops a third of clubs
produces a feature that measures nothing and backtests as neutral. Report unmatched clubs loudly and
treat the match rate as a shipping gate, not a diagnostic.

**Cohort assumption inverted** (medium) — Cohort carry-up may turn out weaker than same-age program
strength: clubs with strong coaching stay strong at U14 every year, while a specific talented group
can move on. This is why all three predictors get computed and the backtest picks, rather than the
other way round.

**Division strength is not stable** (medium) — A team can be realigned into a much stronger division
between seasons, making even a correctly transferred z-score misleading. The λ regression limits the
damage; large realignments are worth detecting and zeroing out explicitly.

**Week-one predictions read as more certain than they are** (low) — Relaxing the MP = 0 gate means the
UI will show confident-looking probabilities built almost entirely from a prior. The existing
`prob_floor` limits the extremes, but the Predictions panel should mark low-information predictions
rather than presenting them identically to ones backed by real results.

---

## Order of work

P0 Track B is the one item worth doing immediately regardless of everything else — every week we
don't archive is a week of next season's prior thrown away. The rest is only worth building once a
usable season of history is actually in hand.

|   # | Work                                              | Effort   | Blocked by |
| --: | ------------------------------------------------- | -------- | ---------- |
|  P0 | Archive feeds weekly · hunt for 25/26             | ½ day    | —          |
|  P1 | Build the three historical predictors             | 1 day    | P0         |
|  P2 | Within-division normalization + λ                 | ½ day    | P1         |
|  P3 | Three-term shrinkage · relax the MP = 0 gate      | 1 day    | P2         |
|  P4 | Cross-season club identity + alias table          | ½ day    | P1         |
|  P5 | Bucketed backtest · tuner params · guardrail test | 1–2 days | P3         |

Roughly four to five days of work once history exists — but the mechanism in P3 is only about twenty
lines. The effort is concentrated in P1, P2 and P5, which is the right place for it: deciding what to
transfer and proving it helps.

---

Weight figures computed at φ = 2.0, τ = 6.0, κ = 2.93 (the current `shrink_pseudo_mp`). Data-source
findings verified against the live feeds on 31 August 2026.

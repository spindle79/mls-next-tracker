'use client';

import { useMemo } from 'react';
import type { DivisionData, WhatifScores } from '@/lib/tracker/types';
import {
  EmptyTableRow,
  GoalDiffTd,
  RankDelta,
  TableScroll,
} from '@/components/tracker/TrackerUi';
import {
  abbreviate,
  buildDefaultWhatifScores,
  getPredictionsArray,
  isFocusTeam,
  parsePredDate,
  whatifCanonicalScores,
  whatifCountChangedFromModel,
  whatifMid,
  whatifOptimizeForFocus,
  whatifOutcomeFromScores,
  whatifSimulate,
} from '@/lib/tracker/logic';
import { useDebounced } from './useDebounced';

type Filter = 'all' | 'focus' | 'glens';

type Props = {
  data: DivisionData;
  focusTeam: string | null;
  whatifScores: WhatifScores;
  onWhatifScores: (next: WhatifScores | ((prev: WhatifScores) => WhatifScores)) => void;
  filter: Filter;
  onFilterChange: (f: Filter) => void;
};

export function WhatIfPanel({
  data,
  focusTeam,
  whatifScores,
  onWhatifScores,
  filter,
  onFilterChange,
}: Props) {
  const debouncedScores = useDebounced(whatifScores, 250);

  const simStandings = useMemo(
    () => whatifSimulate(data, debouncedScores),
    [data, debouncedScores],
  );

  let preds = [...getPredictionsArray(data)];
  if (filter === 'focus' || filter === 'glens') {
    preds = preds.filter((p) => isFocusTeam(p.home, focusTeam) || isFocusTeam(p.away, focusTeam));
  }
  preds.sort((a, b) => parsePredDate(a.date).getTime() - parsePredDate(b.date).getTime());

  const changedCount = whatifCountChangedFromModel(data, whatifScores);
  const totalPreds = getPredictionsArray(data).length;
  const hidden = totalPreds - preds.length;

  const htW = focusTeam;
  const ftSim = htW ? simStandings.find((s) => s.team === htW) : null;
  const curFt = htW ? (data.current_standings || []).find((s) => s.team === htW) : null;
  function setScore(mid: string, home: number, away: number) {
    onWhatifScores((prev) => ({
      ...prev,
      [mid]: { home: Math.max(0, home), away: Math.max(0, away) },
    }));
  }

  function toggleOutcome(mid: string, outcome: string) {
    const s = whatifCanonicalScores(outcome);
    setScore(mid, s.home, s.away);
  }

  function resetFromModel() {
    onWhatifScores(buildDefaultWhatifScores(data));
  }

  function setAll(outcome: string) {
    const canon = whatifCanonicalScores(outcome);
    const next: WhatifScores = { ...whatifScores };
    getPredictionsArray(data).forEach((p) => {
      next[whatifMid(p)] = { ...canon };
    });
    onWhatifScores(next);
  }

  function focusSweep() {
    const ft = focusTeam;
    if (!ft) return;
    const next = { ...whatifScores };
    getPredictionsArray(data).forEach((p) => {
      const mid = whatifMid(p);
      if (p.home === ft) next[mid] = whatifCanonicalScores('home_win');
      else if (p.away === ft) next[mid] = whatifCanonicalScores('away_win');
    });
    onWhatifScores(next);
  }

  function runOptimize(mode: 'best' | 'worst') {
    onWhatifScores(whatifOptimizeForFocus(data, mode, whatifScores, focusTeam));
  }

  return (
    <div id="tab-whatif">
      <div className="summary-cards" id="whatif-summary">
        {ftSim && (
          <>
            <div className="summary-card">
              <div className="value">#{ftSim.rank}</div>
              <div className="label">
                Simulated Rank (currently #{curFt?.rank ?? '?'})
              </div>
            </div>
            <div className="summary-card">
              <div className="value">{ftSim.PTS}</div>
              <div className="label">Simulated Points</div>
            </div>
            <div className="summary-card">
              <div className="value">
                {ftSim.W}W-{ftSim.L}L-{ftSim.T}T
              </div>
              <div className="label">Simulated Record</div>
            </div>
          </>
        )}
      </div>

      <div className="whatif-actions">
        <button type="button" className="tab" onClick={resetFromModel}>
          Reset to model
        </button>
        <button type="button" className="tab" onClick={() => setAll('home_win')}>
          All home wins
        </button>
        <button type="button" className="tab" onClick={() => setAll('draw')}>
          All draws
        </button>
        <button type="button" className="tab" onClick={() => setAll('away_win')}>
          All away wins
        </button>
        <button type="button" className="tab" onClick={focusSweep}>
          Focus wins all
        </button>
        <button type="button" className="tab" onClick={() => runOptimize('best')}>
          Optimize best for focus
        </button>
        <button type="button" className="tab" onClick={() => runOptimize('worst')}>
          Optimize worst for focus
        </button>
      </div>

      <div className="card">
        <div className="card-header card-header--wrap">
          <span>Remaining games — edit scores</span>
          <select
            id="whatif-filter"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value as Filter)}
            title="Filter fixtures"
          >
            <option value="all">All remaining games</option>
            <option value="focus">Focus team games</option>
            <option value="glens">Focus team games (legacy label)</option>
          </select>
          <span className="badge badge-blue" id="whatif-count">
            {preds.length} shown, {changedCount} changed from model
          </span>
          {filter !== 'all' && (
            <span className="badge badge-yellow badge-gap" id="whatif-note">
              {hidden} other games still use your edited scores in the simulation
            </span>
          )}
        </div>

        <div className="whatif-split">
          <TableScroll>
            <table id="whatif-games">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Home</th>
                  <th
                    className="num"
                    title="Whole-number goals; W/L/T follows the 0.5-goal draw rule (equal scores are a draw)"
                  >
                    Pred. score
                  </th>
                  <th>Away</th>
                  <th>Quick</th>
                </tr>
              </thead>
              <tbody>
                {preds.length === 0 ? (
                  <EmptyTableRow colSpan={5}>
                    {totalPreds === 0
                      ? 'No remaining (unplayed) games in this dataset — the model has nothing to simulate.'
                      : 'No games match this filter. Try "All remaining games".'}
                  </EmptyTableRow>
                ) : (
                  preds.map((p) => {
                    const mid = whatifMid(p);
                    const sc = whatifScores[mid];
                    const mhR = Math.round(Number(p.est_home_goals));
                    const maR = Math.round(Number(p.est_away_goals));
                    const h = sc ? Number(sc.home) : mhR;
                    const a = sc ? Number(sc.away) : maR;
                    const out = whatifOutcomeFromScores(h, a);
                    const isChanged = Math.abs(h - mhR) > 1e-6 || Math.abs(a - maR) > 1e-6;
                    const homeF = isFocusTeam(p.home, focusTeam);
                    const awayF = isFocusTeam(p.away, focusTeam);
                    const rowClass = [homeF || awayF ? 'highlight' : '', isChanged ? 'whatif-changed' : '']
                      .filter(Boolean)
                      .join(' ');

                    return (
                      <tr key={mid} className={`whatif-game-row ${rowClass}`} data-match-id={mid}>
                        <td className="cell-date-compact">{p.date || '-'}</td>
                        <td className="team-name team-col--narrow">
                          {homeF ? (
                            <span className="focus-indicator">{abbreviate(p.home, focusTeam)}</span>
                          ) : (
                            abbreviate(p.home, focusTeam)
                          )}
                        </td>
                        <td className="whatif-scores" data-match-id={mid}>
                          <input
                            type="number"
                            step={1}
                            min={0}
                            className="whatif-gh"
                            value={Number.isFinite(h) ? Math.round(h) : 0}
                            aria-label={`${abbreviate(p.home, focusTeam)} goals`}
                            onChange={(e) =>
                              setScore(
                                mid,
                                Math.round(parseFloat(e.target.value)),
                                Math.round(a),
                              )
                            }
                          />
                          <span className="whatif-colon">:</span>
                          <input
                            type="number"
                            step={1}
                            min={0}
                            className="whatif-ga"
                            value={Number.isFinite(a) ? Math.round(a) : 0}
                            aria-label={`${abbreviate(p.away, focusTeam)} goals`}
                            onChange={(e) =>
                              setScore(
                                mid,
                                Math.round(h),
                                Math.round(parseFloat(e.target.value)),
                              )
                            }
                          />
                        </td>
                        <td className="team-name team-col--narrow">
                          {awayF ? (
                            <span className="focus-indicator">{abbreviate(p.away, focusTeam)}</span>
                          ) : (
                            abbreviate(p.away, focusTeam)
                          )}
                        </td>
                        <td>
                          <div className="outcome-toggle">
                            <button
                              type="button"
                              className={`outcome-btn ${out === 'home_win' ? 'active-home' : ''}`}
                              title="Set home win (2–0)"
                              onClick={() => toggleOutcome(mid, 'home_win')}
                            >
                              H
                            </button>
                            <button
                              type="button"
                              className={`outcome-btn ${out === 'draw' ? 'active-draw' : ''}`}
                              title="Set draw (1–1)"
                              onClick={() => toggleOutcome(mid, 'draw')}
                            >
                              D
                            </button>
                            <button
                              type="button"
                              className={`outcome-btn ${out === 'away_win' ? 'active-away' : ''}`}
                              title="Set away win (0–2)"
                              onClick={() => toggleOutcome(mid, 'away_win')}
                            >
                              A
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </TableScroll>

          <TableScroll>
            <table id="whatif-standings">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th className="num">Chg</th>
                  <th>Team</th>
                  <th className="num">PTS</th>
                  <th className="num">W</th>
                  <th className="num">L</th>
                  <th className="num">T</th>
                  <th className="num">GD</th>
                </tr>
              </thead>
              <tbody>
                {simStandings.map((s) => {
                  const isFt = isFocusTeam(s.team, focusTeam);
                  const isCutoff = s.rank === 6;
                  const classes = [isFt ? 'highlight' : '', isCutoff ? 'rank-cutoff' : '']
                    .filter(Boolean)
                    .join(' ');
                  const cur = (data.current_standings || []).find((c) => c.team === s.team);
                  const rankDiff = cur?.rank && s.rank ? cur.rank - s.rank : 0;

                  return (
                    <tr key={s.team} className={classes}>
                      <td className="num">{s.rank}</td>
                      <td className="num">
                        <RankDelta diff={rankDiff} neutral="dash" />
                      </td>
                      <td className="team-name">
                        {isFt ? <span className="focus-indicator">{s.team}</span> : s.team}
                      </td>
                      <td className="num">
                        <strong>{s.PTS}</strong>
                      </td>
                      <td className="num">{s.W}</td>
                      <td className="num">{s.L}</td>
                      <td className="num">{s.T}</td>
                      <GoalDiffTd gd={s.GD} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableScroll>
        </div>
      </div>
    </div>
  );
}

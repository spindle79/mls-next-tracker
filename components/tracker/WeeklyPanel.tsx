'use client';

import type { ReactNode } from 'react';
import type { DivisionData } from '@/lib/tracker/types';
import {
  buildPredByMatchMap,
  computeWeeklyHybridStandings,
  formatDateShort,
  isFocusTeam,
  normalizeMatchId,
  standingsSnapshotSig,
  weeklyPredParts,
} from '@/lib/tracker/logic';
import { GoalDiffTd, RankDelta, TableScroll } from '@/components/tracker/TrackerUi';

type Props = {
  data: DivisionData;
  currentWeek: number;
  focusTeam: string | null;
  onPrev: () => void;
  onNext: () => void;
  onWeekChange: (index: number) => void;
};

export function WeeklyPanel({
  data,
  currentWeek,
  focusTeam,
  onPrev,
  onNext,
  onWeekChange,
}: Props) {
  const weekly = data.weekly || [];
  const w = weekly[currentWeek];
  if (!weekly.length || !w) {
    return (
      <div id="tab-weekly">
        <p className="tracker-empty-panel">No weekly schedule in this bundle.</p>
      </div>
    );
  }
  const predByMatch = buildPredByMatchMap(data);
  const hybridStandings = computeWeeklyHybridStandings(data, currentWeek, predByMatch);
  const hybridPrev =
    currentWeek > 0
      ? computeWeeklyHybridStandings(data, currentWeek - 1, predByMatch)
      : null;

  const ftRow = focusTeam ? hybridStandings.find((s) => s.team === focusTeam) : null;
  const prevFt =
    focusTeam && hybridPrev ? hybridPrev.find((s) => s.team === focusTeam) : null;

  const rankChange = prevFt && ftRow ? prevFt.rank - ftRow.rank : 0;

  const ws = w?.week_start ? new Date(w.week_start + 'T00:00:00') : null;
  const we = w?.week_end ? new Date(w.week_end + 'T00:00:00') : null;

  const hybridSig = standingsSnapshotSig(hybridStandings);
  const prevSig = hybridPrev ? standingsSnapshotSig(hybridPrev) : null;
  let subtitle =
    'Weeks are replayed in order through this date range: each match uses its final score if recorded, otherwise the same projection as the Pred. column (incl. draw if goals are within 0.5). Tiebreakers match the What If tab.';
  if (prevSig !== null && hybridSig === prevSig) {
    subtitle =
      'Same hybrid snapshot as last week. No new games with data (or projections unchanged). ' +
      subtitle;
  }

  const standingsSorted = [...hybridStandings].sort((a, b) => a.rank - b.rank);

  return (
    <div id="tab-weekly">
      <div className="week-nav">
        <button type="button" id="btn-prev" disabled={currentWeek === 0} onClick={onPrev}>
          &larr; Prev
        </button>
        <select
          id="week-select"
          value={currentWeek}
          onChange={(e) => onWeekChange(Number(e.target.value))}
          title="Select week"
        >
          {weekly.map((wk, i) => {
            const d0 = new Date(wk.week_start + 'T00:00:00');
            const d1 = new Date(wk.week_end + 'T00:00:00');
            const playedGames = wk.games?.filter((g) => g.played).length ?? 0;
            const tbdGames = wk.games?.filter((g) => !g.played).length ?? 0;
            let label = `Week ${i + 1}: ${formatDateShort(d0)} - ${formatDateShort(d1)}`;
            if (playedGames > 0) label += ` (${playedGames} played)`;
            if (tbdGames > 0) label += ` (${tbdGames} upcoming)`;
            return (
              <option key={i} value={i}>
                {label}
              </option>
            );
          })}
        </select>
        <button
          type="button"
          id="btn-next"
          disabled={currentWeek >= weekly.length - 1}
          onClick={onNext}
        >
          Next &rarr;
        </button>
        <span className="week-label" id="week-label">
          {ws && we ? `${formatDateShort(ws)} - ${formatDateShort(we)}, ${ws.getFullYear()}` : ''}
        </span>
      </div>

      <div id="weekly-summary" className="summary-cards">
        {ftRow && (
          <>
            <div className={`summary-card ${rankChange > 0 ? 'good' : rankChange < 0 ? 'bad' : ''}`}>
              <div className="value">
                #{ftRow.rank}
                {rankChange > 0 ? ` (+${rankChange})` : rankChange < 0 ? ` (${rankChange})` : ''}
              </div>
              <div className="label">Focus rank</div>
            </div>
            <div className="summary-card">
              <div className="value">{ftRow.PTS}</div>
              <div className="label">Points</div>
            </div>
            <div className={`summary-card ${ftRow.rank <= 6 ? 'good' : 'bad'}`}>
              <div className="value">
                {ftRow.W}W-{ftRow.L}L-{ftRow.T}T
              </div>
              <div className="label">Record</div>
            </div>
            <div className={`summary-card ${(ftRow.GD ?? 0) >= 0 ? 'good' : 'bad'}`}>
              <div className="value">
                {(ftRow.GD ?? 0) > 0 ? '+' : ''}
                {ftRow.GD}
              </div>
              <div className="label">Goal Diff</div>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <div className="card-header">Games this week</div>
        <TableScroll>
          <table id="weekly-games">
            <thead>
              <tr>
                <th>Date</th>
                <th>Home</th>
                <th className="num">Score</th>
                <th
                  className="num"
                  title="Model scoreline: pre-kickoff estimate for finished games; projection for TBD (same engine as Predictions tab)"
                >
                  Pred.
                </th>
                <th>Away</th>
                <th>Venue</th>
              </tr>
            </thead>
            <tbody>
              {(w?.games || []).map((g, gi) => {
                const homeF = isFocusTeam(g.home, focusTeam);
                const awayF = isFocusTeam(g.away, focusTeam);
                const rowClass = homeF || awayF ? 'highlight' : '';
                const pr = predByMatch[normalizeMatchId(g.match_id)];
                let scoreClass = 'tbd';
                let scoreText = '—';
                if (g.played) {
                  const hg = Number(g.home_goals);
                  const ag = Number(g.away_goals);
                  if (hg > ag) scoreClass = homeF ? 'win' : awayF ? 'loss' : '';
                  else if (hg < ag) scoreClass = awayF ? 'win' : homeF ? 'loss' : '';
                  else scoreClass = 'draw';
                  scoreText = `${hg} : ${ag}`;
                } else if (!pr) {
                  scoreText = 'TBD';
                }
                const parts = weeklyPredParts(pr);
                return (
                  <tr key={gi} className={rowClass}>
                    <td>{g.date || '-'}</td>
                    <td className="team-name">
                      {homeF ? <span className="focus-indicator">{g.home}</span> : g.home}
                    </td>
                    <td className={`score ${scoreClass}`}>{scoreText}</td>
                    <td className={parts.predClass}>
                      {!pr || pr.est_home_goals == null ? (
                        '—'
                      ) : parts.eff === 'draw' ? (
                        <>
                          <span className="pred-proj-tie">{parts.hStr}</span> :{' '}
                          <span className="pred-proj-tie">{parts.aStr}</span>
                        </>
                      ) : parts.eff === 'home_win' ? (
                        <>
                          <span className="pred-proj-win">{parts.hStr}</span> :{' '}
                          <span>{parts.aStr}</span>
                        </>
                      ) : (
                        <>
                          <span>{parts.hStr}</span> :{' '}
                          <span className="pred-proj-win">{parts.aStr}</span>
                        </>
                      )}
                    </td>
                    <td className="team-name">
                      {awayF ? <span className="focus-indicator">{g.away}</span> : g.away}
                    </td>
                    <td className="team-name team-col--wide-venue">{g.venue || '-'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableScroll>
      </div>

      <p className="standings-subtitle" id="weekly-standings-subtitle">
        {subtitle}
      </p>
      <TableScroll id="weekly-standings-scroll">
        <table id="weekly-standings">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Team</th>
              <th className="num">PTS</th>
              <th className="num">PPM</th>
              <th className="num">MP</th>
              <th className="num">W</th>
              <th className="num">L</th>
              <th className="num">T</th>
              <th className="num">GF</th>
              <th className="num">GA</th>
              <th className="num">GD</th>
            </tr>
          </thead>
          <tbody>
            {standingsSorted.map((s) => {
              const isFt = isFocusTeam(s.team, focusTeam);
              const isCutoff = s.rank === 6;
              const classes = [
                isFt ? 'highlight' : '',
                isCutoff ? 'rank-cutoff' : '',
              ]
                .filter(Boolean)
                .join(' ');
              let rankDelta: ReactNode = null;
              if (hybridPrev) {
                const prevStanding = hybridPrev.find((ps) => ps.team === s.team);
                if (prevStanding) {
                  const diff = prevStanding.rank - s.rank;
                  rankDelta = <RankDelta diff={diff} />;
                }
              }
              return (
                <tr key={s.team} className={classes}>
                  <td className="num">
                    {s.rank} {rankDelta}
                  </td>
                  <td className="team-name">
                    {isFt ? <span className="focus-indicator">{s.team}</span> : s.team}
                  </td>
                  <td className="num">
                    <strong>{s.PTS}</strong>
                  </td>
                  <td className="num">{Number(s.PPM).toFixed(2)}</td>
                  <td className="num">{s.MP}</td>
                  <td className="num">{s.W}</td>
                  <td className="num">{s.L}</td>
                  <td className="num">{s.T}</td>
                  <td className="num">{s.GF}</td>
                  <td className="num">{s.GA}</td>
                  <GoalDiffTd gd={s.GD} />
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableScroll>
    </div>
  );
}

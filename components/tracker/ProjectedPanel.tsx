"use client";

import type { DivisionData } from "@/lib/tracker/types";
import { GoalDiffTd, RankDelta, TableScroll } from "@/components/tracker/TrackerUi";
import { isFocusTeam } from "@/lib/tracker/logic";

type Props = {
  data: DivisionData;
  focusTeam: string | null;
};

export function ProjectedPanel({ data, focusTeam }: Props) {
  const projected = data.projected_final_standings || [];
  const current = data.current_standings || [];
  const ftRow = focusTeam ? projected.find((s) => s.team === focusTeam) : null;
  const ftCurrentRank = focusTeam ? (current.find((s) => s.team === focusTeam)?.rank ?? 0) : 0;
  return (
    <div id="tab-projected">
      <div className="summary-cards" id="projected-summary">
        {ftRow && (
          <>
            <div className="summary-card">
              <div className="value">#{ftRow.rank}</div>
              <div className="label">Projected Rank (currently #{ftCurrentRank})</div>
            </div>
            <div className="summary-card">
              <div className="value">{ftRow.PTS}</div>
              <div className="label">Projected Points</div>
            </div>
            <div className="summary-card">
              <div className="value">
                {ftRow.W}W-{ftRow.L}L-{ftRow.T}T
              </div>
              <div className="label">Projected Record</div>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <div className="card-header">Projected final standings</div>
        <TableScroll>
          <table id="projected-table">
            <thead>
              <tr>
                <th className="num">#</th>
                <th className="num">Chg</th>
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
              {projected.map((s) => {
                const isFt = isFocusTeam(s.team, focusTeam);
                const isCutoff = s.rank === 6;
                const classes = [isFt ? "highlight" : "", isCutoff ? "rank-cutoff" : ""]
                  .filter(Boolean)
                  .join(" ");
                const cur = current.find((c) => c.team === s.team);
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
    </div>
  );
}

"use client";

import type { ReactNode } from "react";
import type { DivisionData } from "@/lib/tracker/types";
import { GoalDiffTd, EmptyTableRow, TableScroll } from "@/components/tracker/TrackerUi";
import { isFocusTeam } from "@/lib/tracker/logic";

type Props = {
  data: DivisionData;
  focusTeam: string | null;
  selectedTeam: string;
  onTeamChange: (team: string) => void;
};

export function H2HPanel({ data, focusTeam, selectedTeam, onTeamChange }: Props) {
  const h2h = data.head_to_head?.[selectedTeam] || {};

  const opponents = Object.keys(h2h).sort((a, b) => {
    const aTotal = h2h[a].W + h2h[a].L + h2h[a].T;
    const bTotal = h2h[b].W + h2h[b].L + h2h[b].T;
    return bTotal - aTotal;
  });

  return (
    <div id="tab-h2h">
      <div className="week-nav">
        <select
          id="h2h-team"
          value={selectedTeam}
          onChange={(e) => onTeamChange(e.target.value)}
          title="Pivot team"
        >
          {(data.team_names || []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="card">
        <div className="card-header" id="h2h-header">
          Head-to-Head: {selectedTeam}
        </div>
        <TableScroll>
          <table id="h2h-table">
            <thead>
              <tr>
                <th>Opponent</th>
                <th className="num">W</th>
                <th className="num">L</th>
                <th className="num">T</th>
                <th className="num">GF</th>
                <th className="num">GA</th>
                <th className="num">GD</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {opponents.length === 0 ? (
                <EmptyTableRow colSpan={8} center>
                  No head-to-head data yet
                </EmptyTableRow>
              ) : (
                opponents.map((opp) => {
                  const r = h2h[opp];
                  const gd = r.GF - r.GA;
                  let resultText: ReactNode = "";
                  if (r.W > r.L) resultText = <span className="result-label--good">Winning</span>;
                  else if (r.L > r.W)
                    resultText = <span className="result-label--bad">Losing</span>;
                  else if (r.W + r.L + r.T > 0)
                    resultText = <span className="result-label--even">Even</span>;

                  const oppF = isFocusTeam(opp, focusTeam);
                  return (
                    <tr key={opp}>
                      <td className="team-name">
                        {oppF ? <span className="focus-indicator">{opp}</span> : opp}
                      </td>
                      <td className="num">{r.W}</td>
                      <td className="num">{r.L}</td>
                      <td className="num">{r.T}</td>
                      <td className="num">{r.GF}</td>
                      <td className="num">{r.GA}</td>
                      <GoalDiffTd gd={gd} />
                      <td>{resultText}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </TableScroll>
      </div>
    </div>
  );
}

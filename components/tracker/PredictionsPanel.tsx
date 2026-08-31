"use client";

import type { DivisionData } from "@/lib/tracker/types";
import { TableScroll } from "@/components/tracker/TrackerUi";
import {
  effectivePredictedOutcome,
  formatPredGoal,
  getPredictionsArray,
  isFocusTeam,
  parsePredDate,
} from "@/lib/tracker/logic";

type Props = {
  data: DivisionData;
  focusTeam: string | null;
  filter: string;
  focusOnly: boolean;
  onFilterChange: (v: string) => void;
  onFocusOnlyChange: (v: boolean) => void;
};

export function PredictionsPanel({
  data,
  focusTeam,
  filter,
  focusOnly,
  onFilterChange,
  onFocusOnlyChange,
}: Props) {
  let preds = getPredictionsArray(data);
  if (focusOnly) {
    preds = preds.filter((p) => isFocusTeam(p.home, focusTeam) || isFocusTeam(p.away, focusTeam));
  } else if (filter) {
    preds = preds.filter((p) => p.home === filter || p.away === filter);
  }
  preds = [...preds].sort(
    (a, b) => parsePredDate(a.date).getTime() - parsePredDate(b.date).getTime(),
  );

  return (
    <div id="tab-predictions">
      <div className="week-nav">
        <select
          id="pred-filter"
          value={filter}
          onChange={(e) => onFilterChange(e.target.value)}
          title="Filter by team"
        >
          <option value="">All teams</option>
          {(data.team_names || []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <label className="field-inline">
          <input
            type="checkbox"
            id="pred-focus-only"
            checked={focusOnly}
            onChange={(e) => onFocusOnlyChange(e.target.checked)}
          />
          Focus team only
        </label>
      </div>

      <div className="card">
        <div className="card-header">
          Model predictions (remaining fixtures)
          <span className="badge badge-blue" id="pred-count">
            {preds.length} games
          </span>
        </div>
        <TableScroll>
          <table id="pred-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Home</th>
                <th className="num">Est. Score</th>
                <th>Away</th>
                <th>Prediction</th>
                <th>Probabilities</th>
                <th>Venue</th>
              </tr>
            </thead>
            <tbody>
              {preds.map((p, i) => {
                const homeF = isFocusTeam(p.home, focusTeam);
                const awayF = isFocusTeam(p.away, focusTeam);
                const hasF = homeF || awayF;
                const eff = effectivePredictedOutcome(p);
                let predText = "";
                if (eff === "home_win") predText = `${p.home} win`;
                else if (eff === "away_win") predText = `${p.away} win`;
                else predText = "Draw";

                let focusOutcome = "";
                if (hasF) {
                  if (eff === "home_win" && homeF) focusOutcome = "home_win";
                  else if (eff === "away_win" && awayF) focusOutcome = "home_win";
                  else if (eff === "draw") focusOutcome = "draw";
                  else focusOutcome = "away_win";
                }

                const hwPct = Math.round(Number(p.home_win_prob) * 100);
                const dwPct = Math.round(Number(p.draw_prob) * 100);
                const awPct = Math.round(Number(p.away_win_prob) * 100);
                const hEst = formatPredGoal(p.est_home_goals);
                const aEst = formatPredGoal(p.est_away_goals);

                const scoreCell =
                  eff === "draw" ? (
                    <td className="score predicted-est">
                      <span className="pred-proj-tie">{hEst}</span> :{" "}
                      <span className="pred-proj-tie">{aEst}</span>
                    </td>
                  ) : (
                    <td className="score score-dim">
                      {hEst} : {aEst}
                    </td>
                  );

                return (
                  <tr key={`${p.match_id}-${i}`} className={hasF ? "highlight" : ""}>
                    <td>{p.date || "-"}</td>
                    <td className="team-name">
                      {homeF ? <span className="focus-indicator">{p.home}</span> : p.home}
                    </td>
                    {scoreCell}
                    <td className="team-name">
                      {awayF ? <span className="focus-indicator">{p.away}</span> : p.away}
                    </td>
                    <td>
                      <span className={`prediction-tag ${hasF ? focusOutcome : eff}`}>
                        {predText}
                      </span>
                    </td>
                    <td>
                      <div className="prob-inline">
                        <div className="prob-bar">
                          <div className="home" style={{ width: `${hwPct}%` }} />
                          <div className="draw" style={{ width: `${dwPct}%` }} />
                          <div className="away" style={{ width: `${awPct}%` }} />
                        </div>
                        <span className="prob-inline__meta">
                          {hwPct}-{dwPct}-{awPct}
                        </span>
                      </div>
                    </td>
                    <td className="team-name team-col--medium">{p.venue || "-"}</td>
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

/**
 * Pure tracker logic (no DOM). Extracted from the legacy inline script.
 */
import type {
  DivisionData,
  DivisionCatalogEntry,
  HybridStandingRow,
  PredictionRow,
  RootData,
  WhatifScores,
} from "./types";

export const FOCUS_TEAM_LS_PREFIX = "season-tracker-focus-team:";

/** Persisted preference when switching Academy vs Homegrown (multi-league roots). */
export const ACTIVE_LEAGUE_LS_KEY = "season-tracker-active-league";

/** Persisted age group (e.g. U13) when multiple ages exist in the catalog. */
export const ACTIVE_AGE_LS_KEY = "season-tracker-active-age";

export function uniqueSortedLeaguesFromCatalog(cat: DivisionCatalogEntry[]): string[] {
  const s = new Set<string>();
  cat.forEach((e) => {
    const slug = e.league?.trim();
    if (slug) s.add(slug);
  });
  return [...s].sort((a, b) => a.localeCompare(b));
}

/** Title case for catalog slug (academy → Academy). */
export function formatLeagueOptionLabel(slug: string): string {
  if (!slug) return slug;
  return slug.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const GLENS_FOCUS = "San Francisco Glens SC";

/** Distinct age labels (U13, U14, …) from catalog rows, optionally scoped to one league. */
export function uniqueSortedAgeLabelsFromCatalog(
  cat: DivisionCatalogEntry[],
  leagueFilter?: string | null,
): string[] {
  const s = new Set<string>();
  cat.forEach((e) => {
    if (leagueFilter != null && leagueFilter !== "" && e.league !== leagueFilter) {
      return;
    }
    const a = e.age_label?.trim();
    if (a) s.add(a);
  });
  return [...s].sort((x, y) => compareAgeLabels(x, y));
}

/** Sort U13 / U14 / … numerically when possible. */
export function compareAgeLabels(a: string, b: string): number {
  const na = parseAgeLabelNumber(a);
  const nb = parseAgeLabelNumber(b);
  if (na !== nb) return na - nb;
  return a.localeCompare(b);
}

function parseAgeLabelNumber(label: string): number {
  const m = label.trim().match(/U\s*(\d+)/i) ?? label.match(/(\d+)/);
  return m ? parseInt(m[1], 10) : 999;
}

/** Pick a division id within optional league + age filters (prefer SF Glens, default_division_id, else first row). */
export function preferDivisionIdInScope(
  root: RootData | null,
  catalog: DivisionCatalogEntry[],
  filters: { league?: string; age_label?: string },
): string | undefined {
  let filtered = catalog.slice();
  if (filters.league) {
    filtered = filtered.filter((e) => e.league === filters.league);
  }
  if (filters.age_label) {
    filtered = filtered.filter((e) => e.age_label === filters.age_label);
  }
  if (!filtered.length) return undefined;
  const divisions = (root?.divisions || []) as DivisionData[];
  for (const entry of filtered) {
    const div = divisions.find((d) => String(d.id) === String(entry.id));
    if (div?.team_names?.includes(GLENS_FOCUS)) return String(entry.id);
  }
  const defId = root?.default_division_id;
  if (defId && filtered.some((e) => String(e.id) === String(defId))) {
    return String(defId);
  }
  return String(filtered[0].id);
}

/** Pick a division id within a league (prefer SF Glens, then root default if in league, else first catalog row). */
export function preferDivisionIdInLeague(
  root: RootData | null,
  catalog: DivisionCatalogEntry[],
  league: string,
): string | undefined {
  return preferDivisionIdInScope(root, catalog, { league });
}

export function divisionCatalogEntries(root: RootData | null): DivisionCatalogEntry[] {
  const cat = root?.division_catalog as DivisionCatalogEntry[] | undefined;
  if (cat && cat.length) return cat;
  const divs = root?.divisions as DivisionData[] | undefined;
  if (!divs || !divs.length) return [];
  return divs.map((d) => ({
    id: String(d.id ?? ""),
    age_label: d.age_label,
    division: d.division,
    league: d.league,
  }));
}

export function getPredictionsArray(data: DivisionData): PredictionRow[] {
  const p = data.predictions;
  return Array.isArray(p) ? p : [];
}

export function divisionFocusStorageKey(data: DivisionData): string {
  if (data.id != null && data.id !== "") return String(data.id);
  const age = data.age_label || "";
  const div = data.division || "";
  return `${age}|${div}`;
}

export function formatDateShort(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function isFocusTeam(name: string, focus: string | null): boolean {
  return focus != null && name === focus;
}

export function effectivePredictedOutcome(p: PredictionRow): string {
  const h = Math.round(Number(p.est_home_goals));
  const a = Math.round(Number(p.est_away_goals));
  if (Number.isFinite(h) && Number.isFinite(a) && h === a) return "draw";
  return String(p.predicted_outcome ?? "");
}

export function formatPredGoal(n: unknown): string {
  const x = Number(n);
  if (!Number.isFinite(x)) return "";
  return String(Math.round(x));
}

export function normalizeMatchId(id: unknown): string {
  return String(id == null ? "" : id).trim();
}

export type WeeklyPredParts = {
  predClass: string;
  hStr: string;
  aStr: string;
  eff: string;
};

export function weeklyPredParts(pr: PredictionRow | undefined): WeeklyPredParts {
  if (!pr || pr.est_home_goals == null || pr.est_away_goals == null) {
    return { predClass: "score tbd", hStr: "", aStr: "", eff: "" };
  }
  const predClass = "score predicted-est";
  const hStr = formatPredGoal(pr.est_home_goals);
  const aStr = formatPredGoal(pr.est_away_goals);
  const eff = effectivePredictedOutcome(pr);
  return { predClass, hStr, aStr, eff };
}

export function buildPredByMatchMap(data: DivisionData): Record<string, PredictionRow> {
  const predByMatch: Record<string, PredictionRow> = {};
  const retro = data.retro_predictions || {};
  Object.keys(retro).forEach((k) => {
    predByMatch[normalizeMatchId(k)] = retro[k]!;
  });
  getPredictionsArray(data).forEach((p) => {
    predByMatch[normalizeMatchId(p.match_id)] = p;
  });
  return predByMatch;
}

export function standingsSnapshotSig(standings: HybridStandingRow[]): string {
  return [...standings]
    .map((s) => `${s.team}|${s.PTS}|${s.MP}|${s.GF}|${s.GA}|${s.rank}`)
    .sort()
    .join(";");
}

function ensureH2hCell(h2h: Record<string, Record<string, H2hAgg>>, a: string, b: string): H2hAgg {
  if (!h2h[a]) h2h[a] = {};
  if (!h2h[a][b]) h2h[a][b] = { W: 0, L: 0, T: 0, GF: 0, GA: 0 };
  return h2h[a][b];
}

type H2hAgg = { W: number; L: number; T: number; GF: number; GA: number };

type StandAgg = {
  PTS: number;
  W: number;
  L: number;
  T: number;
  GF: number;
  GA: number;
  GD: number;
  MP: number;
  home_GF: number;
  home_GA: number;
  away_GF: number;
  away_GA: number;
};

function applyActualToStandingsAndH2h(
  home: string,
  away: string,
  hg: number,
  ag: number,
  standings: Record<string, StandAgg>,
  h2h: Record<string, Record<string, H2hAgg>>,
) {
  if (!standings[home] || !standings[away]) return;
  const h = standings[home]!;
  const aw = standings[away]!;
  h.MP += 1;
  h.GF += hg;
  h.GA += ag;
  h.GD = h.GF - h.GA;
  h.home_GF += hg;
  h.home_GA += ag;
  aw.MP += 1;
  aw.GF += ag;
  aw.GA += hg;
  aw.GD = aw.GF - aw.GA;
  aw.away_GF += ag;
  aw.away_GA += hg;
  if (hg > ag) {
    h.W += 1;
    h.PTS += 3;
    aw.L += 1;
  } else if (hg < ag) {
    aw.W += 1;
    aw.PTS += 3;
    h.L += 1;
  } else {
    h.T += 1;
    aw.T += 1;
    h.PTS += 1;
    aw.PTS += 1;
  }
  if (hg > ag) {
    ensureH2hCell(h2h, home, away).W += 1;
    ensureH2hCell(h2h, away, home).L += 1;
  } else if (hg < ag) {
    ensureH2hCell(h2h, home, away).L += 1;
    ensureH2hCell(h2h, away, home).W += 1;
  } else {
    ensureH2hCell(h2h, home, away).T += 1;
    ensureH2hCell(h2h, away, home).T += 1;
  }
  ensureH2hCell(h2h, home, away).GF += hg;
  ensureH2hCell(h2h, home, away).GA += ag;
  ensureH2hCell(h2h, away, home).GF += ag;
  ensureH2hCell(h2h, away, home).GA += hg;
}

function applyPredictionToStandingsAndH2h(
  p: PredictionRow,
  standings: Record<string, StandAgg>,
  h2h: Record<string, Record<string, H2hAgg>>,
) {
  const home = p.home;
  const away = p.away;
  if (!standings[home] || !standings[away]) return;
  const outcome = effectivePredictedOutcome(p);
  const eh = Number(p.est_home_goals);
  const ea = Number(p.est_away_goals);
  const h = standings[home]!;
  const aw = standings[away]!;
  h.MP += 1;
  aw.MP += 1;
  if (outcome === "home_win") {
    h.W += 1;
    h.PTS += 3;
    aw.L += 1;
    h.GF += eh;
    h.GA += ea;
    h.home_GF += eh;
    h.home_GA += ea;
    aw.GF += ea;
    aw.GA += eh;
    aw.away_GF += ea;
    aw.away_GA += eh;
    ensureH2hCell(h2h, home, away).W += 1;
    ensureH2hCell(h2h, away, home).L += 1;
  } else if (outcome === "away_win") {
    aw.W += 1;
    aw.PTS += 3;
    h.L += 1;
    h.GF += eh;
    h.GA += ea;
    h.home_GF += eh;
    h.home_GA += ea;
    aw.GF += ea;
    aw.GA += eh;
    aw.away_GF += ea;
    aw.away_GA += eh;
    ensureH2hCell(h2h, home, away).L += 1;
    ensureH2hCell(h2h, away, home).W += 1;
  } else {
    h.T += 1;
    aw.T += 1;
    h.PTS += 1;
    aw.PTS += 1;
    const avg = (eh + ea) / 2;
    h.GF += avg;
    h.GA += avg;
    h.home_GF += avg;
    h.home_GA += avg;
    aw.GF += avg;
    aw.GA += avg;
    aw.away_GF += avg;
    aw.away_GA += avg;
    ensureH2hCell(h2h, home, away).T += 1;
    ensureH2hCell(h2h, away, home).T += 1;
  }
  h.GD = h.GF - h.GA;
  aw.GD = aw.GF - aw.GA;
  ensureH2hCell(h2h, home, away).GF += eh;
  ensureH2hCell(h2h, home, away).GA += ea;
  ensureH2hCell(h2h, away, home).GF += ea;
  ensureH2hCell(h2h, away, home).GA += eh;
}

function initWeeklyReplayState(data: DivisionData): {
  standings: Record<string, StandAgg>;
  h2h: Record<string, Record<string, H2hAgg>>;
} {
  const standings: Record<string, StandAgg> = {};
  (data.team_names || []).forEach((name) => {
    standings[name] = {
      PTS: 0,
      W: 0,
      L: 0,
      T: 0,
      GF: 0,
      GA: 0,
      GD: 0,
      MP: 0,
      home_GF: 0,
      home_GA: 0,
      away_GF: 0,
      away_GA: 0,
    };
  });
  return { standings, h2h: {} };
}

export function computeWeeklyHybridStandings(
  data: DivisionData,
  weekIdx: number,
  predByMatch: Record<string, PredictionRow>,
): HybridStandingRow[] {
  const { standings, h2h } = initWeeklyReplayState(data);
  const weekly = data.weekly || [];
  for (let wi = 0; wi <= weekIdx; wi++) {
    const week = weekly[wi];
    if (!week?.games) continue;
    week.games.forEach((g) => {
      if (g.played) {
        applyActualToStandingsAndH2h(
          g.home,
          g.away,
          Number(g.home_goals),
          Number(g.away_goals),
          standings,
          h2h,
        );
      } else {
        const mid = normalizeMatchId(g.match_id);
        const pr = predByMatch[mid];
        if (pr) applyPredictionToStandingsAndH2h(pr, standings, h2h);
      }
    });
  }
  const ranked: HybridStandingRow[] = [];
  (data.team_names || []).forEach((name) => {
    const s = standings[name]!;
    ranked.push({
      team: name,
      PTS: s.PTS,
      W: s.W,
      L: s.L,
      T: s.T,
      MP: s.MP,
      GF: Math.round(s.GF * 10) / 10,
      GA: Math.round(s.GA * 10) / 10,
      GD: Math.round((s.GF - s.GA) * 10) / 10,
      PPM: s.MP > 0 ? Math.round((s.PTS / s.MP) * 100) / 100 : 0,
      home_GF: Math.round(s.home_GF * 10) / 10,
      home_GA: Math.round(s.home_GA * 10) / 10,
      away_GF: Math.round(s.away_GF * 10) / 10,
      away_GA: Math.round(s.away_GA * 10) / 10,
      rank: 0,
    });
  });
  rankTeamsWhatIf(ranked, h2h as unknown as Record<string, Record<string, H2hMini>> | null);
  return ranked;
}

type SimRow = HybridStandingRow;

type H2hMini = { W: number; L: number; T: number; GF: number; GA: number };

export function whatifMid(p: PredictionRow): string {
  return String(p.match_id);
}

export function whatifCanonicalScores(outcome: string): { home: number; away: number } {
  if (outcome === "home_win") return { home: 2, away: 0 };
  if (outcome === "away_win") return { home: 0, away: 2 };
  return { home: 1, away: 1 };
}

export function isScorelineDrawByMargin(homeG: number, awayG: number): boolean {
  const h = Number(homeG);
  const a = Number(awayG);
  if (!Number.isFinite(h) || !Number.isFinite(a)) return false;
  return Math.abs(h - a) <= 0.5;
}

export function whatifOutcomeFromScores(homeG: number, awayG: number): string {
  if (isScorelineDrawByMargin(homeG, awayG)) return "draw";
  if (homeG > awayG) return "home_win";
  return "away_win";
}

export function buildDefaultWhatifScores(data: DivisionData): WhatifScores {
  const whatifScores: WhatifScores = {};
  getPredictionsArray(data).forEach((p) => {
    whatifScores[whatifMid(p)] = {
      home: Math.round(Number(p.est_home_goals)),
      away: Math.round(Number(p.est_away_goals)),
    };
  });
  return whatifScores;
}

export function whatifCountChangedFromModel(
  data: DivisionData,
  whatifScores: WhatifScores,
): number {
  let n = 0;
  getPredictionsArray(data).forEach((p) => {
    const s = whatifScores[whatifMid(p)];
    if (!s) return;
    const mhR = Math.round(Number(p.est_home_goals));
    const maR = Math.round(Number(p.est_away_goals));
    if (Math.abs(s.home - mhR) > 1e-6 || Math.abs(s.away - maR) > 1e-6) n += 1;
  });
  return n;
}

export function getContenderTeams(data: DivisionData, focusTeam: string | null): Set<string> {
  const contenders = new Set<string>();
  (data.current_standings || []).forEach((s) => {
    const r = s.rank ?? 999;
    if (r >= 4 && r <= 14) contenders.add(s.team);
  });
  if (focusTeam) contenders.add(focusTeam);
  return contenders;
}

export function whatifCloneScores(scores: WhatifScores | null | undefined): WhatifScores {
  const out: WhatifScores = {};
  Object.keys(scores || {}).forEach((k) => {
    const v = scores![k];
    if (!v) return;
    out[String(k)] = { home: Number(v.home), away: Number(v.away) };
  });
  return out;
}

export function findLastPlayedWeek(data: DivisionData) {
  const weekly = data.weekly;
  if (!weekly || !weekly.length) return null;
  for (let i = weekly.length - 1; i >= 0; i--) {
    const w = weekly[i];
    if (w?.games?.some((g) => g.played)) return w;
  }
  return null;
}

function simulateFromScores(data: DivisionData, scores: WhatifScores): SimRow[] {
  const lastPlayedWeek = findLastPlayedWeek(data);
  const baseStandings: Record<string, StandAgg> = {};
  const standingsOk =
    lastPlayedWeek &&
    Array.isArray(lastPlayedWeek.standings) &&
    lastPlayedWeek.standings!.length > 0;

  if (standingsOk) {
    lastPlayedWeek!.standings!.forEach((s) => {
      baseStandings[s.team] = {
        PTS: s.PTS ?? 0,
        W: s.W ?? 0,
        L: s.L ?? 0,
        T: s.T ?? 0,
        GF: s.GF ?? 0,
        GA: s.GA ?? 0,
        GD: s.GD ?? 0,
        MP: s.MP ?? 0,
        home_GF: s.home_GF ?? 0,
        home_GA: s.home_GA ?? 0,
        away_GF: s.away_GF ?? 0,
        away_GA: s.away_GA ?? 0,
      };
    });
  } else {
    (Array.isArray(data.team_names) ? data.team_names : []).forEach((name) => {
      baseStandings[name] = {
        PTS: 0,
        W: 0,
        L: 0,
        T: 0,
        GF: 0,
        GA: 0,
        GD: 0,
        MP: 0,
        home_GF: 0,
        home_GA: 0,
        away_GF: 0,
        away_GA: 0,
      };
    });
  }

  getPredictionsArray(data).forEach((p) => {
    const home = p.home;
    const away = p.away;
    if (!baseStandings[home] || !baseStandings[away]) return;

    const ws = scores[whatifMid(p)];
    const eh = Math.max(0, Number(ws?.home ?? p.est_home_goals));
    const ea = Math.max(0, Number(ws?.away ?? p.est_away_goals));
    const outcome = whatifOutcomeFromScores(eh, ea);
    const h = baseStandings[home]!;
    const aw = baseStandings[away]!;

    h.MP += 1;
    aw.MP += 1;

    if (outcome === "home_win") {
      h.W += 1;
      h.PTS += 3;
      aw.L += 1;
      h.GF += eh;
      h.GA += ea;
      h.home_GF += eh;
      h.home_GA += ea;
      aw.GF += ea;
      aw.GA += eh;
      aw.away_GF += ea;
      aw.away_GA += eh;
    } else if (outcome === "away_win") {
      aw.W += 1;
      aw.PTS += 3;
      h.L += 1;
      h.GF += eh;
      h.GA += ea;
      h.home_GF += eh;
      h.home_GA += ea;
      aw.GF += ea;
      aw.GA += eh;
      aw.away_GF += ea;
      aw.away_GA += eh;
    } else {
      h.T += 1;
      aw.T += 1;
      h.PTS += 1;
      aw.PTS += 1;
      const avg = (eh + ea) / 2;
      h.GF += avg;
      h.GA += avg;
      h.home_GF += avg;
      h.home_GA += avg;
      aw.GF += avg;
      aw.GA += avg;
      aw.away_GF += avg;
      aw.away_GA += avg;
    }
  });

  const ranked: SimRow[] = [];
  Object.keys(baseStandings).forEach((name) => {
    const s = baseStandings[name]!;
    ranked.push({
      team: name,
      PTS: s.PTS,
      W: s.W,
      L: s.L,
      T: s.T,
      MP: s.MP,
      GF: Math.round(s.GF * 10) / 10,
      GA: Math.round(s.GA * 10) / 10,
      GD: Math.round((s.GF - s.GA) * 10) / 10,
      PPM: s.MP > 0 ? Math.round((s.PTS / s.MP) * 100) / 100 : 0,
      home_GF: Math.round(s.home_GF * 10) / 10,
      home_GA: Math.round(s.home_GA * 10) / 10,
      away_GF: Math.round(s.away_GF * 10) / 10,
      away_GA: Math.round(s.away_GA * 10) / 10,
      rank: 0,
    });
  });

  const h2hStatic = data.head_to_head || null;
  rankTeamsWhatIf(ranked, h2hStatic);
  return ranked;
}

export function whatifSimulateWithScores(
  data: DivisionData,
  scoresOverride: WhatifScores,
): SimRow[] {
  return simulateFromScores(data, scoresOverride);
}

export function whatifSimulate(data: DivisionData, whatifScores: WhatifScores): SimRow[] {
  return simulateFromScores(data, whatifScores);
}

export type FocusObjective = {
  rank: number;
  pts: number;
  ptsAheadOf7: number;
  ptsAheadOf6: number;
};

export function whatifFocusObjective(simStandings: SimRow[], focus: string | null): FocusObjective {
  const glens = focus ? simStandings.find((s) => s.team === focus) : null;
  const seventh = simStandings.find((s) => s.rank === 7);
  const sixth = simStandings.find((s) => s.rank === 6);
  return {
    rank: glens?.rank ?? 999,
    pts: glens?.PTS ?? -999,
    ptsAheadOf7: glens && seventh ? Number(glens.PTS) - Number(seventh.PTS) : 0,
    ptsAheadOf6: glens && sixth ? Number(glens.PTS) - Number(sixth.PTS) : 0,
  };
}

function whatifIsBetterObjective(a: FocusObjective, b: FocusObjective): boolean {
  if (a.rank !== b.rank) return a.rank < b.rank;
  if (a.ptsAheadOf7 !== b.ptsAheadOf7) return a.ptsAheadOf7 > b.ptsAheadOf7;
  if (a.pts !== b.pts) return a.pts > b.pts;
  return a.ptsAheadOf6 > b.ptsAheadOf6;
}

function whatifIsWorseObjective(a: FocusObjective, b: FocusObjective): boolean {
  if (a.rank !== b.rank) return a.rank > b.rank;
  if (a.ptsAheadOf7 !== b.ptsAheadOf7) return a.ptsAheadOf7 < b.ptsAheadOf7;
  if (a.pts !== b.pts) return a.pts < b.pts;
  return a.ptsAheadOf6 < b.ptsAheadOf6;
}

export function whatifOptimizeForFocus(
  data: DivisionData,
  mode: "best" | "worst",
  initialScores: WhatifScores,
  focusTeam: string | null,
): WhatifScores {
  const scores = whatifCloneScores(initialScores);

  const ft = focusTeam;
  if (!ft) return scores;

  getPredictionsArray(data).forEach((p) => {
    const mid = whatifMid(p);
    if (p.home === ft)
      scores[mid] = whatifCanonicalScores(mode === "best" ? "home_win" : "away_win");
    else if (p.away === ft)
      scores[mid] = whatifCanonicalScores(mode === "best" ? "away_win" : "home_win");
  });

  const preds = [...getPredictionsArray(data)].filter((p) => p.home !== ft && p.away !== ft);
  const contenders = getContenderTeams(data, ft);
  preds.sort((a, b) => {
    const aImp = (contenders.has(a.home) ? 1 : 0) + (contenders.has(a.away) ? 1 : 0);
    const bImp = (contenders.has(b.home) ? 1 : 0) + (contenders.has(b.away) ? 1 : 0);
    if (aImp !== bImp) return bImp - aImp;
    return parsePredDate(a.date).getTime() - parsePredDate(b.date).getTime();
  });

  const isBetter = mode === "best" ? whatifIsBetterObjective : whatifIsWorseObjective;
  let baseObj = whatifFocusObjective(whatifSimulateWithScores(data, scores), ft);

  preds.forEach((p) => {
    const mid = whatifMid(p);
    const candidates = ["home_win", "draw", "away_win"];
    let bestOutcome: string | null = null;
    let bestObj: FocusObjective | null = null;
    candidates.forEach((outcome) => {
      const prev = scores[mid];
      scores[mid] = whatifCanonicalScores(outcome);
      const obj = whatifFocusObjective(whatifSimulateWithScores(data, scores), ft);
      if (!bestObj || isBetter(obj, bestObj)) {
        bestObj = obj;
        bestOutcome = outcome;
      }
      scores[mid] = prev;
    });
    if (bestOutcome) {
      scores[mid] = whatifCanonicalScores(bestOutcome);
      baseObj = bestObj || baseObj;
    }
  });

  preds.forEach((p) => {
    const mid = whatifMid(p);
    const candidates = ["home_win", "draw", "away_win"];
    let bestOutcome: string | null = null;
    let bestObj = baseObj;
    candidates.forEach((outcome) => {
      const prev = scores[mid];
      scores[mid] = whatifCanonicalScores(outcome);
      const obj = whatifFocusObjective(whatifSimulateWithScores(data, scores), ft);
      if (isBetter(obj, bestObj)) {
        bestObj = obj;
        bestOutcome = outcome;
      }
      scores[mid] = prev;
    });
    if (bestOutcome) {
      scores[mid] = whatifCanonicalScores(bestOutcome);
      baseObj = bestObj;
    }
  });

  return scores;
}

function perMatchWhatIf(val: number, mp: number): number {
  return mp > 0 ? val / mp : 0;
}

function compareNonH2hWhatIf(a: SimRow, b: SimRow): number {
  const aWpm = perMatchWhatIf(Number(a.W), Number(a.MP));
  const bWpm = perMatchWhatIf(Number(b.W), Number(b.MP));
  if (Math.abs(aWpm - bWpm) > 1e-9) return bWpm - aWpm;
  const aGdpm = perMatchWhatIf(Number(a.GD), Number(a.MP));
  const bGdpm = perMatchWhatIf(Number(b.GD), Number(b.MP));
  if (Math.abs(aGdpm - bGdpm) > 1e-9) return bGdpm - aGdpm;
  const aGfpm = perMatchWhatIf(Number(a.GF), Number(a.MP));
  const bGfpm = perMatchWhatIf(Number(b.GF), Number(b.MP));
  if (Math.abs(aGfpm - bGfpm) > 1e-9) return bGfpm - aGfpm;
  const aAgd = perMatchWhatIf((a.away_GF ?? 0) - (a.away_GA ?? 0), Number(a.MP));
  const bAgd = perMatchWhatIf((b.away_GF ?? 0) - (b.away_GA ?? 0), Number(b.MP));
  if (Math.abs(aAgd - bAgd) > 1e-9) return bAgd - aAgd;
  const aAgf = perMatchWhatIf(a.away_GF ?? 0, Number(a.MP));
  const bAgf = perMatchWhatIf(b.away_GF ?? 0, Number(b.MP));
  if (Math.abs(aAgf - bAgf) > 1e-9) return bAgf - aAgf;
  const aHgd = perMatchWhatIf((a.home_GF ?? 0) - (a.home_GA ?? 0), Number(a.MP));
  const bHgd = perMatchWhatIf((b.home_GF ?? 0) - (b.home_GA ?? 0), Number(b.MP));
  if (Math.abs(aHgd - bHgd) > 1e-9) return bHgd - aHgd;
  const aHgf = perMatchWhatIf(a.home_GF ?? 0, Number(a.MP));
  const bHgf = perMatchWhatIf(b.home_GF ?? 0, Number(b.MP));
  if (Math.abs(aHgf - bHgf) > 1e-9) return bHgf - aHgf;
  return 0;
}

function compareTwoClubSamePpmWhatIf(
  a: SimRow,
  b: SimRow,
  h2h: Record<string, Record<string, H2hMini>> | null,
): number {
  const rec = h2h?.[a.team]?.[b.team];
  if (rec) {
    const aH2h = rec.W * 3 + rec.T;
    const bH2h = rec.L * 3 + rec.T;
    if (aH2h !== bH2h) return bH2h - aH2h;
  }
  return compareNonH2hWhatIf(a, b);
}

export function rankTeamsWhatIf(
  ranked: SimRow[],
  h2h: Record<string, Record<string, H2hMini>> | null,
): SimRow[] {
  ranked.sort((a, b) => {
    const diff = Number(b.PPM) - Number(a.PPM);
    if (Math.abs(diff) < 1e-9) return 0;
    return diff;
  });
  const out: SimRow[] = [];
  let i = 0;
  const n = ranked.length;
  while (i < n) {
    let j = i + 1;
    while (j < n && Math.abs(Number(ranked[j]!.PPM) - Number(ranked[i]!.PPM)) < 1e-9) j += 1;
    const group = ranked.slice(i, j);
    if (group.length === 2 && h2h) {
      group.sort((a, b) => compareTwoClubSamePpmWhatIf(a, b, h2h));
    } else {
      group.sort(compareNonH2hWhatIf);
    }
    out.push(...group);
    i = j;
  }
  ranked.length = 0;
  ranked.push(...out);
  ranked.forEach((r, idx) => {
    r.rank = idx + 1;
  });
  return ranked;
}

export function parsePredDate(dateStr: string | undefined): Date {
  if (!dateStr) return new Date(0);
  const m = dateStr.match(/(\d{2})\/(\d{2})\/(\d{2})\s+(\d{1,2}):(\d{2})(am|pm)/i);
  if (!m) return new Date(0);
  let hr = parseInt(m[4]!, 10);
  if (m[6]!.toLowerCase() === "pm" && hr !== 12) hr += 12;
  if (m[6]!.toLowerCase() === "am" && hr === 12) hr = 0;
  return new Date(
    2000 + parseInt(m[3]!, 10),
    parseInt(m[1]!, 10) - 1,
    parseInt(m[2]!, 10),
    hr,
    parseInt(m[5]!, 10),
  );
}

export function abbreviate(name: string, focusTeamName: string | null): string {
  const table: Record<string, string> = {
    "Silicon Valley Soccer Academy": "SV Soccer Academy",
    "Woodside Soccer Club Crush": "Woodside Crush",
    "Diablo Valley Futbol Club": "Diablo Valley FC",
    "Burlingame Soccer Club": "Burlingame SC",
    "Modesto Ajax United": "Modesto Ajax",
    "Sacramento United": "Sacramento Utd",
  };
  if (table[name]) return table[name];
  const ft = focusTeamName;
  if (name === ft) {
    let s = name.replace(/\s+(Soccer Club|Futbol Club|Academy)$/i, "").trim();
    if (s.length > 22) return `${s.slice(0, 20)}…`;
    return s;
  }
  return name;
}

/** Resolve default focus team from localStorage + highlight_team (same priority as legacy select). */
export function resolveFocusTeam(data: DivisionData, stored: string | null): string | null {
  const names = data.team_names || [];
  if (stored && names.includes(stored)) return stored;
  const sug = data.highlight_team;
  if (sug && names.includes(sug)) return sug;
  return names.length ? names[0]! : null;
}

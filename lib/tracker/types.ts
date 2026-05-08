/** Loose shapes for bundled division JSON (`data.json`, `/divisions/*.json`). */

export interface DivisionCatalogEntry {
  id: string;
  age_label?: string;
  division?: string;
  /** academy | homegrown | … when multi-league roots merge scrapes */
  league?: string;
}

export interface RootData {
  schema_version?: number;
  division_catalog?: DivisionCatalogEntry[];
  divisions?: DivisionData[];
  default_division_id?: string;
  [key: string]: unknown;
}

export interface GameRow {
  match_id?: string | number;
  home: string;
  away: string;
  played?: boolean;
  home_goals?: number;
  away_goals?: number;
  date?: string;
  venue?: string;
}

export interface WeeklySlice {
  week_start?: string;
  week_end?: string;
  games?: GameRow[];
  standings?: HybridStandingRow[];
}

export interface PredictionRow {
  match_id?: string | number;
  home: string;
  away: string;
  date?: string;
  venue?: string;
  predicted_outcome?: string;
  est_home_goals?: number;
  est_away_goals?: number;
  home_win_prob?: number;
  draw_prob?: number;
  away_win_prob?: number;
}

export interface StandingRow {
  team: string;
  rank?: number;
  PTS?: number;
  W?: number;
  L?: number;
  T?: number;
  MP?: number;
  GF?: number;
  GA?: number;
  GD?: number;
  PPM?: number;
  home_GF?: number;
  home_GA?: number;
  away_GF?: number;
  away_GA?: number;
}

export interface H2hMini {
  W: number;
  L: number;
  T: number;
  GF: number;
  GA: number;
}

export interface DivisionData {
  id?: string;
  age_label?: string;
  division?: string;
  league?: string;
  team_names?: string[];
  highlight_team?: string;
  weekly?: WeeklySlice[];
  predictions?: PredictionRow[];
  retro_predictions?: Record<string, PredictionRow>;
  current_standings?: StandingRow[];
  projected_final_standings?: StandingRow[];
  head_to_head?: Record<string, Record<string, H2hMini>>;
  [key: string]: unknown;
}

/** Row after ranking (includes computed rank). */
export interface HybridStandingRow extends StandingRow {
  rank: number;
}

export type WhatifScores = Record<string, { home: number; away: number }>;

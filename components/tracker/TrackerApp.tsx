"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ACTIVE_AGE_LS_KEY,
  ACTIVE_LEAGUE_LS_KEY,
  FOCUS_TEAM_LS_PREFIX,
  buildDefaultWhatifScores,
  divisionCatalogEntries,
  divisionFocusStorageKey,
  formatLeagueOptionLabel,
  preferDivisionIdInScope,
  resolveFocusTeam,
  uniqueSortedAgeLabelsFromCatalog,
  uniqueSortedLeaguesFromCatalog,
} from "@/lib/tracker/logic";
import { loadDivisionBundle } from "@/lib/tracker/loadDivision";
import type { DivisionData, RootData, WhatifScores } from "@/lib/tracker/types";
import { H2HPanel } from "./H2HPanel";
import { PredictionsPanel } from "./PredictionsPanel";
import { ProjectedPanel } from "./ProjectedPanel";
import { WeeklyPanel } from "./WeeklyPanel";
import { TrackerState } from "@/components/tracker/TrackerUi";
import { WhatIfPanel } from "./WhatIfPanel";

type Tab = "weekly" | "predictions" | "projected" | "h2h" | "whatif";

function defaultWeekIndex(data: DivisionData): number {
  let latest = 0;
  (data.weekly || []).forEach((w, i) => {
    if (w.games?.some((g) => g.played)) latest = i;
  });
  return latest;
}

export default function TrackerApp() {
  const [rootData, setRootData] = useState<RootData | null>(null);
  const [data, setData] = useState<DivisionData | null>(null);
  const [divisionId, setDivisionId] = useState<string>("");
  const [currentWeek, setCurrentWeek] = useState(0);
  const [tab, setTab] = useState<Tab>("weekly");
  const [focusTeam, setFocusTeam] = useState<string | null>(null);
  const [predFilter, setPredFilter] = useState("");
  const [predFocusOnly, setPredFocusOnly] = useState(false);
  const [h2hTeam, setH2hTeam] = useState("");
  const [whatifScores, setWhatifScores] = useState<WhatifScores>({});
  const [whatifFilter, setWhatifFilter] = useState<"all" | "focus" | "glens">("all");
  const [loadError, setLoadError] = useState<string | null>(null);

  const applyDivision = useCallback(
    async (id: string) => {
      if (!rootData) return;
      const loaded = await loadDivisionBundle(id, rootData);
      if (!loaded) {
        setDivisionId(String(data?.id ?? ""));
        return;
      }
      setRootData(loaded.root);
      setData(loaded.div);
      setDivisionId(id);
    },
    [rootData, data?.id],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch("/data.json");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const ROOT_DATA = (await resp.json()) as RootData;
        if (cancelled) return;

        const cat = divisionCatalogEntries(ROOT_DATA);
        let pick = String(ROOT_DATA.default_division_id || cat[0]?.id || "");
        const leaguesOnLoad = uniqueSortedLeaguesFromCatalog(cat);

        let leagueFilterLoad: string | undefined;
        if (leaguesOnLoad.length > 1 && typeof localStorage !== "undefined") {
          const storedLeague = localStorage.getItem(ACTIVE_LEAGUE_LS_KEY);
          if (storedLeague && leaguesOnLoad.includes(storedLeague)) {
            leagueFilterLoad = storedLeague;
          }
        }

        const scopedForAgeLoad = leagueFilterLoad
          ? cat.filter((e) => e.league === leagueFilterLoad)
          : cat;
        const agesOnLoad = uniqueSortedAgeLabelsFromCatalog(scopedForAgeLoad);

        let ageFilterLoad: string | undefined;
        if (agesOnLoad.length > 1 && typeof localStorage !== "undefined") {
          const storedAge = localStorage.getItem(ACTIVE_AGE_LS_KEY);
          if (storedAge && agesOnLoad.includes(storedAge)) {
            ageFilterLoad = storedAge;
          }
        }

        const preferredLoad = preferDivisionIdInScope(ROOT_DATA, cat, {
          league: leagueFilterLoad,
          age_label: ageFilterLoad,
        });
        if (preferredLoad) pick = preferredLoad;
        const useDivisionBundle =
          ROOT_DATA.schema_version === 2 && cat.length > 0 && pick.length > 0;

        if (useDivisionBundle) {
          const loaded = await loadDivisionBundle(pick, ROOT_DATA);
          if (cancelled) return;
          if (loaded) {
            setRootData(loaded.root);
            setData(loaded.div);
            setDivisionId(pick);
            return;
          }
          const divisions = (ROOT_DATA.divisions || []) as DivisionData[];
          const fallback = divisions.find((d) => String(d.id) === pick) ?? divisions[0];
          if (fallback) {
            setRootData(ROOT_DATA);
            setData(fallback);
            setDivisionId(String(fallback.id ?? pick));
            return;
          }
          setLoadError(
            `Could not load division "${pick}". Check data.json, run \`pnpm run export-divisions\`, or verify /divisions/${pick}.json is deployed.`,
          );
          return;
        }

        setRootData(ROOT_DATA);
        setData(ROOT_DATA as DivisionData);
        setDivisionId(String((ROOT_DATA as DivisionData).id ?? ""));
      } catch {
        setLoadError(
          "Could not load /data.json. Run `pnpm run export-divisions` after building data.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!data) return;
    const key = FOCUS_TEAM_LS_PREFIX + divisionFocusStorageKey(data);
    const stored = typeof localStorage !== "undefined" ? localStorage.getItem(key) : null;
    setFocusTeam(resolveFocusTeam(data, stored));
    setCurrentWeek(defaultWeekIndex(data));
    setWhatifScores(buildDefaultWhatifScores(data));
    setPredFilter("");
    setPredFocusOnly(false);
  }, [data?.id]);

  useEffect(() => {
    if (!data || !focusTeam) return;
    setH2hTeam(focusTeam);
  }, [data?.id, focusTeam]);

  useEffect(() => {
    if (!data || !focusTeam) return;
    const age = data.age_label ? `${data.age_label} · ` : "";
    const divName = data.division || "Division";
    const subtitle = `${age}${divName} · ${focusTeam}`;
    document.title = `${subtitle} — tracker`;
  }, [data, focusTeam]);

  useEffect(() => {
    if (tab !== "whatif" || !data) return;
    setWhatifScores((prev) => {
      if (Object.keys(prev).length > 0) return prev;
      if (!(data.predictions?.length ?? 0)) return prev;
      return buildDefaultWhatifScores(data);
    });
  }, [tab, data]);

  function persistFocus(ft: string) {
    if (!data) return;
    const key = FOCUS_TEAM_LS_PREFIX + divisionFocusStorageKey(data);
    localStorage.setItem(key, ft);
    setFocusTeam(ft);
  }

  const catalog = rootData ? divisionCatalogEntries(rootData) : [];
  const leaguesInCatalog = uniqueSortedLeaguesFromCatalog(catalog);
  const showLeaguePicker =
    !!rootData && rootData.schema_version === 2 && leaguesInCatalog.length > 1;

  const currentDivisionEntry = catalog.find((e) => e.id === divisionId);
  const activeLeagueSlug = currentDivisionEntry?.league?.trim() || leaguesInCatalog[0] || "";

  const leagueScopedCatalog = showLeaguePicker
    ? catalog.filter((e) => e.league === activeLeagueSlug)
    : catalog;

  const agesInScope = uniqueSortedAgeLabelsFromCatalog(leagueScopedCatalog);
  const showAgePicker = !!rootData && rootData.schema_version === 2 && agesInScope.length > 1;

  const activeAgeLabel = currentDivisionEntry?.age_label?.trim() || agesInScope[0] || "";

  const catalogForDivisionSelect =
    showAgePicker && activeAgeLabel
      ? leagueScopedCatalog.filter((e) => e.age_label === activeAgeLabel)
      : leagueScopedCatalog;

  const handleLeagueChange = useCallback(
    async (nextLeague: string) => {
      if (!rootData || nextLeague === activeLeagueSlug) return;
      localStorage.setItem(ACTIVE_LEAGUE_LS_KEY, nextLeague);
      const scoped = catalog.filter((e) => e.league === nextLeague);
      const ages = uniqueSortedAgeLabelsFromCatalog(scoped);
      const keepAge = ages.includes(activeAgeLabel) ? activeAgeLabel : ages[0];
      if (keepAge && typeof localStorage !== "undefined") {
        localStorage.setItem(ACTIVE_AGE_LS_KEY, keepAge);
      }
      const nextId = preferDivisionIdInScope(rootData, catalog, {
        league: nextLeague,
        age_label: keepAge,
      });
      if (nextId) await applyDivision(nextId);
    },
    [rootData, catalog, activeLeagueSlug, activeAgeLabel, applyDivision],
  );

  const handleAgeChange = useCallback(
    async (nextAge: string) => {
      if (!rootData || nextAge === activeAgeLabel) return;
      localStorage.setItem(ACTIVE_AGE_LS_KEY, nextAge);
      const nextId = preferDivisionIdInScope(rootData, catalog, {
        league: showLeaguePicker ? activeLeagueSlug : undefined,
        age_label: nextAge,
      });
      if (nextId) await applyDivision(nextId);
    },
    [rootData, catalog, activeAgeLabel, activeLeagueSlug, showLeaguePicker, applyDivision],
  );

  const showDivisionPicker =
    rootData?.schema_version === 2 &&
    (showLeaguePicker || showAgePicker ? catalogForDivisionSelect.length > 1 : catalog.length > 1);

  if (loadError) {
    return <TrackerState variant="error">{loadError}</TrackerState>;
  }

  if (!data) {
    return <TrackerState variant="loading">Loading division data…</TrackerState>;
  }

  return (
    <>
      <header>
        <h1>
          <span id="hdr-brand">Season tracker</span>{" "}
          <span id="hdr-scope">
            {data.age_label ? `${data.age_label} · ` : ""}
            {data.division || "Division"}
          </span>
        </h1>
        <div className="header-toolbar">
          {showLeaguePicker && (
            <div className="league-picker">
              <label htmlFor="league-select">League</label>
              <select
                id="league-select"
                title="Academy vs Homegrown"
                value={activeLeagueSlug}
                onChange={(e) => void handleLeagueChange(e.target.value)}
              >
                {leaguesInCatalog.map((slug) => (
                  <option key={slug} value={slug}>
                    {formatLeagueOptionLabel(slug)}
                  </option>
                ))}
              </select>
            </div>
          )}
          {showAgePicker && (
            <div className="age-picker">
              <label htmlFor="age-select">Age group</label>
              <select
                id="age-select"
                title="U13, U14, …"
                value={activeAgeLabel}
                onChange={(e) => void handleAgeChange(e.target.value)}
              >
                {agesInScope.map((label) => (
                  <option key={label} value={label}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          )}
          {showDivisionPicker && (
            <div className="division-picker">
              <label htmlFor="division-select">Division</label>
              <select
                id="division-select"
                title="Regional division within the selected league and age"
                value={divisionId}
                onChange={(e) => {
                  const id = e.target.value;
                  const entry = catalog.find((c) => c.id === id);
                  if (typeof localStorage !== "undefined") {
                    if (entry?.league) {
                      localStorage.setItem(ACTIVE_LEAGUE_LS_KEY, entry.league);
                    }
                    if (entry?.age_label) {
                      localStorage.setItem(ACTIVE_AGE_LS_KEY, entry.age_label);
                    }
                  }
                  void applyDivision(id);
                }}
              >
                {catalogForDivisionSelect.map((d) => {
                  const label = showAgePicker
                    ? d.division || d.id
                    : (d.age_label ? `${d.age_label} — ` : "") + (d.division || d.id);
                  return (
                    <option key={d.id} value={d.id}>
                      {label}
                    </option>
                  );
                })}
              </select>
            </div>
          )}
          <div className="focus-team-row">
            <label htmlFor="focus-team-select">Focus team</label>
            <select
              id="focus-team-select"
              title="Highlights, summaries, and What If use this club"
              value={focusTeam || ""}
              onChange={(e) => persistFocus(e.target.value)}
            >
              {[...(data.team_names || [])]
                .sort((a, b) => a.localeCompare(b))
                .map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
            </select>
          </div>
          <nav className="tabs" aria-label="Tracker sections">
            {(
              [
                ["weekly", "Weekly"],
                ["predictions", "Predictions"],
                ["projected", "Projected"],
                ["h2h", "H2H"],
                ["whatif", "What If"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`tab ${tab === id ? "active" : ""}`}
                data-tab={id}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="container">
        <div className={tab === "weekly" ? "" : "hidden"}>
          <WeeklyPanel
            data={data}
            currentWeek={currentWeek}
            focusTeam={focusTeam}
            onPrev={() => setCurrentWeek((w) => Math.max(0, w - 1))}
            onNext={() => setCurrentWeek((w) => Math.min((data.weekly?.length ?? 1) - 1, w + 1))}
            onWeekChange={(i) => setCurrentWeek(i)}
          />
        </div>
        <div className={tab === "predictions" ? "" : "hidden"}>
          <PredictionsPanel
            data={data}
            focusTeam={focusTeam}
            filter={predFilter}
            focusOnly={predFocusOnly}
            onFilterChange={setPredFilter}
            onFocusOnlyChange={setPredFocusOnly}
          />
        </div>
        <div className={tab === "projected" ? "" : "hidden"}>
          <ProjectedPanel data={data} focusTeam={focusTeam} />
        </div>
        <div className={tab === "h2h" ? "" : "hidden"}>
          <H2HPanel
            data={data}
            focusTeam={focusTeam}
            selectedTeam={h2hTeam || focusTeam || data.team_names?.[0] || ""}
            onTeamChange={setH2hTeam}
          />
        </div>
        <div className={tab === "whatif" ? "" : "hidden"}>
          <WhatIfPanel
            data={data}
            focusTeam={focusTeam}
            whatifScores={whatifScores}
            onWhatifScores={setWhatifScores}
            filter={whatifFilter}
            onFilterChange={setWhatifFilter}
          />
        </div>
      </main>
    </>
  );
}

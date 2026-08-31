import type { DivisionData, RootData } from "./types";

export async function loadDivisionBundle(
  divisionId: string,
  root: RootData,
): Promise<{ root: RootData; div: DivisionData } | null> {
  const next: RootData = {
    ...root,
    divisions: [...((root.divisions as DivisionData[] | undefined) || [])],
  };
  const bundles = (next.divisions || []) as DivisionData[];
  let div = bundles.find((d) => String(d.id) === String(divisionId));
  if (div) return { root: next, div };

  const shardUrl = `/divisions/${encodeURIComponent(divisionId)}.json`;
  try {
    const resp = await fetch(shardUrl);
    if (resp.ok) {
      div = (await resp.json()) as DivisionData;
      const list = (next.divisions as DivisionData[]) || [];
      const idx = list.findIndex((d) => String(d.id) === String(divisionId));
      if (idx >= 0) list[idx] = div;
      else list.push(div);
      next.divisions = list;
      return { root: next, div };
    }
  } catch {
    /* offline */
  }

  try {
    const resp = await fetch("/data.json");
    if (!resp.ok) return null;
    const full = (await resp.json()) as RootData;
    if (full.schema_version === 2 && Array.isArray(full.divisions)) {
      next.divisions = full.divisions as DivisionData[];
      div = (next.divisions as DivisionData[]).find((d) => String(d.id) === String(divisionId));
      if (div) return { root: next, div };
    }
  } catch {
    /* missing */
  }

  return null;
}

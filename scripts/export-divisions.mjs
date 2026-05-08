#!/usr/bin/env node
/**
 * Split schema_version 2 data.json into shards under public/divisions/<id>.json.
 * Copies data.json → public/data.json when present (Next/Vite dev fetch path).
 *
 * Safe no-op if data.json is missing or not multi-division.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.join(__dirname, '..');
const dataPath = path.join(rootDir, 'data.json');
const publicDir = path.join(rootDir, 'public');

if (!fs.existsSync(dataPath)) {
  console.warn('[export-divisions] No data.json — skipping (embed-only deploy ok)');
  process.exit(0);
}

let root;
try {
  root = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
} catch (e) {
  console.warn('[export-divisions] Could not parse data.json:', e.message);
  process.exit(0);
}

fs.mkdirSync(publicDir, { recursive: true });
fs.copyFileSync(dataPath, path.join(publicDir, 'data.json'));
console.log('[export-divisions] Copied data.json → public/data.json');

if (root.schema_version !== 2 || !Array.isArray(root.divisions)) {
  console.warn('[export-divisions] data.json is not multi-division — shard step skipped');
  process.exit(0);
}

const outDir = path.join(publicDir, 'divisions');
fs.mkdirSync(outDir, { recursive: true });

let n = 0;
for (const d of root.divisions) {
  const id = d.id;
  if (!id || typeof id !== 'string') continue;
  if (/[/\\]/.test(id)) {
    console.warn('[export-divisions] Skip unsafe id:', id);
    continue;
  }
  const file = path.join(outDir, `${id}.json`);
  fs.writeFileSync(file, JSON.stringify(d));
  n += 1;
}

console.log(`[export-divisions] Wrote ${n} files under public/divisions/`);

#!/bin/bash
# Re-embed data.json into index.html, and optionally rebuild data first.
#
# Usage:
#   ./refresh.sh
#       Re-embed only (keeps existing data.json). Use after build_data or scrape.
#   ./refresh.sh --from-scrape
#       python3 build_data.py --from-scrape, then re-embed (U13 NorCal from scraped_matches.json).
#   ./refresh.sh --from-academy-scrape
#       python3 build_data.py --from-academy-scrape, then re-embed.
#       Merges scraped_academy.json + scraped_homegrown.json when present (run scrape_academy.py / scrape_homegrown.py first).
#
# For the full multi-division app, serve the directory over HTTP (e.g. python3 -m http.server) so
# the page can fetch the full data.json. The embed is a slim default division for file:// fallback.

set -e

if [ "$1" = "--from-scrape" ]; then
  echo "=== Rebuilding from scraped_matches.json ==="
  python3 build_data.py --from-scrape
elif [ "$1" = "--from-academy-scrape" ]; then
  echo "=== Rebuilding from scraped_academy.json ==="
  python3 build_data.py --from-academy-scrape
elif [ -n "$1" ]; then
  echo "Unknown option: $1" >&2
  echo "Use: $0 | $0 --from-scrape | $0 --from-academy-scrape" >&2
  exit 1
else
  echo "=== Re-embed only (data.json unchanged) ==="
fi

echo ""
echo "=== Re-embedding into index.html ==="
python3 -c "
import json, re

with open('data.json') as f:
    root = json.load(f)

# Multi-division files are large; embed only the default division bundle but keep the full
# division_catalog so the header dropdown lists every age/region (switching loads data.json).
if root.get('schema_version') == 2 and root.get('divisions'):
    default_id = root.get('default_division_id')
    slim_div = None
    for d in root['divisions']:
        if d.get('id') == default_id:
            slim_div = d
            break
    if slim_div is None:
        slim_div = root['divisions'][0]
    catalog = root.get('division_catalog')
    if not catalog:
        catalog = [
            {'id': d['id'], 'age_label': d.get('age_label'), 'division': d.get('division')}
            for d in root['divisions']
        ]
    embed_obj = {
        'schema_version': 2,
        'league': root.get('league'),
        'default_division_id': slim_div.get('id'),
        'division_catalog': catalog,
        'divisions': [slim_div],
    }
else:
    embed_obj = root

data = json.dumps(embed_obj, separators=(',', ':'))

INDEX = 'public/index.html'
with open(INDEX) as f:
    html = f.read()

html = re.sub(r'<script>const EMBEDDED_DATA = .*?;</script>\s*', '', html, flags=re.DOTALL)
embedded = f'<script>const EMBEDDED_DATA = {data};</script>\n'
html = html.replace('<script>\nlet DATA = null;', embedded + '<script>\nlet DATA = null;')

with open(INDEX, 'w') as f:
    f.write(html)
print('Done!')
"

echo ""
echo "=== Division shards + public/data.json (Next / Vercel) ==="
if command -v pnpm >/dev/null 2>&1; then
  pnpm run export-divisions || true
elif command -v npm >/dev/null 2>&1; then
  npm run export-divisions || node scripts/export-divisions.mjs || true
else
  echo "Install Node + pnpm and run: pnpm install && pnpm export-divisions"
fi

echo ""
echo "=== Done. Run: pnpm dev  —  Tracker: http://localhost:3000/index.html ==="

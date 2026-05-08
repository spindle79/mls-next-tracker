async (page) => {
  const data = await page.evaluate(async () => {
    const section = "/public_schedule/";
    const age = 21, tournament = 35, list_type = '71', group = '215';

    const containers = document.querySelectorAll('.container-table-standing');
    let norcal = null;
    for (const c of containers) {
      const title = c.querySelector('.container-group-text p[data-title]');
      if (title && title.getAttribute('data-title').includes('Northern California')) { norcal = c; break; }
    }
    if (!norcal) return [];

    const teams = [];
    for (const row of norcal.querySelectorAll('.container-division-row')) {
      const mainRow = row.querySelector('.main_row');
      if (!mainRow) continue;
      const name = mainRow.querySelector('.container-team-info p[data-title]')?.getAttribute('data-title')?.trim() || '';
      const rowAttr = mainRow.getAttribute('row');
      let pagData = [];
      if (window.matchLists && window.matchLists[rowAttr]) {
        pagData = window.matchLists[rowAttr].paginationData;
      }
      teams.push({ name, pagData });
    }

    function parseMatches(html) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const rows = doc.querySelectorAll('.table-content-row.hidden-xs');
      const matches = [];
      for (const mr of rows) {
        const midDiv = mr.querySelector('.col-sm-1');
        const matchId = midDiv ? midDiv.textContent.trim().split('\n')[0].replace('MALE', '').trim() : '';
        const detailsDiv = mr.querySelector('.col-sm-2');
        let date = '', venue = '';
        if (detailsDiv) {
          const dateMatch = detailsDiv.textContent.trim().match(/(\d{2}\/\d{2}\/\d{2}\s+\d{1,2}:\d{2}[ap]m)/);
          if (dateMatch) date = dateMatch[1];
          const venueP = detailsDiv.querySelector('p[data-title]');
          if (venueP) venue = venueP.getAttribute('data-title').trim();
        }
        const home = mr.querySelector('.container-first-team p[data-title]')?.getAttribute('data-title')?.trim() || '';
        const away = mr.querySelector('.container-second-team p[data-title]')?.getAttribute('data-title')?.trim() || '';
        const scoreSpan = mr.querySelector('.score-match-table');
        const score = scoreSpan ? scoreSpan.textContent.trim().replace(/\u00a0/g, ' ') : '';
        if (matchId) matches.push({ match_id: matchId, date, venue, home, away, score });
      }
      return matches;
    }

    async function fetchPage(pagData, pageNum) {
      const params = new URLSearchParams({
        open_page: pageNum,
        pagination_data: JSON.stringify(pagData),
        bracket: '', age, tournament, group, list_type,
      });
      const resp = await fetch(section + 'league/get_partial_matches_by_team?' + params.toString());
      return await resp.text();
    }

    const results = [];
    for (const team of teams) {
      const allMatches = [];
      const seenIds = new Set();
      for (let p = 1; p <= 3; p++) {
        const html = await fetchPage(team.pagData, p);
        const matches = parseMatches(html);
        const newMatches = matches.filter(m => !seenIds.has(m.match_id));
        if (newMatches.length === 0) break;
        newMatches.forEach(m => { seenIds.add(m.match_id); allMatches.push(m); });
        if (matches.length < 10) break;
      }
      results.push({ name: team.name, matchCount: allMatches.length, matches: allMatches });
    }
    return results;
  });
  return JSON.stringify(data);
}

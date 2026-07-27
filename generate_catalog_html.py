#!/usr/bin/env python3
"""Render bird_catalog_data.json into a single self-contained HTML page
(bird_catalog.html) with searchable species cards. Clicking a card opens a
modal that fetches a description + photo from Wikipedia client-side and lists
every recorded sighting of that species.

Usage:
    generate_catalog_html.py [--data bird_catalog_data.json] \
        [--out bird_catalog.html]
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird Song Catalog</title>
<style>
  :root {
    --bg: #0f1720; --panel: #17212b; --panel2: #1e2b38;
    --text: #e7edf3; --muted: #9fb0c0; --accent: #6bd08a; --border: #2a3a49;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
  }
  header {
    padding: 32px 20px 20px; text-align: center;
    background: linear-gradient(160deg, #1b2a1f, #0f1720);
    border-bottom: 1px solid var(--border);
  }
  header h1 { margin: 0 0 6px; font-size: 2rem; }
  header p { margin: 0; color: var(--muted); }
  .stats { display: flex; gap: 24px; justify-content: center; flex-wrap: wrap; margin-top: 18px; }
  .stat { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 18px; min-width: 90px; }
  .stat .num { font-size: 1.6rem; font-weight: 700; color: var(--accent); }
  .stat .lbl { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  main { max-width: 1100px; margin: 0 auto; padding: 24px 20px 60px; }
  .search-wrap { margin: 0 auto 24px; max-width: 480px; }
  #search {
    width: 100%; padding: 12px 16px; font-size: 1rem; border-radius: 10px;
    border: 1px solid var(--border); background: var(--panel); color: var(--text);
  }
  #search:focus { outline: none; border-color: var(--accent); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; cursor: pointer; transition: transform .1s ease, border-color .1s ease;
  }
  .card:hover { transform: translateY(-3px); border-color: var(--accent); }
  .card h3 { margin: 0 0 4px; font-size: 1.1rem; }
  .card .sci { margin: 0 0 10px; font-style: italic; color: var(--muted); font-size: 0.85rem; }
  .card .meta { display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--muted); }
  .card .badge { background: var(--panel2); border-radius: 20px; padding: 2px 10px; color: var(--accent); font-weight: 600; }
  .empty { text-align: center; color: var(--muted); padding: 40px; }
  /* Modal */
  .overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,.6); display: none;
    align-items: flex-start; justify-content: center; padding: 40px 16px; overflow-y: auto; z-index: 10;
  }
  .overlay.open { display: flex; }
  .modal {
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
    max-width: 640px; width: 100%; padding: 24px; position: relative;
  }
  .modal .close {
    position: absolute; top: 12px; right: 14px; background: none; border: none;
    color: var(--muted); font-size: 1.6rem; cursor: pointer; line-height: 1;
  }
  .modal h2 { margin: 0 0 2px; padding-right: 30px; }
  .modal .sci { font-style: italic; color: var(--muted); margin: 0 0 16px; }
  .wiki { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
  .wiki img { width: 180px; max-width: 100%; border-radius: 10px; object-fit: cover; background: var(--panel2); }
  .wiki .desc { flex: 1; min-width: 200px; color: var(--text); font-size: 0.92rem; }
  .wiki .desc a { color: var(--accent); }
  .wiki .loading, .wiki .fallback { color: var(--muted); font-style: italic; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; }
  td.conf { color: var(--accent); font-weight: 600; }
  .table-scroll { overflow-x: auto; }
  footer { text-align: center; color: var(--muted); font-size: 0.8rem; padding: 20px; }
</style>
</head>
<body>
<header>
  <h1>&#127925; Bird Song Catalog</h1>
  <p>Species detected from field audio recordings</p>
  <div class="stats">
    <div class="stat"><div class="num" id="stat-species">0</div><div class="lbl">Species</div></div>
    <div class="stat"><div class="num" id="stat-sightings">0</div><div class="lbl">Sightings</div></div>
    <div class="stat"><div class="num" id="stat-locations">0</div><div class="lbl">Locations</div></div>
  </div>
</header>
<main>
  <div class="search-wrap">
    <input id="search" type="search" placeholder="Search species by name..." autocomplete="off">
  </div>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" style="display:none">No species match your search.</div>
</main>
<footer>Generated from bird_catalog_data.json &middot; Photos &amp; facts from Wikipedia</footer>

<div class="overlay" id="overlay">
  <div class="modal" id="modal">
    <button class="close" id="close" aria-label="Close">&times;</button>
    <h2 id="m-name"></h2>
    <p class="sci" id="m-sci"></p>
    <div class="wiki" id="m-wiki"></div>
    <h3 style="margin:0 0 8px">Sightings</h3>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Location</th><th>Date</th><th>Confidence</th><th>Recording</th></tr></thead>
        <tbody id="m-sightings"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
// Catalog data is embedded directly so this file is fully portable.
const CATALOG = __CATALOG_JSON__;

const speciesList = Object.values(CATALOG.species || {}).sort(
  (a, b) => a.common_name.localeCompare(b.common_name));

function computeStats() {
  let sightings = 0; const locs = new Set();
  for (const sp of speciesList) {
    sightings += (sp.sightings || []).length;
    for (const s of (sp.sightings || [])) locs.add(s.location);
  }
  document.getElementById('stat-species').textContent = speciesList.length;
  document.getElementById('stat-sightings').textContent = sightings;
  document.getElementById('stat-locations').textContent = locs.size;
}

function locationSummary(sp) {
  const locs = [...new Set((sp.sightings || []).map(s => s.location))];
  if (locs.length <= 2) return locs.join(', ');
  return locs.slice(0, 2).join(', ') + ' +' + (locs.length - 2);
}

function renderGrid(filter) {
  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  grid.innerHTML = '';
  const f = (filter || '').trim().toLowerCase();
  let shown = 0;
  for (const sp of speciesList) {
    const hay = (sp.common_name + ' ' + (sp.scientific_name || '')).toLowerCase();
    if (f && !hay.includes(f)) continue;
    shown++;
    const card = document.createElement('div');
    card.className = 'card';
    const count = (sp.sightings || []).length;
    card.innerHTML =
      '<h3></h3><p class="sci"></p>' +
      '<div class="meta"><span class="badge"></span><span class="locs"></span></div>';
    card.querySelector('h3').textContent = sp.common_name;
    card.querySelector('.sci').textContent = sp.scientific_name || '';
    card.querySelector('.badge').textContent = count + (count === 1 ? ' sighting' : ' sightings');
    card.querySelector('.locs').textContent = locationSummary(sp);
    card.addEventListener('click', () => openModal(sp));
    grid.appendChild(card);
  }
  empty.style.display = shown === 0 ? 'block' : 'none';
}

function openModal(sp) {
  document.getElementById('m-name').textContent = sp.common_name;
  document.getElementById('m-sci').textContent = sp.scientific_name || '';

  const tbody = document.getElementById('m-sightings');
  tbody.innerHTML = '';
  const sightings = (sp.sightings || []).slice().sort((a, b) =>
    (b.date || '').localeCompare(a.date || ''));
  for (const s of sightings) {
    const tr = document.createElement('tr');
    const conf = s.confidence != null ? Math.round(s.confidence * 100) + '%' : '-';
    for (const [cls, val] of [['', s.location], ['', s.date],
        ['conf', conf], ['', s.recording_file || '-']]) {
      const td = document.createElement('td');
      if (cls) td.className = cls;
      td.textContent = val || '-';
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  const wiki = document.getElementById('m-wiki');
  wiki.innerHTML = '<p class="loading">Loading photo and facts from Wikipedia...</p>';
  fetchWiki(sp.common_name, wiki);

  document.getElementById('overlay').classList.add('open');
}

function fetchWiki(name, container) {
  const title = encodeURIComponent(name.replace(/ /g, '_'));
  const url = 'https://en.wikipedia.org/api/rest_v1/page/summary/' + title;
  fetch(url)
    .then(r => { if (!r.ok) throw new Error('not found'); return r.json(); })
    .then(data => {
      if (data.type && data.type.indexOf('not_found') !== -1) throw new Error('not found');
      const img = data.thumbnail && data.thumbnail.source;
      const extract = data.extract || 'No description available.';
      const pageUrl = data.content_urls && data.content_urls.desktop &&
        data.content_urls.desktop.page;
      container.innerHTML = '';
      if (img) {
        const el = document.createElement('img');
        el.src = img; el.alt = name; el.loading = 'lazy';
        container.appendChild(el);
      }
      const desc = document.createElement('div');
      desc.className = 'desc';
      const p = document.createElement('p');
      p.textContent = extract;
      desc.appendChild(p);
      if (pageUrl) {
        const a = document.createElement('a');
        a.href = pageUrl; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = 'Read more on Wikipedia →';
        desc.appendChild(a);
      }
      container.appendChild(desc);
    })
    .catch(() => {
      container.innerHTML = '<p class="fallback">Could not load Wikipedia info ' +
        '(offline or no matching article for “' + name + '”).</p>';
    });
}

function closeModal() { document.getElementById('overlay').classList.remove('open'); }

document.getElementById('close').addEventListener('click', closeModal);
document.getElementById('overlay').addEventListener('click', e => {
  if (e.target.id === 'overlay') closeModal();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
document.getElementById('search').addEventListener('input', e => renderGrid(e.target.value));

computeStats();
renderGrid('');
</script>
</body>
</html>
"""


def main():
    p = argparse.ArgumentParser(description="Render the catalog to HTML.")
    p.add_argument("--data", default=os.path.join(HERE, "bird_catalog_data.json"))
    p.add_argument("--out", default=os.path.join(HERE, "bird_catalog.html"))
    args = p.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Embed the JSON as a JS object literal. json.dumps is valid JS; escape
    # </script> so the payload can't break out of the <script> block.
    embedded = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = PAGE_TEMPLATE.replace("__CATALOG_JSON__", embedded)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    n_species = len(data.get("species", {}))
    print(f"Wrote {args.out} ({n_species} species).")


if __name__ == "__main__":
    main()

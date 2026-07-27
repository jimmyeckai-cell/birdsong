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
import base64
import copy
import json
import os

import catalog_clips as cc

HERE = os.path.dirname(os.path.abspath(__file__))


def attach_top_clips(data):
    """Return a deep copy of the catalog with each species' top songs (and their
    embedded base64 OGG audio, when a cached clip exists) attached as
    `top_clips`. The audio is embedded only in the HTML, never written back to
    bird_catalog_data.json, which stays audio-free."""
    out = copy.deepcopy(data)
    for entry in out.get("species", {}).values():
        clips = []
        for song in cc.top_songs(entry):
            start = song.get("start_time_sec")
            end = song.get("end_time_sec")
            audio = None
            if start is not None and end is not None:
                path = cc.clip_path(cc.clip_id(song["recording_file"], start, end))
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    audio = "data:audio/ogg;base64," + b64
            clips.append({
                "confidence": song.get("confidence"),
                "recording_file": song.get("recording_file"),
                "location": song.get("location"),
                "date": song.get("date"),
                "start_time_sec": start,
                "end_time_sec": end,
                "audio": audio,
            })
        entry["top_clips"] = clips
    return out


def attach_sketches(data):
    """Embed each species' cached pencil sketch (sketches/<slug>.png) as a
    base64 PNG data URI on the entry as `sketch` (None if no cached sketch)."""
    for entry in data.get("species", {}).values():
        path = cc.sketch_path(entry.get("common_name"))
        if os.path.exists(path):
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            entry["sketch"] = "data:image/png;base64," + b64
        else:
            entry["sketch"] = None
    return data

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird Song Catalog</title>
<style>
  :root {
    --bg: #ffffff; --panel: #ffffff; --panel2: #f3f6f4;
    --text: #1b2a22; --muted: #6b7b72; --accent: #2e7d46; --border: #e3e9e5;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
  }
  header {
    padding: 36px 20px 22px; text-align: center;
    background: var(--bg); border-bottom: 1px solid var(--border);
  }
  header h1 { margin: 0 0 6px; font-size: 2rem; letter-spacing: -0.01em; }
  header p { margin: 0; color: var(--muted); }
  .stats { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; margin-top: 20px; }
  .stat { background: var(--panel2); border-radius: 10px; padding: 10px 18px; min-width: 88px; }
  .stat .num { font-size: 1.6rem; font-weight: 700; color: var(--accent); }
  .stat .lbl { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  main { max-width: 1120px; margin: 0 auto; padding: 24px 20px 60px; }
  .search-wrap { margin: 0 auto 26px; max-width: 460px; }
  #search {
    width: 100%; padding: 12px 16px; font-size: 1rem; border-radius: 10px;
    border: 1px solid var(--border); background: var(--panel); color: var(--text);
  }
  #search:focus { outline: none; border-color: var(--accent); }

  /* Bird sketch grid */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 22px; }
  .bird { cursor: pointer; text-align: center; }
  .sketch-wrap {
    position: relative; background: #fff; border: 1px solid var(--border);
    border-radius: 14px; overflow: hidden; aspect-ratio: 1 / 1;
    display: flex; align-items: center; justify-content: center;
    transition: box-shadow .15s ease, transform .15s ease, border-color .15s ease;
  }
  .bird:hover .sketch-wrap { box-shadow: 0 8px 22px rgba(0,0,0,.10); transform: translateY(-3px); border-color: #cfe0d5; }
  .bird.playing .sketch-wrap { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
  .sketch { max-width: 88%; max-height: 88%; object-fit: contain; }
  .sketch.fallback { width: 45%; height: 45%; opacity: .35; }
  .bird-name { margin-top: 10px; font-weight: 600; font-size: 0.95rem; }
  .bird-sci { font-style: italic; color: var(--muted); font-size: 0.8rem; }

  /* Hover info overlay on each sketch */
  .hoverinfo {
    position: absolute; inset: 0; background: rgba(255,255,255,.95);
    padding: 14px; display: flex; flex-direction: column; justify-content: center;
    gap: 4px; opacity: 0; pointer-events: none; transition: opacity .15s ease;
    text-align: left;
  }
  .bird:hover .hoverinfo { opacity: 1; pointer-events: auto; }
  .hoverinfo .hi-name { font-weight: 700; font-size: 0.98rem; }
  .hoverinfo .hi-sci { font-style: italic; color: var(--muted); font-size: 0.78rem; margin-bottom: 4px; }
  .hoverinfo .hi-row { font-size: 0.8rem; color: var(--text); }
  .hoverinfo .hi-row b { color: var(--accent); }
  .hoverinfo .hi-play { margin-top: 8px; font-size: 0.82rem; color: var(--accent); font-weight: 600; }
  .hoverinfo .hi-details {
    margin-top: 6px; align-self: flex-start; background: var(--panel2); border: 1px solid var(--border);
    color: var(--text); border-radius: 8px; padding: 4px 10px; font-size: 0.78rem; cursor: pointer;
  }
  .hoverinfo .hi-details:hover { border-color: var(--accent); color: var(--accent); }
  .empty { text-align: center; color: var(--muted); padding: 40px; }

  /* Modal */
  .overlay {
    position: fixed; inset: 0; background: rgba(20,30,25,.45); display: none;
    align-items: flex-start; justify-content: center; padding: 40px 16px; overflow-y: auto; z-index: 10;
  }
  .overlay.open { display: flex; }
  .modal {
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
    max-width: 640px; width: 100%; padding: 24px; position: relative;
    box-shadow: 0 20px 60px rgba(0,0,0,.2);
  }
  .modal .close {
    position: absolute; top: 12px; right: 14px; background: none; border: none;
    color: var(--muted); font-size: 1.6rem; cursor: pointer; line-height: 1;
  }
  .modal h2 { margin: 0 0 2px; padding-right: 30px; }
  .modal .sci { font-style: italic; color: var(--muted); margin: 0 0 10px; }
  .modal .summary { margin: 0 0 16px; font-size: 0.9rem; color: var(--text); }
  .modal .summary b { color: var(--accent); }
  #m-clips-wrap { margin-bottom: 20px; }
  .clip { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .clip:last-child { border-bottom: none; }
  .clip .rank { color: var(--accent); font-weight: 700; }
  .clip .clip-meta { font-size: 0.82rem; color: var(--muted); min-width: 170px; flex: 1; }
  .clip .clip-meta b { color: var(--accent); }
  .clip audio { height: 34px; max-width: 100%; }
  .clip .noaudio { font-style: italic; color: var(--muted); font-size: 0.82rem; }
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
  <p>Hover a bird for details &middot; click it to hear its best song</p>
  <div class="stats">
    <div class="stat"><div class="num" id="stat-species">0</div><div class="lbl">Species</div></div>
    <div class="stat"><div class="num" id="stat-sessions">0</div><div class="lbl">Sessions</div></div>
    <div class="stat"><div class="num" id="stat-songs">0</div><div class="lbl">Songs</div></div>
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
<footer>Generated from bird_catalog_data.json &middot; Sketches &amp; facts from Wikipedia</footer>

<div class="overlay" id="overlay">
  <div class="modal" id="modal">
    <button class="close" id="close" aria-label="Close">&times;</button>
    <h2 id="m-name"></h2>
    <p class="sci" id="m-sci"></p>
    <p class="summary" id="m-summary"></p>
    <div class="wiki" id="m-wiki"></div>
    <div id="m-clips-wrap" style="display:none">
      <h3 style="margin:0 0 8px">Top songs</h3>
      <div id="m-clips"></div>
    </div>
    <h3 style="margin:0 0 8px">Sessions</h3>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Location</th><th>Date</th><th>Recording</th><th>Songs</th><th>Highest</th><th>Avg</th></tr></thead>
        <tbody id="m-sessions"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
// Catalog data is embedded directly so this file is fully portable.
const CATALOG = __CATALOG_JSON__;

const speciesList = Object.values(CATALOG.species || {}).sort(
  (a, b) => a.common_name.localeCompare(b.common_name));

function sessionsOf(sp) { return sp.sessions || []; }
function songsOf(session) { return session.songs || []; }
function allSongs(sp) {
  const out = [];
  for (const s of sessionsOf(sp)) for (const g of songsOf(s)) out.push(g);
  return out;
}
// {high, avg} confidence (0-1) over a list of songs, or null if empty.
function confStats(songs) {
  if (!songs.length) return null;
  let high = 0, sum = 0;
  for (const g of songs) {
    const c = g.confidence || 0;
    if (c > high) high = c;
    sum += c;
  }
  return { high: high, avg: sum / songs.length };
}
function pct(x) { return Math.round(x * 100) + '%'; }
function fmtTime(sec) {
  if (sec == null) return '?';
  const s = Math.floor(sec % 60), m = Math.floor(sec / 60);
  return m + ':' + String(s).padStart(2, '0');
}

function renderClips(sp) {
  const wrap = document.getElementById('m-clips-wrap');
  const box = document.getElementById('m-clips');
  box.innerHTML = '';
  const clips = sp.top_clips || [];
  if (!clips.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';
  clips.forEach((c, i) => {
    const row = document.createElement('div');
    row.className = 'clip';

    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = '#' + (i + 1);
    row.appendChild(rank);

    const meta = document.createElement('span');
    meta.className = 'clip-meta';
    const conf = c.confidence != null ? pct(c.confidence) : '-';
    meta.innerHTML = '<b>' + conf + '</b> · ' + fmtTime(c.start_time_sec) +
      '–' + fmtTime(c.end_time_sec) + ' · ' + (c.location || '') +
      ' · ' + (c.recording_file || '');
    row.appendChild(meta);

    if (c.audio) {
      const audio = document.createElement('audio');
      audio.controls = true;
      audio.preload = 'none';
      audio.src = c.audio;
      row.appendChild(audio);
    } else {
      const na = document.createElement('span');
      na.className = 'noaudio';
      na.textContent = '(audio not available on this machine)';
      row.appendChild(na);
    }
    box.appendChild(row);
  });
}

function computeStats() {
  let sessions = 0, songs = 0; const locs = new Set();
  for (const sp of speciesList) {
    for (const sess of sessionsOf(sp)) {
      sessions++;
      songs += songsOf(sess).length;
      locs.add(sess.location);
    }
  }
  document.getElementById('stat-species').textContent = speciesList.length;
  document.getElementById('stat-sessions').textContent = sessions;
  document.getElementById('stat-songs').textContent = songs;
  document.getElementById('stat-locations').textContent = locs.size;
}

function locationSummary(sp) {
  const locs = [...new Set(sessionsOf(sp).map(s => s.location))];
  if (locs.length <= 2) return locs.join(', ');
  return locs.slice(0, 2).join(', ') + ' +' + (locs.length - 2);
}

// Simple bird-silhouette fallback when a species has no cached sketch.
const FALLBACK_SKETCH = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#8aa596">' +
  '<path d="M22 6c-1 0-2 .5-2.5 1.4C18.8 5.4 16.6 4 14 4c-3.9 0-7 3.1-7 7 0 .3 0 .6.1.9' +
  'C4.7 12.4 3 14.5 3 17c0 .6.4 1 1 1 2.5 0 4.6-1.7 5.1-4 .3 0 .6.1.9.1 3.9 0 7-3.1 7-7' +
  ' 0-.4 0-.7-.1-1.1.6-.3 1.1-.9 1.4-1.6.3.1.5.1.7.1.6 0 1-.4 1-1s-.4-1-1-1z"/></svg>');

// One shared player so a new click stops whatever was playing.
let currentAudio = null;
let currentBird = null;

function stopCurrent() {
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  if (currentBird) { currentBird.classList.remove('playing'); currentBird = null; }
}

function playTopSong(sp, birdEl) {
  const clip = (sp.top_clips || [])[0];
  // Clicking the currently-playing bird stops it (toggle).
  if (currentBird === birdEl) { stopCurrent(); return; }
  stopCurrent();
  if (!clip || !clip.audio) return;   // no audio available
  const audio = new Audio(clip.audio);
  currentAudio = audio; currentBird = birdEl;
  birdEl.classList.add('playing');
  audio.addEventListener('ended', () => {
    if (currentBird === birdEl) stopCurrent();
  });
  audio.play().catch(() => stopCurrent());
}

function renderGrid(filter) {
  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  stopCurrent();
  grid.innerHTML = '';
  const f = (filter || '').trim().toLowerCase();
  let shown = 0;
  for (const sp of speciesList) {
    const hay = (sp.common_name + ' ' + (sp.scientific_name || '')).toLowerCase();
    if (f && !hay.includes(f)) continue;
    shown++;

    const nSessions = sessionsOf(sp).length;
    const nSongs = allSongs(sp).length;
    const stats = confStats(allSongs(sp));
    const hasAudio = !!((sp.top_clips || [])[0] || {}).audio;

    const bird = document.createElement('div');
    bird.className = 'bird';

    const wrap = document.createElement('div');
    wrap.className = 'sketch-wrap';

    const img = document.createElement('img');
    img.className = 'sketch' + (sp.sketch ? '' : ' fallback');
    img.src = sp.sketch || FALLBACK_SKETCH;
    img.alt = sp.common_name + ' sketch';
    img.loading = 'lazy';
    wrap.appendChild(img);

    // Hover info overlay.
    const info = document.createElement('div');
    info.className = 'hoverinfo';
    const playLine = hasAudio ? '▶ Click to play top song'
                              : '(no audio for this species yet)';
    info.innerHTML =
      '<div class="hi-name"></div><div class="hi-sci"></div>' +
      '<div class="hi-row"><b>' + nSessions + '</b> session' + (nSessions === 1 ? '' : 's') +
      ' · <b>' + nSongs + '</b> song' + (nSongs === 1 ? '' : 's') + '</div>' +
      '<div class="hi-row">Top confidence <b>' + (stats ? pct(stats.high) : '-') + '</b></div>' +
      '<div class="hi-row hi-loc"></div>' +
      '<div class="hi-play">' + playLine + '</div>';
    info.querySelector('.hi-name').textContent = sp.common_name;
    info.querySelector('.hi-sci').textContent = sp.scientific_name || '';
    info.querySelector('.hi-loc').textContent = locationSummary(sp);

    const details = document.createElement('button');
    details.className = 'hi-details';
    details.textContent = 'Details ▸';
    details.addEventListener('click', (e) => { e.stopPropagation(); openModal(sp); });
    info.appendChild(details);
    wrap.appendChild(info);

    bird.appendChild(wrap);

    const nameEl = document.createElement('div');
    nameEl.className = 'bird-name';
    nameEl.textContent = sp.common_name;
    bird.appendChild(nameEl);

    bird.addEventListener('click', () => playTopSong(sp, bird));
    grid.appendChild(bird);
  }
  empty.style.display = shown === 0 ? 'block' : 'none';
}

function openModal(sp) {
  document.getElementById('m-name').textContent = sp.common_name;
  document.getElementById('m-sci').textContent = sp.scientific_name || '';

  // Species-level confidence summary across all sessions.
  const sessions = sessionsOf(sp);
  const overall = confStats(allSongs(sp));
  const nSongs = allSongs(sp).length;
  const summary = document.getElementById('m-summary');
  if (overall) {
    summary.innerHTML =
      'Heard in <b>' + sessions.length + '</b> session' +
      (sessions.length === 1 ? '' : 's') + ' · <b>' + nSongs + '</b> song' +
      (nSongs === 1 ? '' : 's') + ' · highest confidence <b>' +
      pct(overall.high) + '</b> · average <b>' + pct(overall.avg) + '</b>';
  } else {
    summary.textContent = '';
  }

  const tbody = document.getElementById('m-sessions');
  tbody.innerHTML = '';
  const rows = sessions.slice().sort((a, b) =>
    (b.date || '').localeCompare(a.date || ''));
  for (const sess of rows) {
    const songs = songsOf(sess);
    const st = confStats(songs);
    const tr = document.createElement('tr');
    const cells = [
      ['', sess.location],
      ['', sess.date],
      ['', sess.recording_file || '-'],
      ['', String(songs.length)],
      ['conf', st ? pct(st.high) : '-'],
      ['conf', st ? pct(st.avg) : '-'],
    ];
    for (const [cls, val] of cells) {
      const td = document.createElement('td');
      if (cls) td.className = cls;
      td.textContent = val || '-';
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  renderClips(sp);

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

    # Attach top-song clips (embedded audio) and pencil sketches for the page.
    augmented = attach_top_clips(data)
    attach_sketches(augmented)

    # Embed the JSON as a JS object literal. json.dumps is valid JS; escape
    # </script> so the payload can't break out of the <script> block.
    embedded = json.dumps(augmented, ensure_ascii=False).replace("</", "<\\/")
    html = PAGE_TEMPLATE.replace("__CATALOG_JSON__", embedded)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    n_species = len(data.get("species", {}))
    with_audio = sum(
        1 for e in augmented.get("species", {}).values()
        for c in e.get("top_clips", []) if c.get("audio"))
    total_clips = sum(
        len(e.get("top_clips", [])) for e in augmented.get("species", {}).values())
    size_kb = os.path.getsize(args.out) / 1024
    print(f"Wrote {args.out} ({n_species} species, {with_audio}/{total_clips} "
          f"top-song clips with audio embedded, {size_kb:.0f} KB).")


if __name__ == "__main__":
    main()

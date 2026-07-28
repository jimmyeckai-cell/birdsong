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

# A species is only shown in the catalog if at least one of its songs reaches
# this confidence. Lower-confidence species stay stored in the JSON (and
# embedded in the page) but hidden — change this one number to reveal them.
DISPLAY_MIN_CONF = 0.5


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


ART_EMBED_MAX_W = 560  # px; source images are downscaled to keep the page small


def _has_alpha(img):
    return img.mode in ("RGBA", "LA") or (img.mode == "P"
                                          and "transparency" in img.info)


def _embed_art(path):
    """Return a base64 data URI for a source image, downscaled to keep the page
    small. Transparent cutouts are trimmed to the bird and kept as WebP with
    alpha; opaque images are flattened/encoded as JPEG. Falls back to raw bytes
    if Pillow processing fails."""
    try:
        import io
        from PIL import Image
        img = Image.open(path)
        if _has_alpha(img):
            img = img.convert("RGBA")
            bbox = img.split()[-1].getbbox()  # crop away transparent margins
            if bbox:
                img = img.crop(bbox)
            w, h = img.size
            if w > ART_EMBED_MAX_W:
                img = img.resize((ART_EMBED_MAX_W,
                                  max(1, int(h * ART_EMBED_MAX_W / w))))
            # Add a uniform transparent margin so the bird never visually touches
            # a tile/scene edge (and any tight-cropped wingtip gets breathing room).
            pad = max(6, round(0.05 * max(img.size)))
            padded = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad),
                               (0, 0, 0, 0))
            padded.paste(img, (pad, pad))
            img = padded
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=90, method=6)  # alpha-preserving
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return "data:image/webp;base64," + b64
        # Opaque: flatten onto white and encode JPEG.
        img = img.convert("RGB")
        w, h = img.size
        if w > ART_EMBED_MAX_W:
            img = img.resize((ART_EMBED_MAX_W, max(1, int(h * ART_EMBED_MAX_W / w))))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return "data:image/jpeg;base64," + b64
    except Exception:
        import mimetypes
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return "data:" + mime + ";base64," + b64


def attach_art(data):
    """Embed each species' best artwork (custom_art/ preferred, else the auto
    watercolor) as a base64 data URI on the entry as `art` (None if neither)."""
    for entry in data.get("species", {}).values():
        path = cc.resolve_art_path(entry.get("common_name"))
        entry["art"] = _embed_art(path) if path else None
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

  [hidden] { display: none !important; }

  /* Landing view — minimal watercolor gallery */
  #view-landing { min-height: 100vh; padding: 54px 24px 130px; }
  .kpi { text-align: center; margin: 4px auto 44px; }
  .kpi-num { font-size: 3.2rem; font-weight: 700; color: var(--accent); line-height: 1; }
  .kpi-label { font-size: 0.78rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted); margin-top: 6px; }
  /* Free-placement scene (Where's-Waldo style scatter) */
  .scene {
    position: relative; width: 100%; max-width: 1200px; margin: 0 auto;
    aspect-ratio: 3 / 2;
  }
  .scene-bird {
    position: absolute; transform: translate(-50%, -50%) rotate(var(--rot, 0deg));
    cursor: pointer; will-change: transform;
  }
  .scene-bird img {
    display: block; width: 100%; height: auto;
    filter: drop-shadow(0 3px 5px rgba(0,0,0,.14));
    transition: transform .15s ease;
  }
  .scene-bird img.fallback { opacity: .35; }
  .scene-bird:hover { z-index: 999 !important; }
  .scene-bird:hover img { transform: scale(1.07); }
  .scene-bird.playing img { filter: drop-shadow(0 0 0 2px var(--accent)) drop-shadow(0 3px 5px rgba(0,0,0,.14)); }
  /* Name is hidden until you hover the bird. */
  .scene-bird .scene-name {
    position: absolute; left: 50%; bottom: -18px; transform: translateX(-50%);
    white-space: nowrap; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: #34403a; opacity: 0; pointer-events: none;
    transition: opacity .15s ease;
    text-shadow: 0 1px 3px rgba(255,255,255,.95), 0 0 8px rgba(255,255,255,.9);
  }
  .scene-bird:hover .scene-name { opacity: 1; }
  .explore-bar {
    position: fixed; left: 0; right: 0; bottom: 0; display: flex; justify-content: center;
    padding: 22px; pointer-events: none;
    background: linear-gradient(to top, rgba(255,255,255,.96) 40%, rgba(255,255,255,0));
  }
  .explore-btn {
    pointer-events: auto; background: var(--accent); color: #fff; border: none;
    border-radius: 999px; padding: 14px 32px; font-size: 0.95rem; letter-spacing: 0.04em;
    cursor: pointer; box-shadow: 0 6px 20px rgba(46,125,70,.35);
    transition: transform .12s ease, background .12s ease;
  }
  .explore-btn:hover { transform: translateY(-2px); background: #26683a; }

  /* Explore view */
  #view-explore { padding-bottom: 110px; }

  /* Bird sketch grid */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 22px; }
  .bird { cursor: pointer; text-align: center; }
  .sketch-wrap {
    position: relative; background: #fff; border: 1px solid var(--border);
    border-radius: 14px; overflow: hidden; aspect-ratio: 1 / 1; padding: 14px;
    display: flex; align-items: center; justify-content: center;
    transition: box-shadow .15s ease, transform .15s ease, border-color .15s ease;
  }
  .bird:hover .sketch-wrap { box-shadow: 0 8px 22px rgba(0,0,0,.10); transform: translateY(-3px); border-color: #cfe0d5; }
  .bird.playing .sketch-wrap { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
  /* width+height 100% + object-fit:contain guarantees the WHOLE bird fits,
     scaling down as needed so portrait birds no longer overflow and clip. */
  .sketch { width: 100%; height: 100%; object-fit: contain; }
  .sketch.fallback { width: 45%; height: 45%; object-fit: contain; opacity: .35; }
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

<!-- ============ LANDING VIEW (minimal watercolor gallery) ============ -->
<section id="view-landing" class="view">
  <div class="kpi">
    <div class="kpi-num" id="kpi-num">0</div>
    <div class="kpi-label">species identified</div>
  </div>
  <div class="scene" id="scene"></div>
  <div class="explore-bar">
    <button id="go-explore" class="explore-btn">Explore database</button>
  </div>
</section>

<!-- ================ EXPLORE VIEW (full catalog) ==================== -->
<section id="view-explore" class="view" hidden>
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
  <footer>Generated from bird_catalog_data.json &middot; Watercolors &amp; facts from Wikipedia</footer>
  <div class="explore-bar">
    <button id="go-mural" class="explore-btn">Explore mural</button>
  </div>
</section>

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

// Only species with a detection at/above this confidence are displayed.
// Everything is still embedded above, so lowering this reveals the rest.
const DISPLAY_MIN_CONF = __DISPLAY_MIN_CONF__;

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

function speciesMaxConf(sp) {
  const s = confStats(allSongs(sp));
  return s ? s.high : 0;
}
// The species actually shown anywhere in the UI (>= DISPLAY_MIN_CONF).
const displayedSpecies = speciesList.filter(
  sp => speciesMaxConf(sp) >= DISPLAY_MIN_CONF);

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
  let songs = 0; const locs = new Set(); const recordings = new Set();
  for (const sp of displayedSpecies) {
    for (const sess of sessionsOf(sp)) {
      // A "session" is one recording; the same recording shows up under many
      // species, so count DISTINCT recordings, not per-species session objects.
      recordings.add((sess.recording_file || '') + '|' + (sess.location || '') +
                     '|' + (sess.date || ''));
      songs += songsOf(sess).length;
      locs.add(sess.location);
    }
  }
  document.getElementById('stat-species').textContent = displayedSpecies.length;
  document.getElementById('stat-sessions').textContent = recordings.size;
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
  for (const sp of displayedSpecies) {
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
    img.className = 'sketch' + (sp.art ? '' : ' fallback');
    img.src = sp.art || FALLBACK_SKETCH;
    img.alt = sp.common_name;
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

// ---- Landing scene: free-placement scatter (Where's-Waldo style) ----
// Small seeded PRNG so the layout is the same every load/rebuild.
function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
const SCENE_SEED = 1337;
// Work in scene units where the 3:2 canvas is 150 wide x 100 tall, so x and y
// distances are directly comparable.
const SW = 150, SH = 100;

// Approximate half-extents of a bird box in scene units. Cutouts are portrait,
// so height ~1.35x width; using this stops birds from overlapping vertically.
function halfExtents(sizePct) {
  const hw = (sizePct / 100 * SW) / 2;
  return [hw, hw * 1.35];
}

function renderScene() {
  const scene = document.getElementById('scene');
  scene.innerHTML = '';
  document.getElementById('kpi-num').textContent = displayedSpecies.length;
  const rand = mulberry32(SCENE_SEED);
  const placed = [];  // {x, y, hw, hh} in scene units

  for (const sp of displayedSpecies) {
    const size = 9 + rand() * 7;                 // bird width as % of scene width
    const [hw, hh] = halfExtents(size);
    const mx = hw * 0.6, my = hh * 0.6;          // keep mostly in-frame

    // Best-candidate (blue-noise) sampling: try K spots, keep the one whose
    // nearest neighbour is farthest -> even, non-grid, minimal overlap.
    let best = { x: SW / 2, y: SH / 2 }, bestScore = -Infinity;
    for (let k = 0; k < 60; k++) {
      const x = mx + rand() * (SW - 2 * mx);
      const y = my + rand() * (SH - 2 * my);
      let score = Infinity;
      for (const p of placed) {
        // Box clearance: >=1 means the boxes don't overlap on some axis.
        const clear = Math.max(Math.abs(x - p.x) / (hw + p.hw),
                               Math.abs(y - p.y) / (hh + p.hh));
        if (clear < score) score = clear;
      }
      if (score > bestScore) { bestScore = score; best = { x, y }; }
    }
    placed.push({ x: best.x, y: best.y, hw, hh });

    const bird = document.createElement('div');
    bird.className = 'scene-bird';
    bird.style.left = (best.x / SW * 100) + '%';
    bird.style.top = (best.y / SH * 100) + '%';
    bird.style.width = size + '%';
    bird.style.setProperty('--rot', ((rand() * 2 - 1) * 6).toFixed(1) + 'deg');
    bird.style.zIndex = Math.round(best.y);      // lower birds sit in front

    const img = document.createElement('img');
    if (!sp.art) img.className = 'fallback';
    img.src = sp.art || FALLBACK_SKETCH;
    img.alt = sp.common_name;
    img.loading = 'lazy';

    const name = document.createElement('div');
    name.className = 'scene-name';
    name.textContent = sp.common_name;

    bird.appendChild(img);
    bird.appendChild(name);
    bird.addEventListener('click', () => playTopSong(sp, bird));
    scene.appendChild(bird);
  }
}

// ---- View switching (landing <-> explore) ----
let exploreRendered = false;
function showExplore() {
  if (!exploreRendered) { computeStats(); renderGrid(''); exploreRendered = true; }
  document.getElementById('view-landing').hidden = true;
  document.getElementById('view-explore').hidden = false;
  window.scrollTo(0, 0);
}
function showLanding() {
  stopCurrent();
  closeModal();
  document.getElementById('view-explore').hidden = true;
  document.getElementById('view-landing').hidden = false;
  window.scrollTo(0, 0);
}

document.getElementById('close').addEventListener('click', closeModal);
document.getElementById('overlay').addEventListener('click', e => {
  if (e.target.id === 'overlay') closeModal();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
document.getElementById('search').addEventListener('input', e => renderGrid(e.target.value));
document.getElementById('go-explore').addEventListener('click', showExplore);
document.getElementById('go-mural').addEventListener('click', showLanding);

renderScene();
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

    # Attach top-song clips (embedded audio) and watercolor art for the page.
    augmented = attach_top_clips(data)
    attach_art(augmented)

    # Embed the JSON as a JS object literal. json.dumps is valid JS; escape
    # </script> so the payload can't break out of the <script> block.
    embedded = json.dumps(augmented, ensure_ascii=False).replace("</", "<\\/")
    html = (PAGE_TEMPLATE
            .replace("__CATALOG_JSON__", embedded)
            .replace("__DISPLAY_MIN_CONF__", repr(DISPLAY_MIN_CONF)))

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

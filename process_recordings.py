#!/usr/bin/env python3
"""Batch-process new recordings dropped into recordings/.

Workflow:
  1. Drop audio files into recordings/. Name them  <Location...>_<YYYYMMDD>.<ext>
     e.g.  Robbinsville_NJ_20260727.WAV  ->  location "Robbinsville NJ", 2026-07-27
  2. Run this script. For each new file it:
       - parses the location + date from the filename,
       - looks up coordinates in locations.json (optional; improves accuracy),
       - runs BirdNET and merges detections into the catalog,
       - moves the file into recordings/processed/,
     then re-extracts top-song clips and rebuilds bird_catalog.html.
  3. It reports any NEW species that crossed the 50% mural threshold and still
     need artwork. Generating art costs money (OpenAI), so this script never
     does it — run generate_art_openai.py separately for those.

Usage:
    process_recordings.py
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

import catalog_clips as cc
from analyze_recording import (build_analyzer, analyze_file, merge_detections,
                               load_catalog, save_catalog, CATALOG_PATH)

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_EXTS = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aif", ".aiff")
PROCESSED_DIR = os.path.join(cc.RECORDINGS_DIR, "processed")
LOCATIONS_PATH = os.path.join(HERE, "locations.json")
ANALYZE_MIN_CONF = 0.15   # store everything down to here; the page filters to 50%
DISPLAY_MIN_CONF = 0.5    # keep in sync with generate_catalog_html.DISPLAY_MIN_CONF


def load_locations():
    if not os.path.exists(LOCATIONS_PATH):
        return {}
    try:
        with open(LOCATIONS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def parse_filename(path):
    """Return (location, date_str). Location is the filename (minus the date
    token) with underscores as spaces; date is the YYYYMMDD token, or the file's
    modified date if no such token is present."""
    stem = os.path.splitext(os.path.basename(path))[0]
    date_str = None
    loc_parts = []
    for part in stem.split("_"):
        if date_str is None and re.fullmatch(r"\d{8}", part):
            try:
                date_str = dt.datetime.strptime(part, "%Y%m%d").date().isoformat()
                continue
            except ValueError:
                pass
        loc_parts.append(part)
    if date_str is None:
        date_str = dt.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    location = " ".join(loc_parts).strip() or "Unknown"
    return location, date_str


def species_over(catalog, thresh):
    """Set of species whose best song confidence is >= thresh."""
    out = set()
    for name, entry in catalog["species"].items():
        confs = [g.get("confidence") or 0
                 for s in entry.get("sessions", []) for g in s.get("songs", [])]
        if confs and max(confs) >= thresh:
            out.add(name)
    return out


def pending_files():
    files = []
    if not os.path.isdir(cc.RECORDINGS_DIR):
        return files
    for name in sorted(os.listdir(cc.RECORDINGS_DIR)):
        full = os.path.join(cc.RECORDINGS_DIR, name)
        if os.path.isdir(full) or name.startswith("."):
            continue
        if os.path.splitext(name)[1].lower() in AUDIO_EXTS:
            files.append(full)
    return files


def main():
    todo = pending_files()
    if not todo:
        print("No new recordings in recordings/ to process. "
              "(Processed files live in recordings/processed/.)")
        return 0

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    locations = load_locations()
    catalog = load_catalog(CATALOG_PATH)
    before = species_over(catalog, DISPLAY_MIN_CONF)

    print(f"Found {len(todo)} recording(s) to process. Loading BirdNET...")
    analyzer = build_analyzer()

    for path in todo:
        fname = os.path.basename(path)
        location, date_str = parse_filename(path)
        coords = locations.get(location) or {}
        lat, lon = coords.get("lat"), coords.get("lon")
        rec_date = dt.date.fromisoformat(date_str)
        print(f"\n=== {fname} ===")
        print(f"  location={location!r}  date={date_str}  "
              + (f"coords=({lat},{lon})" if lat is not None
                 else "(no coords in locations.json -> global detection)"))
        dets = analyze_file(analyzer, path, ANALYZE_MIN_CONF, lat, lon,
                            rec_date if lat is not None else None)
        added, per = merge_detections(catalog, dets, location, date_str, fname)
        print(f"  {added} new song(s) across {len(per)} species.")
        dest = os.path.join(PROCESSED_DIR, fname)
        shutil.move(path, dest)
        print(f"  moved -> recordings/processed/{fname}")

    save_catalog(CATALOG_PATH, catalog)

    # Refresh top-song clips and the page.
    print("\nExtracting top-song clips...")
    import extract_clips
    extract_clips.main()
    print("Building spectrograms...")
    import build_spectrograms
    build_spectrograms.main([])
    print("Rebuilding bird_catalog.html...")
    subprocess.run([sys.executable, os.path.join(HERE, "generate_catalog_html.py")],
                   check=True)

    # Report species newly crossing the mural threshold that still lack art.
    after = species_over(catalog, DISPLAY_MIN_CONF)
    new_over = sorted(after - before)
    print("\n" + "=" * 60)
    print(f"Mural species now: {len(after)} (was {len(before)}).")
    if new_over:
        print(f"NEW species over {DISPLAY_MIN_CONF:.0%}: {', '.join(new_over)}")
        need_art = [n for n in new_over if cc.custom_art_path(n) is None]
        if need_art:
            print("\nThese need artwork for the mural (paid OpenAI step — run "
                  "separately after approving cost):")
            for n in need_art:
                print(f"  - {n}   ->  custom_art/{cc.species_slug(n)}.png")
            print("\n  ./venv/bin/python generate_art_openai.py --style field-guide "
                  "--transparent --poses")
    else:
        print("No new species crossed the threshold.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

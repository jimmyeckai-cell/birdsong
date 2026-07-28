#!/usr/bin/env python3
"""Detect bird species in an audio recording with BirdNET and add the
results to the persistent catalog (bird_catalog_data.json).

Usage:
    analyze_recording.py <audio_file> --location "Backyard" \
        [--date YYYY-MM-DD] [--min-conf 0.15] [--lat LAT --lon LON]

lat/lon/date are optional. When provided they are passed to BirdNET, which
restricts the candidate species list by location and season. Omit them for
open-ended global detection.

Catalog schema (bird_catalog_data.json):
    {"species": {
        <common_name>: {
            "common_name": str,
            "scientific_name": str,
            "sessions": [                 # one entry per recording
                {"location", "date", "recording_file",
                 "songs": [               # each detection of the bird
                    {"confidence", "start_time_sec", "end_time_sec"}]}
            ]}}}

A "session" is a single recording the species was heard in; each time the
bird is heard within that recording is a "song". Highest and average
confidence are derived from the songs at display time.
"""
import argparse
import datetime as dt
import json
import os
import sys

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "bird_catalog_data.json")


def _migrate_entry(entry):
    """Convert an old-schema species entry (flat "sightings") into the new
    session/song schema. New-schema entries pass through unchanged."""
    if "sessions" in entry:
        entry.setdefault("common_name", entry.get("common_name"))
        return entry
    sessions = {}
    order = []
    for s in entry.get("sightings", []):
        key = (s.get("location"), s.get("date"), s.get("recording_file"))
        if key not in sessions:
            sessions[key] = {
                "location": s.get("location"),
                "date": s.get("date"),
                "recording_file": s.get("recording_file"),
                "songs": [],
            }
            order.append(key)
        sessions[key]["songs"].append({
            "confidence": s.get("confidence"),
            "start_time_sec": s.get("start_time_sec"),
            "end_time_sec": s.get("end_time_sec"),
        })
    entry["sessions"] = [sessions[k] for k in order]
    entry.pop("sightings", None)
    return entry


def load_catalog(path):
    """Load the catalog JSON (migrating old schema), or return a fresh one."""
    if not os.path.exists(path):
        return {"species": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "species" not in data or not isinstance(data["species"], dict):
        return {"species": {}}
    for entry in data["species"].values():
        _migrate_entry(entry)
    return data


def save_catalog(path, data):
    """Write the catalog JSON back to disk (pretty-printed, stable order)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def song_key(song):
    """Identity of a song, used to avoid inserting exact duplicates."""
    return (
        round(float(song.get("start_time_sec") or 0), 3),
        round(float(song.get("end_time_sec") or 0), 3),
        round(float(song.get("confidence") or 0), 4),
    )


def get_or_create_session(entry, location, date_str, recording_file):
    """Return the session for this recording, creating it if needed."""
    for sess in entry["sessions"]:
        if (sess.get("location") == location
                and sess.get("date") == date_str
                and sess.get("recording_file") == recording_file):
            return sess
    sess = {
        "location": location,
        "date": date_str,
        "recording_file": recording_file,
        "songs": [],
    }
    entry["sessions"].append(sess)
    return sess


def build_analyzer():
    """Load the BirdNET analyzer (slow; reuse it across many files)."""
    from birdnetlib.analyzer import Analyzer
    return Analyzer()


def analyze_file(analyzer, audio_file, min_conf, lat=None, lon=None, rec_date=None):
    """Run BirdNET on one file and return its raw detections. lat/lon (with an
    optional date) restrict the species list by location/season when given."""
    from birdnetlib import Recording
    kwargs = {"min_conf": min_conf}
    if lat is not None and lon is not None:
        kwargs["lat"] = lat
        kwargs["lon"] = lon
        if rec_date is not None:
            kwargs["date"] = rec_date
    recording = Recording(analyzer, audio_file, **kwargs)
    recording.analyze()
    return recording.detections


def merge_detections(catalog, detections, location, date_str, recording_file):
    """Merge detections into the catalog as songs under the right session.
    Returns (songs_added, {common_name: [confidences added]})."""
    species_map = catalog["species"]
    songs_added = 0
    per_species_added = {}
    for det in detections:
        common = det.get("common_name")
        scientific = det.get("scientific_name")
        if not common:
            continue
        entry = species_map.setdefault(common, {
            "common_name": common,
            "scientific_name": scientific,
            "sessions": [],
        })
        if not entry.get("scientific_name") and scientific:
            entry["scientific_name"] = scientific
        session = get_or_create_session(entry, location, date_str, recording_file)
        song = {
            "confidence": round(float(det.get("confidence", 0.0)), 4),
            "start_time_sec": det.get("start_time"),
            "end_time_sec": det.get("end_time"),
        }
        if song_key(song) in {song_key(s) for s in session["songs"]}:
            continue
        session["songs"].append(song)
        songs_added += 1
        per_species_added.setdefault(common, []).append(song["confidence"])
    return songs_added, per_species_added


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Detect birds in an audio recording and add to the catalog.")
    p.add_argument("audio_file", help="Path to the audio recording.")
    p.add_argument("--location", required=True,
                   help='Human-readable location label, e.g. "Backyard".')
    p.add_argument("--date", default=None,
                   help="Recording date as YYYY-MM-DD (default: today).")
    p.add_argument("--min-conf", type=float, default=0.15,
                   help="Minimum detection confidence (default: 0.15).")
    p.add_argument("--lat", type=float, default=None,
                   help="Latitude (optional; restricts species by location).")
    p.add_argument("--lon", type=float, default=None,
                   help="Longitude (optional; restricts species by location).")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if not os.path.exists(args.audio_file):
        sys.exit(f"Error: audio file not found: {args.audio_file}")

    if args.date:
        try:
            rec_date = dt.date.fromisoformat(args.date)
        except ValueError:
            sys.exit(f"Error: --date must be YYYY-MM-DD, got: {args.date}")
    else:
        rec_date = dt.date.today()
    date_str = rec_date.isoformat()

    if (args.lat is None) != (args.lon is None):
        sys.exit("Error: --lat and --lon must be provided together.")

    print("Loading BirdNET analyzer...")
    analyzer = build_analyzer()

    if args.lat is not None and args.lon is not None:
        print(f"Restricting species to lat={args.lat}, lon={args.lon}, "
              f"date={date_str}")
    else:
        print("Open-ended global detection (no lat/lon/date filter).")

    print(f"Analyzing {args.audio_file} (min confidence "
          f"{args.min_conf:.2f})...")
    detections = analyze_file(analyzer, args.audio_file, args.min_conf,
                              args.lat, args.lon, rec_date)
    recording_file = os.path.basename(args.audio_file)

    catalog = load_catalog(CATALOG_PATH)
    species_map = catalog["species"]
    songs_added, per_species_added = merge_detections(
        catalog, detections, args.location, date_str, recording_file)

    save_catalog(CATALOG_PATH, catalog)

    # Plain-English summary.
    print()
    if not detections:
        print(f"No birds detected in {recording_file} at or above "
              f"confidence {args.min_conf:.2f}.")
    else:
        n_species = len(per_species_added)
        print(f"Recorded a session at {args.location} on {date_str} "
              f"({recording_file}): {songs_added} song(s) across {n_species} "
              f"species.")
        # Sort species by highest confidence in this session.
        ranked = sorted(per_species_added.items(),
                        key=lambda kv: -max(kv[1]))
        for common, confs in ranked:
            sci = species_map[common].get("scientific_name") or "?"
            high = max(confs) * 100
            avg = (sum(confs) / len(confs)) * 100
            print(f"  - {common} ({sci}): {len(confs)} song(s), "
                  f"highest {high:.0f}%, avg {avg:.0f}%")
    print()
    n_sessions = sum(len(e["sessions"]) for e in species_map.values())
    print(f"Added {songs_added} new song(s). Catalog now holds "
          f"{len(species_map)} species across {n_sessions} session(s). "
          f"Saved to {CATALOG_PATH}.")


if __name__ == "__main__":
    main()

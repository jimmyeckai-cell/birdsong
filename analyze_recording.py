#!/usr/bin/env python3
"""Detect bird species in an audio recording with BirdNET and add the
results to the persistent catalog (bird_catalog_data.json).

Usage:
    analyze_recording.py <audio_file> --location "Backyard" \
        [--date YYYY-MM-DD] [--min-conf 0.15] [--lat LAT --lon LON]

lat/lon/date are optional. When provided they are passed to BirdNET, which
restricts the candidate species list by location and season. Omit them for
open-ended global detection.
"""
import argparse
import datetime as dt
import json
import os
import sys

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "bird_catalog_data.json")


def load_catalog(path):
    """Load the catalog JSON, or return a fresh empty structure."""
    if not os.path.exists(path):
        return {"species": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "species" not in data or not isinstance(data["species"], dict):
        data = {"species": {}}
    return data


def save_catalog(path, data):
    """Write the catalog JSON back to disk (pretty-printed, stable order)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def sighting_key(s):
    """Identity of a sighting used to avoid inserting exact duplicates."""
    return (
        s.get("location"),
        s.get("date"),
        s.get("recording_file"),
        round(float(s.get("start_time_sec") or 0), 3),
        round(float(s.get("end_time_sec") or 0), 3),
    )


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

    # Determine the recording date.
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

    # Import here so --help works even before heavy deps are installed.
    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer

    print(f"Loading BirdNET analyzer...")
    analyzer = Analyzer()

    # Only pass lat/lon/date to BirdNET when the user supplied coordinates,
    # since these restrict the candidate species list by location/season.
    rec_kwargs = {"min_conf": args.min_conf}
    if args.lat is not None and args.lon is not None:
        rec_kwargs["lat"] = args.lat
        rec_kwargs["lon"] = args.lon
        rec_kwargs["date"] = rec_date
        print(f"Restricting species to lat={args.lat}, lon={args.lon}, "
              f"date={date_str}")
    else:
        print("Open-ended global detection (no lat/lon/date filter).")

    print(f"Analyzing {args.audio_file} (min confidence "
          f"{args.min_conf:.2f})...")
    recording = Recording(analyzer, args.audio_file, **rec_kwargs)
    recording.analyze()

    detections = recording.detections
    recording_file = os.path.basename(args.audio_file)

    catalog = load_catalog(CATALOG_PATH)
    species_map = catalog["species"]

    added = 0
    per_species_added = {}
    for det in detections:
        common = det.get("common_name")
        scientific = det.get("scientific_name")
        if not common:
            continue
        entry = species_map.setdefault(common, {
            "common_name": common,
            "scientific_name": scientific,
            "sightings": [],
        })
        # Keep the scientific name up to date if it was missing before.
        if not entry.get("scientific_name") and scientific:
            entry["scientific_name"] = scientific

        sighting = {
            "location": args.location,
            "date": date_str,
            "confidence": round(float(det.get("confidence", 0.0)), 4),
            "recording_file": recording_file,
            "start_time_sec": det.get("start_time"),
            "end_time_sec": det.get("end_time"),
        }

        existing_keys = {sighting_key(s) for s in entry["sightings"]}
        if sighting_key(sighting) in existing_keys:
            continue
        entry["sightings"].append(sighting)
        added += 1
        per_species_added[common] = per_species_added.get(common, 0) + 1

    save_catalog(CATALOG_PATH, catalog)

    # Plain-English summary.
    print()
    if not detections:
        print(f"No birds detected in {recording_file} at or above "
              f"confidence {args.min_conf:.2f}.")
    else:
        n_species = len(per_species_added)
        print(f"Detected {len(detections)} call(s) across {n_species} "
              f"species in {recording_file} at {args.location} on {date_str}:")
        # Report best confidence per newly-added species.
        best = {}
        for det in detections:
            c = det.get("common_name")
            if c in per_species_added:
                best[c] = max(best.get(c, 0.0), float(det.get("confidence", 0)))
        for common in sorted(best, key=lambda k: -best[k]):
            sci = species_map[common].get("scientific_name") or "?"
            print(f"  - {common} ({sci}): {per_species_added[common]} "
                  f"detection(s), best confidence {best[common] * 100:.0f}%")
    print()
    print(f"Added {added} new sighting(s). Catalog now holds "
          f"{len(species_map)} species. Saved to {CATALOG_PATH}.")


if __name__ == "__main__":
    main()

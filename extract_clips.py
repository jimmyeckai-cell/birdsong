#!/usr/bin/env python3
"""Extract audio for the top songs of each species into clips/*.ogg.

Reads bird_catalog_data.json, picks each species' top-N highest-confidence
songs (see catalog_clips.TOP_N), and cuts the matching audio window out of the
source recording in recordings/. Clips are written as small OGG/Vorbis files
that are committed to git, so they sync to other machines even though the large
source WAVs are not.

Already-extracted clips are skipped (cached). Songs whose source recording is
not present locally are skipped with a note (their audio simply won't appear in
the catalog until the recording is available on some machine that runs this).

Usage:
    extract_clips.py
"""
import os
import sys

import catalog_clips as cc
from analyze_recording import load_catalog, CATALOG_PATH


def find_recording(recording_file):
    """Locate a recording by basename inside recordings/ (case-insensitive)."""
    if not recording_file:
        return None
    direct = os.path.join(cc.RECORDINGS_DIR, recording_file)
    if os.path.exists(direct):
        return direct
    if os.path.isdir(cc.RECORDINGS_DIR):
        want = recording_file.lower()
        for name in os.listdir(cc.RECORDINGS_DIR):
            if name.lower() == want:
                return os.path.join(cc.RECORDINGS_DIR, name)
    return None


def main():
    import soundfile as sf

    catalog = load_catalog(CATALOG_PATH)
    os.makedirs(cc.CLIPS_DIR, exist_ok=True)

    # Collect the unique clips we need (a clip may be top for several species).
    needed = {}  # clip_id -> (recording_file, start, end)
    for entry in catalog["species"].values():
        for song in cc.top_songs(entry):
            start = song.get("start_time_sec")
            end = song.get("end_time_sec")
            if start is None or end is None:
                continue
            cid = cc.clip_id(song["recording_file"], start, end)
            needed[cid] = (song["recording_file"], start, end)

    made = cached = missing = 0
    missing_files = set()
    # Cache SoundFile info per recording so we open each file once for metadata.
    info_cache = {}

    for cid, (rec_file, start, end) in sorted(needed.items()):
        out_path = cc.clip_path(cid)
        if os.path.exists(out_path):
            cached += 1
            continue
        src = find_recording(rec_file)
        if not src:
            missing += 1
            missing_files.add(rec_file)
            continue
        if src not in info_cache:
            info_cache[src] = sf.info(src)
        info = info_cache[src]
        sr = info.samplerate
        start_frame = max(0, int((start - cc.PAD_SEC) * sr))
        stop_frame = min(info.frames, int((end + cc.PAD_SEC) * sr))
        data, _ = sf.read(src, start=start_frame, stop=stop_frame, dtype="float32")
        if getattr(data, "ndim", 1) > 1:  # mix stereo -> mono
            data = data.mean(axis=1)
        sf.write(out_path, data, sr, format="OGG", subtype="VORBIS")
        made += 1

    print(f"Clips: {made} extracted, {cached} already cached, "
          f"{missing} unavailable (source recording not on this machine).")
    if missing_files:
        print("  Missing recordings (run extract on a machine that has them):")
        for f in sorted(missing_files):
            print(f"    - {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

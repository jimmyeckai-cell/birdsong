#!/usr/bin/env python3
"""Shared helpers for the top-song audio clips feature.

For each species we keep audio for its N highest-confidence songs. Clips are
extracted from the source recordings into clips/*.ogg (small, committed so they
sync across machines), then embedded into the HTML as base64 audio players.

extract_clips.py (needs the source WAV) and generate_catalog_html.py (needs
only the cached clips/) both import this module so they agree on *which* songs
are "top" and *how* the clip files are named.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(HERE, "clips")
ART_DIR = os.path.join(HERE, "watercolors")
RECORDINGS_DIR = os.path.join(HERE, "recordings")

TOP_N = 3          # number of top songs to keep audio for, per species
PAD_SEC = 0.5      # extra context padding on each side of the detection window


def species_slug(common_name):
    """Filesystem-safe slug for a species (used for artwork filenames)."""
    return "".join(c if (c.isalnum() or c in "-_") else "_"
                   for c in (common_name or "unknown"))


def art_path(common_name):
    """Path to the auto-generated watercolor (watercolors/<slug>.jpg)."""
    return os.path.join(ART_DIR, species_slug(common_name) + ".jpg")


# Hand-made artwork (e.g. generated in ChatGPT) goes here and takes precedence
# over the auto watercolor. Any of these extensions is accepted.
CUSTOM_ART_DIR = os.path.join(HERE, "custom_art")
ART_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Mel-spectrogram images of top songs, keyed by clip id (same id as clips/).
SPECTRO_DIR = os.path.join(HERE, "spectrograms")


def spectrogram_path(cid):
    return os.path.join(SPECTRO_DIR, cid + ".webp")


def custom_art_path(common_name):
    """Return the hand-made image for a species in custom_art/, or None."""
    slug = species_slug(common_name)
    for ext in ART_EXTS:
        p = os.path.join(CUSTOM_ART_DIR, slug + ext)
        if os.path.exists(p):
            return p
    return None


def resolve_art_path(common_name):
    """Best available artwork: a custom image if present, else the auto
    watercolor, else None."""
    custom = custom_art_path(common_name)
    if custom:
        return custom
    auto = art_path(common_name)
    return auto if os.path.exists(auto) else None


def top_songs(entry, n=TOP_N):
    """Return a species entry's N highest-confidence songs, flattened across
    sessions and annotated with the session's recording_file/location/date."""
    songs = []
    for sess in entry.get("sessions", []):
        for g in sess.get("songs", []):
            songs.append({
                "confidence": g.get("confidence") or 0.0,
                "start_time_sec": g.get("start_time_sec"),
                "end_time_sec": g.get("end_time_sec"),
                "recording_file": sess.get("recording_file"),
                "location": sess.get("location"),
                "date": sess.get("date"),
            })
    songs.sort(key=lambda s: -(s.get("confidence") or 0.0))
    return songs[:n]


def clip_id(recording_file, start, end):
    """Stable, filesystem-safe identifier for a clip (recording + time window).
    Deterministic so extract and generate produce/consume the same name."""
    stem = os.path.splitext(os.path.basename(recording_file or "unknown"))[0]
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem)
    return f"{safe}__{float(start or 0):.1f}-{float(end or 0):.1f}"


def clip_filename(cid):
    return cid + ".ogg"


def clip_path(cid):
    return os.path.join(CLIPS_DIR, clip_filename(cid))

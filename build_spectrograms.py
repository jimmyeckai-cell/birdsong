#!/usr/bin/env python3
"""Render a mel-spectrogram image for each species' #1 top-song clip.

Reads clips/ (committed), writes spectrograms/<clip_id>.webp (committed), which
the Details modal embeds. Cached: existing spectrograms are skipped. Works on
any machine that has the clips, without the raw recordings.

Usage:
    build_spectrograms.py [--force]
"""
import argparse
import io
import os
import sys

import catalog_clips as cc
from analyze_recording import load_catalog, CATALOG_PATH


def render_spectrogram(clip_path):
    """Return WebP bytes of a magma mel-spectrogram for an audio clip."""
    import numpy as np
    import librosa
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    y, sr = librosa.load(clip_path, sr=32000, mono=True)
    S = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=1024, hop_length=256,
                                       n_mels=128, fmin=500, fmax=12000)
    s_db = librosa.power_to_db(S, ref=np.max)

    fig, ax = plt.subplots(figsize=(4.2, 1.5), dpi=110)
    ax.imshow(s_db, origin="lower", aspect="auto", cmap="magma", vmin=-60, vmax=0)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#000", pad_inches=0)
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf).convert("RGB")
    if img.width > 460:
        img = img.resize((460, max(1, round(img.height * 460 / img.width))))
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=80, method=6)
    return out.getvalue()


def main(argv=None):
    p = argparse.ArgumentParser(description="Render top-song spectrograms.")
    p.add_argument("--force", action="store_true", help="Rebuild even if cached.")
    args = p.parse_args(argv)

    catalog = load_catalog(CATALOG_PATH)
    os.makedirs(cc.SPECTRO_DIR, exist_ok=True)

    made = cached = missing = 0
    for entry in catalog["species"].values():
        tops = cc.top_songs(entry)
        if not tops:
            continue
        top = tops[0]
        start, end = top.get("start_time_sec"), top.get("end_time_sec")
        if start is None or end is None:
            continue
        cid = cc.clip_id(top["recording_file"], start, end)
        out_path = cc.spectrogram_path(cid)
        if os.path.exists(out_path) and not args.force:
            cached += 1
            continue
        clip = cc.clip_path(cid)
        if not os.path.exists(clip):
            missing += 1
            continue
        with open(out_path, "wb") as f:
            f.write(render_spectrogram(clip))
        made += 1

    print(f"Spectrograms: {made} created, {cached} cached, {missing} "
          f"missing clip.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Bird Song Catalog

A local, offline bird-identification pipeline for field audio recordings.
Point it at a recording, it detects which bird species are calling using the
[BirdNET](https://birdnet.cornell.edu/) acoustic model (via
[`birdnetlib`](https://github.com/joeweiss/birdnetlib)), and accumulates the
results into a persistent catalog that renders as a self-contained HTML page.

Everything runs locally — no API key, no model download, no internet required
for detection (Wikipedia photos/facts are fetched in the browser when you open
a species card).

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

See `requirements.txt` for the numpy / tflite-runtime vs. tensorflow notes if
you're setting up on a different platform.

Audio formats: **WAV / FLAC / OGG work out of the box.** MP3 / M4A require
`ffmpeg` on your PATH (`brew install ffmpeg` on macOS).

## Usage

**1. Analyze a recording** (adds detections to `bird_catalog_data.json`):

```bash
./venv/bin/python analyze_recording.py recordings/myclip.wav --location "Backyard"
```

Options:

| Flag | Meaning |
|------|---------|
| `--location "Backyard"` | **Required.** Human-readable location label. |
| `--date 2026-07-27` | Recording date (default: today). |
| `--min-conf 0.15` | Minimum detection confidence (default 0.15). |
| `--lat 47.6 --lon -122.3` | Optional. Restricts candidate species by location/season. Omit for open-ended global detection. Must be given together; when used, `--date` is also passed to BirdNET. |

**2. Rebuild the catalog page:**

```bash
./venv/bin/python generate_catalog_html.py
```

Open `bird_catalog.html` in any browser (it's fully self-contained — the
catalog data is embedded, so it works opened directly or hosted anywhere).

## Files

- `analyze_recording.py` — CLI that runs BirdNET and merges detections into the catalog JSON.
- `generate_catalog_html.py` — renders `bird_catalog_data.json` → `bird_catalog.html`.
- `bird_catalog_data.json` — the persistent catalog (committed, syncs across machines).
- `bird_catalog.html` — the generated page (committed).
- `recordings/` — put your raw audio here. **Not committed** — field-recorder
  WAVs are too large for git (~800 MB each; GitHub caps at 100 MB), so audio
  stays local per machine. The catalog records each recording's filename, so
  provenance still syncs. If you want the audio on another machine, copy it via
  cloud storage or an external drive.

## Custom bird artwork (e.g. from ChatGPT)

The mural uses an auto-generated watercolor for each bird by default, but you can
override any bird with your own image (such as a ChatGPT-generated watercolor):

1. Run `./venv/bin/python art_status.py` to see the exact filename for each
   species (and which still use the auto watercolor).
2. Generate the image using the prompt in `ART_STYLE_PROMPT.md` (attach a
   reference photo for accuracy).
3. Save it in `custom_art/` with that filename, e.g.
   `custom_art/American_Robin.png` (PNG/JPG/JPEG/WEBP all accepted).
4. Rebuild: `./venv/bin/python generate_catalog_html.py` (or `./save.sh`).

Custom images take precedence over the auto watercolors and are downscaled to
~560px JPEG on embed, so the page stays small no matter how large the source is.
`custom_art/` is committed, so your artwork syncs across machines.

## Syncing across two (or more) machines

The catalog data and generated page are committed to git, so GitHub is the
single source of truth for your results. (Raw audio is not synced — see the
`recordings/` note above.) To avoid conflicts when switching between
computers, follow one rule: **pull before you start, save when you finish.**

Two helper scripts make this foolproof:

```bash
./sync.sh              # when you SIT DOWN: pulls the latest catalog
# ... analyze recordings ...
./save.sh "note"       # when you're DONE: rebuilds HTML, commits, pushes
```

- `sync.sh` runs `git pull --rebase`.
- `save.sh` regenerates `bird_catalog.html` from the JSON, stages everything
  (catalog, page, new recordings, code), commits, rebases on the remote, and
  pushes. The commit message argument is optional.

Because `bird_catalog.html` is fully generated, you never merge it by hand — if
it ever conflicts, just re-run `generate_catalog_html.py` (or `save.sh`).

### First-time auth on each machine (recommended: SSH)

Set up an SSH key once per computer so you're never prompted for credentials:

```bash
ssh-keygen -t ed25519 -C "your-email"      # press enter through the prompts
cat ~/.ssh/id_ed25519.pub                   # add this to github.com/settings/keys
```

Then clone with the SSH URL (`git@github.com:USER/REPO.git`).

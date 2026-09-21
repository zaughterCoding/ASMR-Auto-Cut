# ASMR Auto Cut

**English** · [中文](README.zh-CN.md)

> Pull the parts worth keeping out of long ASMR recordings, and cut the chatter and the
> silence. A desktop app that runs entirely on your machine — nothing is ever uploaded.

A single ASMR stream can run for hours, and only some of it is worth keeping. Trimming that
by hand on a timeline takes a long time. This tool labels every part of the recording as
speech, silence, or ASMR, draws the result on the original waveform, lets you walk the
timeline and fix what it got wrong, then exports the keepers as one file.

It is deliberately **assistive, not automatic**. Whispered and lightly-touching ASMR is easy
to mistake for speech, so a review pass is part of the workflow rather than an optional extra.
![window](asserts/window.jpg)

## Features

- **Local only.** No account, no network, no telemetry. Your recordings never leave the machine.
- **Two-level timeline.** An overview lane zoomed to the whole recording, and a detail lane
  zoomed into a selection. Both zoom independently; scrubbing one moves the other.
- **Segment-level review.** Click a block to play from its start, retag it from preset
  buttons, and see the effect immediately. Cut segments render faded.
- **Review depth you choose.** Quick / Standard / Thorough controls how wide a band of
  uncertainty gets surfaced for a human to listen to.
- **Progress you can read.** Analysis and export report the current stage and percentage
  instead of freezing the window.
- **Video passes through untouched.** Export stream-copies the video track, so exporting is
  bound by disk speed, not by re-encoding.
- **Command line included.** The backend is a standalone CLI. Batch it, script it, or use it
  without the GUI at all.
![overview](asserts/overview.gif)

## Install

### Windows installer

Download the `.msi` or the `-setup.exe` from Releases and run it. Everything is bundled —
**no Python, no ffmpeg, and no network access required.**

- **The first launch asks where to keep project data.** Intermediate files and exports go
  there, so the app does not decide for you. The choice is remembered in
  `%APPDATA%\com.asmrautocut.desktop\config.json`.
- Set `ASMR_AUTO_CUT_DATA` to override that with a fixed path — handy for scripting.

The installed backend can also be driven directly:

```powershell
& "$env:LOCALAPPDATA\ASMR Auto Cut\backend\asmr-auto-cut.exe" analyze input.mp4 --project-dir E:\data\example
```

Build sizes and what lands on disk are recorded in [Build](#build) below.

### From source

Requires Python 3.11+, Node.js 18+, and a Rust toolchain. `ffmpeg` and `ffprobe` must be on
`PATH` — analysis and export both shell out to them.

```powershell
git clone https://github.com/zaughterCoding/ASMR-Auto-Cut.git
cd ASMR-Auto-Cut

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
# Speech detection (Silero VAD on ONNX Runtime). Weights ship with the package.
.\.venv\Scripts\python.exe -m pip install -e ".\backend[ml]"

cd app
npm install
npm run tauri dev
```

Outside a dev build the shell looks for the backend on `PATH`. During development the
backend usually only exists inside the virtualenv, so point at it:

```powershell
$env:ASMR_AUTO_CUT_BIN = "<repo>\.venv\Scripts\asmr-auto-cut.exe"
npm run tauri dev
```

## Usage

```text
Import → Analyze → Review and fix on the waveform → Save → Export
```

1. **Import** a recording or a video.
2. **Analyze.** Audio is extracted, speech and silence detection run, and the recording is
   split into segments. Each gets a label (`asmr` / `talk` / `inactive` / `uncertain`) and a
   disposition (`keep` / `cut`).
3. **Review.** Drag on the overview lane to pick a range; the detail lane zooms to it. Click
   a block to hear it, then retag it from the preset buttons on the right.
4. **Save** writes your edits back to `segments.json`.
5. **Export** concatenates every segment marked `keep`, in order, into one new file.

### Timeline controls

| Action | Overview lane | Detail lane |
|---|---|---|
| Plain drag | Select a range | — |
| Drag the selection box | Move the selection | — |
| `Ctrl` + wheel | Zoom the view | Zoom the selection |
| `Shift` + drag | Pan the view | — |
| Click a segment block | Select it | Select it |
| Drag the triangle at the top | — | Set the playback start |

### Command line

```powershell
# Analyze; results land in the project directory
asmr-auto-cut analyze input.mp4 --project-dir data/projects/example

# Export the timeline
asmr-auto-cut export data/projects/example/segments.json --output clean.mp4

# Machine-readable progress: one JSON object per line on stdout
asmr-auto-cut analyze input.mp4 --project-dir data/projects/example --progress-json
```

With `--progress-json`, stdout carries one JSON object per line — `{"type":"progress",...}`
records while work is running, and a final `{"type":"result",...}`. Human-readable progress
goes to stderr, so the two never interleave.

`--review quick|standard|thorough` sets how much uncertainty gets flagged for review.
`--mode quality|fast` on `export` trades the crossfade for a little speed; the difference is
about 5%, so `quality` is the right default.

A project directory holds:

```text
project.json     source metadata + the timeline as analyzed
segments.json    the timeline as edited; both the GUI and export read this
waveform.json    waveform samples, 20 per second, for drawing
```

The extracted `analysis.wav` is an intermediate (roughly 0.9 GB for an 8-hour recording) and
is deleted once analysis succeeds. It is kept on failure, to make the failure diagnosable.

## Supported formats

**Input** — anything ffmpeg can decode: `.mp4` `.mkv` `.flv` `.ts` `.mov` `.mp3` `.m4a`
`.flac` `.wav` `.aac` `.ogg`, and more.

**In-app playback** uses the system WebView2 (Chromium), whose container support is narrower
than ffmpeg's. This affects *listening while you review* only — analysis and export are
unaffected, and a file you cannot preview can still be cut and exported.

| Extension | Preview |
|---|---|
| `.mp3` `.wav` `.flac` `.m4a` `.aac` `.ogg` / opus | ✅ |
| `.mp4` `.mov` `.mkv` | ✅ (audio track only) |
| `.flv` `.ts` | ❌ `SRC_NOT_SUPPORTED` |

Preview support depends on the installed WebView2 version and may differ across machines. If
a file will not play, transcode it first — the rest of the workflow is unchanged:

```powershell
ffmpeg -i input.flv -vn -c:a aac output.m4a
```

## How it works

```
source ──ffmpeg──▶ 16 kHz mono analysis audio ──┬──▶ waveform samples (20/s)
                                                │
                                                ├──▶ Silero VAD (ONNX) ─┐
                                                │                       ├──▶ merge & refine
                                                └──▶ silence detection ─┘        │
                                                                                 ▼
                                                              segments: label + keep/cut
                                                                                 │
                                                          human review ◀─────────┘
                                                                 │
                                                                 ▼
                                        export: -c:v copy + AAC re-encode with 30 ms fades
```

Speech and silence are two independent detectors. Their intervals get merged, split at
detected boundaries, and refined before becoming segments, so that a boundary lands where the
audio actually changes rather than on a fixed grid.

Export re-encodes audio to AAC 192k — each kept segment gets a 30 ms fade at both ends,
because a hard splice between unrelated waveforms clicks. That fade is the only reason audio
is re-encoded at all; the video track is stream-copied.

Output container choice depends on whether the source has a video track, since a stream-copied
video track has to fit in the container:

| Extension | Video source | Audio-only source |
|---|---|---|
| `.mp4` `.mkv` `.mov` | ✅ | ✅ |
| `.m4a` | ❌ | ✅ |
| `.aac` | ⚠️ video track silently dropped | ✅ |
| `.mp3` `.flac` | ❌ | ❌ |
| `.wav` | ⚠️ non-standard AAC-in-WAV | same |

**Use `.mp4` for video and `.m4a` for audio-only.** Picking wrong never damages the source —
just export again.

## Limitations

- **Windows only so far.** Tauri is cross-platform and nothing here is Windows-specific by
  design, but no other platform has been tested.
- **It will misjudge things.** Whispered and lightly-touching ASMR gets labelled as speech
  sometimes. That is what the review pass is for.
- **`waveform.json` is large.** 20 samples per second, roughly 50–70 bytes each; an 8-hour
  recording is around 30–40 MB. The UI reads the whole file into memory, so very long
  recordings get slower to open.
- **Review is manual.** There is no "auto-fix" for the segments you correct; your edits live
  in `segments.json` and the next analysis starts over.

## Build

```powershell
cd app
npm run bundle          # = freeze:backend + tauri build
```

`freeze:backend` runs PyInstaller to produce a self-contained backend in
`src-tauri/resources/backend/`; `tauri build` then packs that and ffmpeg into the installers
declared by `bundle.resources` in `tauri.conf.json`.

One-time prerequisites:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"   # brings in PyInstaller
powershell -File app\scripts\vendor-ffmpeg.ps1                  # pinned LGPL ffmpeg build
```

Measured on Windows:

| Artifact | Size |
|---|---|
| `target/release/asmr-auto-cut.exe` (shell) | 8.8 MB |
| `src-tauri/resources/backend/` (frozen backend) | 98.6 MB |
| `src-tauri/resources/ffmpeg/` (LGPL build) | 147.6 MB |
| `ASMR Auto Cut_0.4.0_x64_en-US.msi` | **108.0 MB** |
| `ASMR Auto Cut_0.4.0_x64-setup.exe` | **81.4 MB** |

Installed footprint: **254.8 MiB** across 138 files. Most of it is not negotiable —
`onnxruntime` alone is 35.8 MB, numpy's BLAS 20.2 MB, and the CPython runtime about 18 MB.
The NSIS installer is 26.6 MB smaller than the MSI purely because of compression; the payload
is byte-for-byte identical.

## Development

```powershell
# Backend
cd backend
..\.venv\Scripts\python.exe -m pytest -v

# Frontend
cd app
npm test          # vitest
npm run build     # tsc + vite
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup, the repository layout, and a few traps worth knowing about before you
change the pipeline or the export path.

## License

[MIT](LICENSE).

The installers bundle third-party components under their own licenses:

| Component | License | Notes |
|---|---|---|
| FFmpeg (`ffmpeg.exe` / `ffprobe.exe` + DLLs) | **LGPLv3** | [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) `win64-lgpl-shared`; full text at `ffmpeg\LICENSE.txt` in the install directory |
| Silero VAD (`silero_vad.onnx`) | MIT | model weights |
| ONNX Runtime | MIT | inference runtime for speech detection |
| CPython and dependencies | PSF / MIT / BSD | frozen by PyInstaller |

FFmpeg is the **LGPL** build rather than the GPL one on purpose. The project only uses
`-c:v copy`, `-c:a aac`, `afade`, and `concat` — all inside LGPL coverage, with no GPL
encoder involved. LGPLv3 requires shipping the license text and a source offer with the
binaries; those are `ffmpeg\LICENSE.txt` and the BtbN repository linked above.

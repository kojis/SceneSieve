# SceneSieve

Local video review and filtering: find visual content and spoken words, review timestamped ranges, preview cuts and audio treatments, and export filtered media or compatible player sidecars.

## Release status

- **Windows v3.24:** standalone bootstrap executable. Downloads its runtime and dependencies on first launch; models download when selected for scanning.
- **macOS/Linux v3.20 preview:** executable shell installers, not compiled standalone binaries. macOS uses a separate preview window. Linux installer targets Ubuntu/Debian with X11/XWayland. Native desktop playback, GPU inference and platform speech backends have not been verified end to end.

Source on the main branch includes the cross-platform preview changes. The Windows v3.24 release retains the Original/Filtered selection across editing and segment previews, with matching visual and audio treatments; its matching source is included in the v3.24 source archive.

## Features

- Local Ollama vision scanning, speech transcription and subtitle matching.
- Dockable editor, waveform/gain timeline, range marking and Original/Filtered playback.
- Skip (default), Pixelate, Blur, More blur and Freeze frame for visual findings.
- Mute, bleep, system-voice replacement and noise distortion, with filtered subtitles.
- Filtered media exports and player-compatible scene files, including Kodi.
- Guided setup, review prompts and per-operation progress.

Detections can miss content or flag harmless scenes. Review results before relying on them. Player sidecar formats cannot represent every visual/audio edit; the export UI explains limitations.

## Build packages

Python 3.10–3.13 is needed for the development environment; Python 3.12 is recommended.

```sh
python -m venv .venv
# Activate the environment for your shell, then:
python -m pip install -r requirements.txt
python -m unittest discover -s src -p 'test_*.py'
```

Create the macOS/Linux self-extracting installers with:

```sh
python packaging/build_unix.py
```

On Windows with .NET Framework 4.x installed:

```powershell
python packaging/build_windows.py
```

Packages are written to `dist/`. The Windows source build is labeled v3.24 because it uses the cross-platform source. The Windows bootstrap pins downloaded runtime assets in `src/runtime-manifest.json`. Unix installers use Homebrew/apt plus pinned top-level Python packages; their transitive dependencies are resolved at installation time.

For development, install mpv, FFmpeg/ffprobe and Ollama first. On Linux also install eSpeak NG and Qt desktop libraries. Start with `python src/desktop_entry.py`. Windows dependencies must be provisioned by the Windows installer first, with `SCENESIEVE_HOME` set to its runtime folder if needed.

## Data and privacy

Processing is local. Dependency/model downloads and optional subtitle searches require network access. Application settings, model caches and user media are not included in this repository.

- Windows: `%LOCALAPPDATA%/SceneSieve`
- macOS: `~/Library/Application Support/SceneSieve`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/SceneSieve`

Override the storage root with `SCENESIEVE_HOME`.

See [Windows guide](docs/Windows-guide.txt) and [macOS/Linux preview notes](docs/macOS-Linux-preview.txt). Third-party components retain their own licenses. No distribution license for the application source has been selected yet.

# Manim Media Studio

A Windows desktop studio for placing frame-accurate Manim animations over images and videos.

## Features

- Imports common image and video formats.
- Reads width, height, duration, frame count, codecs, audio and exact fractional FPS with FFprobe.
- Previews and scrubs video frame by frame.
- Stores projects as readable JSON files.
- Renders a transparent Manim overlay at the source resolution and frame rate.
- Composites the overlay over the original media while preserving audio.
- Tracks a selected rectangle with OpenCV CSRT and exports coordinates for Manim.
- Includes a Windows 10/11 x64 offline Setup EXE builder with download validation.

## Run from source

Install Python 3.11 x64, FFmpeg, Manim's native dependencies and a LaTeX distribution. Then:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m manim_media_studio
```

## Build the Windows offline installer

On a connected Windows 10/11 x64 build machine, install MiKTeX with the packages you need, then run:

```text
BUILD-OFFLINE-INSTALLER.bat
```

The script creates `dist-installer\ManimMediaStudio-Setup-1.0.0.exe`. That Setup EXE installs without internet access. The build script refuses corrupt or HTML downloads, retries alternate sources, verifies PE headers, and supports `ISCC.exe` already installed on the build machine.

If a build reached step 5 or 6 and stopped, extract the latest source package over a fresh folder and copy your existing `dist` folder into it. Run `RETRY-INSTALLER-ONLY.bat` to reuse the already-built application and finish only the installer stage.

See [docs/BUILDING.md](docs/BUILDING.md) for details.

### Build through GitHub

Open **Actions → Build Windows Offline Installer → Run workflow**. The Windows runner installs the required build tools, bundles the application and MiKTeX packages, validates the Setup EXE, and uploads `ManimMediaStudio-Windows-Offline-Setup` as a downloadable artifact. Pushing a `v*` tag also attaches the Setup EXE to the matching GitHub Release.

## Tracking data

Tracking is written as JSON with source-pixel `x`, `y`, `width`, `height`, and `center`. Use `studio_tracking.py` generated beside a project to convert those points to Manim coordinates. Tracking should be restarted after hard cuts, full occlusion, or severe motion blur.

## License

MIT. Third-party components remain under their own licenses; see `THIRD_PARTY_NOTICES.md`.

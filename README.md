# Manim Media Studio

A Windows desktop studio for running ChatGPT-generated Manim animation code with automatic asset selection.

## Features

- Accepts Manim code copied directly from ChatGPT.
- Removes Markdown code fences and accidental standalone backticks before validation.
- Detects the Scene class automatically when the field is blank.
- Detects missing image, video, audio and data-file references and asks for each path.
- Runs code without any file prompt when the animation has no external assets.
- Provides exactly three primary actions: Render, Download Video and Reset.
- Renders a high-quality MP4 and keeps it ready until the user downloads it.
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

Every push to `main` builds the installer automatically. You can also open **Actions → Build Windows Offline Installer → Run workflow**. The Windows runner installs the required build tools, bundles the application and MiKTeX packages, validates the Setup EXE, and uploads `ManimMediaStudio-Windows-Offline-Setup` as a downloadable artifact. Pushing a `v*` tag also attaches the Setup EXE to the matching GitHub Release.

## ChatGPT code workflow

Ask ChatGPT for a complete Manim scene, paste the code into the editor, and click **Render**. When the code contains a reference such as `ImageMobject("earth.png")`, Manim Studio asks you to select that file and substitutes its real Windows path only in the temporary render copy. After a successful render, click **Download Video** to choose where the MP4 is saved.

## License

MIT. Third-party components remain under their own licenses; see `THIRD_PARTY_NOTICES.md`.

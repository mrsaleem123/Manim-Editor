# Building the offline Windows installer

## Build-machine prerequisites

- Windows 10 or 11, 64-bit
- Python 3.11 x64 available through `py -3.11`
- Internet access for the build only
- MiKTeX installed with the packages your scenes require
- Approximately 8–15 GB free disk space

Run `BUILD-OFFLINE-INSTALLER.bat`. It creates a clean build environment, downloads and validates FFmpeg, freezes Python and Manim, copies MiKTeX, then compiles one offline Setup EXE.

### Retry after an Inno Setup failure

If the first build already completed step 4, run `RETRY-INSTALLER-ONLY.bat`. It validates and reuses `dist\ManimMediaStudio`, then performs only steps 5 and 6. The builder supports project paths containing spaces and searches the requested install folder, registry, PATH, per-user installation, and standard Inno Setup 6/7 locations for `ISCC.exe`.

If MiKTeX is installed in a non-standard location:

```powershell
$env:MIKTEX_ROOT = "D:\Apps\MiKTeX"
.\scripts\build-offline-installer.ps1
```

For a smaller build without formulas, use `-SkipLatex`. That does not meet the full-LaTeX release profile and should be used only for testing.

## Why the old corrupt-download error is prevented

The builder:

1. writes downloads to a `.partial` file;
2. follows redirects and identifies itself with a stable user agent;
3. checks minimum size and the Windows `MZ` executable header or opens the ZIP directory;
4. deletes failed responses instead of caching them;
5. retries three times across the immutable official GitHub release and the official redirect;
6. validates the final Setup EXE before reporting success.

If Inno Setup is already installed, its local `ISCC.exe` is used and no Inno download occurs.

## GitHub Actions

Two workflows are included:

- `Validate` runs the Python tests on every push and pull request.
- `Build Windows Offline Installer` can be started manually. It installs Inno Setup and MiKTeX on a Windows runner, adds the common packages used by Manim formulas, runs the validated builder, and uploads the finished Setup EXE as an Actions artifact. Preinstalling Inno Setup bypasses the bootstrap-download path that can fail on some local Windows configurations.

When a `v*` tag is pushed, the installer workflow also creates the corresponding GitHub Release and attaches the Setup EXE. GitHub Actions artifacts expire after 30 days; tagged release assets do not use that artifact retention window.

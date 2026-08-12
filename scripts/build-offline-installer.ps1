[CmdletBinding()]
param(
    [string]$Python = "py",
    [string]$MikTexRoot = $env:MIKTEX_ROOT,
    [switch]$SkipLatex,
    [switch]$InstallerOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Vendor = Join-Path $ProjectRoot "vendor"
$Cache = Join-Path $Vendor "downloads"
$Build = Join-Path $ProjectRoot "build"
$Dist = Join-Path $ProjectRoot "dist"
$InstallerDist = Join-Path $ProjectRoot "dist-installer"
$VenvPython = Join-Path $ProjectRoot ".venv-build\Scripts\python.exe"
$AppDist = Join-Path $Dist "ManimMediaStudio"

New-Item -ItemType Directory -Force -Path $Vendor, $Cache, $Build, $InstallerDist | Out-Null

function Test-PeFile([string]$Path, [long]$MinimumBytes = 1000000) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    if (-not (Test-Path -LiteralPath $Path) -or (Get-Item -LiteralPath $Path).Length -lt $MinimumBytes) { return $false }
    $stream = [IO.File]::OpenRead($Path)
    try { return ($stream.ReadByte() -eq 0x4D -and $stream.ReadByte() -eq 0x5A) } finally { $stream.Dispose() }
}

function Get-PeValidationError([string]$Path, [long]$MinimumBytes) {
    if (-not $Path) { return "no path was returned" }
    if (-not (Test-Path -LiteralPath $Path)) { return "file not found at '$Path'" }
    $length = (Get-Item -LiteralPath $Path).Length
    if ($length -lt $MinimumBytes) { return "file is only $length bytes (minimum expected: $MinimumBytes) at '$Path'" }
    return "file does not have a valid Windows PE header at '$Path'"
}

function Test-ZipFile([string]$Path, [long]$MinimumBytes = 1000000) {
    if (-not (Test-Path -LiteralPath $Path) -or (Get-Item -LiteralPath $Path).Length -lt $MinimumBytes) { return $false }
    try { Add-Type -AssemblyName System.IO.Compression.FileSystem; $zip = [IO.Compression.ZipFile]::OpenRead($Path); $count = $zip.Entries.Count; $zip.Dispose(); return $count -gt 0 } catch { return $false }
}

function Get-ValidatedDownload {
    param([string[]]$Urls, [string]$Destination, [ValidateSet("PE", "ZIP")][string]$Kind, [long]$MinimumBytes)
    if ((($Kind -eq "PE") -and (Test-PeFile $Destination $MinimumBytes)) -or (($Kind -eq "ZIP") -and (Test-ZipFile $Destination $MinimumBytes))) {
        Write-Host "Using validated cache: $Destination" -ForegroundColor DarkGreen
        return
    }
    Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
    foreach ($url in $Urls) {
        foreach ($attempt in 1..3) {
            $partial = "$Destination.partial"
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            try {
                Write-Host "Downloading $url (attempt $attempt/3)"
                Invoke-WebRequest -UseBasicParsing -MaximumRedirection 10 -Uri $url -OutFile $partial -Headers @{"User-Agent"="Manim-Media-Studio-Builder/1.0"}
                $valid = if ($Kind -eq "PE") { Test-PeFile $partial $MinimumBytes } else { Test-ZipFile $partial $MinimumBytes }
                if (-not $valid) { throw "Downloaded content failed $Kind validation (possibly an HTML/error response)." }
                Move-Item -LiteralPath $partial -Destination $Destination -Force
                return
            } catch {
                Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
                Write-Warning $_.Exception.Message
            }
        }
    }
    throw "All validated download attempts failed for $Destination"
}

function Find-Iscc {
    param([string[]]$AdditionalRoots = @())

    $candidates = @()
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source) { $candidates += $command.Source }

    $candidates += @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe"
    )

    $registryPaths = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    )
    foreach ($registryPath in $registryPaths) {
        $entry = Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue
        $installLocation = if ($entry -and $entry.PSObject.Properties["InstallLocation"]) { $entry.InstallLocation } else { $null }
        if ($installLocation) { $candidates += (Join-Path $installLocation "ISCC.exe") }
    }

    foreach ($root in $AdditionalRoots) {
        if ($root -and (Test-Path -LiteralPath $root)) {
            $found = Get-ChildItem -LiteralPath $root -Filter ISCC.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { $candidates += $found.FullName }
        }
    }

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (Test-PeFile $candidate 50000) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    return $null
}

if (-not $InstallerOnly) {
    Write-Host "[1/6] Creating isolated build environment" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        if ($Python -eq "py") { & py -3.11 -m venv (Join-Path $ProjectRoot ".venv-build") }
        else { & $Python -m venv (Join-Path $ProjectRoot ".venv-build") }
        if ($LASTEXITCODE -ne 0) { throw "Python 3.11 x64 is required." }
    }
    & $VenvPython -m pip install --upgrade pip wheel
    & $VenvPython -m pip install $ProjectRoot "pyinstaller>=6.10,<7"
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

    Write-Host "[2/6] Fetching and validating FFmpeg" -ForegroundColor Cyan
    $FfmpegZip = Join-Path $Cache "ffmpeg-release-essentials.zip"
    Get-ValidatedDownload -Urls @(
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"
    ) -Destination $FfmpegZip -Kind ZIP -MinimumBytes 20000000
    $FfmpegExtract = Join-Path $Vendor "ffmpeg-extract"
    Remove-Item -LiteralPath $FfmpegExtract -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -LiteralPath $FfmpegZip -DestinationPath $FfmpegExtract
    $FfmpegExe = Get-ChildItem -Path $FfmpegExtract -Filter ffmpeg.exe -Recurse | Select-Object -First 1
    if (-not $FfmpegExe) { throw "FFmpeg extraction produced no ffmpeg.exe." }
    $FfmpegBin = $FfmpegExe.Directory.FullName
    if (-not (Test-PeFile (Join-Path $FfmpegBin "ffmpeg.exe") 10000000)) { throw "FFmpeg extraction validation failed." }
    if (-not (Test-PeFile (Join-Path $FfmpegBin "ffprobe.exe") 10000000)) { throw "FFprobe extraction validation failed." }

    Write-Host "[3/6] Locating LaTeX" -ForegroundColor Cyan
    if (-not $SkipLatex) {
        if (-not $MikTexRoot) {
            $pdflatex = Get-Command pdflatex.exe -ErrorAction SilentlyContinue
            $miktexCandidates = @("$env:LOCALAPPDATA\Programs\MiKTeX", "$env:ProgramFiles\MiKTeX")
            if ($pdflatex) {
                $cursor = (Get-Item $pdflatex.Source).Directory
                while ($cursor -and -not (Test-Path (Join-Path $cursor.FullName "miktex"))) { $cursor = $cursor.Parent }
                if ($cursor) { $MikTexRoot = $cursor.FullName }
            }
            if (-not $MikTexRoot) { foreach ($candidate in $miktexCandidates) { if (Test-Path $candidate) { $MikTexRoot = $candidate; break } } }
        }
        if (-not $MikTexRoot -or -not (Test-Path -LiteralPath $MikTexRoot)) {
            throw "MiKTeX was not found. Install MiKTeX, set MIKTEX_ROOT, or explicitly build with -SkipLatex."
        }
        Write-Host "Bundling MiKTeX from $MikTexRoot"
    }

    Write-Host "[4/6] Building the desktop application" -ForegroundColor Cyan
    Remove-Item -LiteralPath $Dist -Recurse -Force -ErrorAction SilentlyContinue
    & $VenvPython -m PyInstaller --noconfirm --clean --windowed --name ManimMediaStudio `
        --collect-all manim --collect-all cv2 --collect-all PySide6 `
        --copy-metadata manim --copy-metadata manimpango --copy-metadata mapbox-earcut `
        (Join-Path $ProjectRoot "launcher.py")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    $Tools = Join-Path $AppDist "tools"
    New-Item -ItemType Directory -Force -Path (Join-Path $Tools "ffmpeg") | Out-Null
    Copy-Item (Join-Path $FfmpegBin "ffmpeg.exe"), (Join-Path $FfmpegBin "ffprobe.exe") -Destination (Join-Path $Tools "ffmpeg")
    if (-not $SkipLatex) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Tools "miktex") | Out-Null
        & robocopy.exe $MikTexRoot (Join-Path $Tools "miktex") /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NJH /NJS
        if ($LASTEXITCODE -ge 8) { throw "Copying MiKTeX failed with robocopy code $LASTEXITCODE" }
    }
} else {
    Write-Host "[resume] Reusing the application created by the previous build" -ForegroundColor Cyan
    $AppExe = Join-Path $AppDist "ManimMediaStudio.exe"
    if (-not (Test-PeFile $AppExe 100000)) {
        throw "Installer-only retry cannot continue: $(Get-PeValidationError $AppExe 100000). Run BUILD-OFFLINE-INSTALLER.bat once first."
    }
}

Write-Host "[5/6] Locating validated Inno Setup compiler" -ForegroundColor Cyan
$Iscc = Find-Iscc
if (-not $Iscc) {
    $InnoInstaller = Join-Path $Cache "innosetup.exe"
    Get-ValidatedDownload -Urls @(
        "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe",
        "https://jrsoftware.org/download.php/is.exe"
    ) -Destination $InnoInstaller -Kind PE -MinimumBytes 5000000
    $signature = Get-AuthenticodeSignature -FilePath $InnoInstaller
    if ($signature.Status -ne "Valid") { Remove-Item $InnoInstaller -Force; throw "Inno Setup signature validation failed: $($signature.Status)" }
    $InnoDir = Join-Path $Vendor "inno-setup"
    Remove-Item -LiteralPath $InnoDir -Recurse -Force -ErrorAction SilentlyContinue
    # Embedded quotes are required when the project path contains spaces.
    $innoArguments = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER /DIR=`"$InnoDir`""
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $InnoInstaller
    $startInfo.Arguments = $innoArguments
    $startInfo.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Inno Setup bootstrap failed with code $($process.ExitCode)." }
    $Iscc = Find-Iscc -AdditionalRoots @($InnoDir, $Vendor)
}
if (-not (Test-PeFile $Iscc 50000)) {
    throw "ISCC.exe failed validation: $(Get-PeValidationError $Iscc 50000). Install Inno Setup 6 manually, or run RETRY-INSTALLER-ONLY.bat after correcting the installation."
}
Write-Host "Using Inno Setup compiler: $Iscc" -ForegroundColor DarkGreen

Write-Host "[6/6] Compiling offline Setup EXE" -ForegroundColor Cyan
& $Iscc (Join-Path $ProjectRoot "installer\ManimMediaStudio.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
$Setup = Join-Path $InstallerDist "ManimMediaStudio-Setup-1.0.0.exe"
if (-not (Test-PeFile $Setup 10000000)) { throw "Final Setup EXE failed validation." }
Write-Host "SUCCESS: $Setup" -ForegroundColor Green

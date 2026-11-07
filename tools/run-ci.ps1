param(
    [string]$Version = "1.0.0",
    [string]$FfmpegDir,
    [string]$DistPath = "dist",
    [switch]$SkipInstaller,
    [switch]$ForceFixture
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Write-Step([string]$text) {
    Write-Host ""
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

Write-Step "Python"
python --version
python -m pip install --quiet --disable-pip-version-check -r requirements.txt -r requirements-dev.txt

Write-Step "FFmpeg"
if (-not $FfmpegDir) {
    $FfmpegDir = $env:FFMPEG_DIR
}
if (-not $FfmpegDir) {
    $candidate = Join-Path $root "..\ffmpeg-master-latest-win64-gpl\bin"
    if (Test-Path (Join-Path $candidate "ffmpeg.exe")) {
        $FfmpegDir = (Resolve-Path $candidate).Path
    }
}
if (-not $FfmpegDir -or -not (Test-Path (Join-Path $FfmpegDir "ffmpeg.exe"))) {
    throw "No encuentro ffmpeg.exe. Pasa -FfmpegDir o define FFMPEG_DIR."
}
$FfmpegDir = (Resolve-Path $FfmpegDir).Path
$env:FFMPEG_DIR = $FfmpegDir
$env:PATH = "$FfmpegDir;$env:PATH"
$ffmpeg = Join-Path $FfmpegDir "ffmpeg.exe"
$ffprobe = Join-Path $FfmpegDir "ffprobe.exe"
Write-Host "FFMPEG_DIR=$FfmpegDir"

Write-Step "Muestra de pruebas"
$mediaDir = Join-Path (Split-Path -Parent $root) ".probe\media"
New-Item -ItemType Directory -Force -Path $mediaDir | Out-Null
$sample = Join-Path $mediaDir "base.mp4"
$subs = Join-Path $mediaDir "subs.srt"

if ($ForceFixture -or -not (Test-Path $sample)) {
    & $ffmpeg -y -hide_banner -loglevel error -f lavfi -i "testsrc2=size=1280x720:rate=30" `
        -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 4 `
        -c:v libx264 -pix_fmt yuv420p -c:a aac $sample
    Write-Host "Generado $sample"
}
else {
    Write-Host "Reutilizo $sample (usa -ForceFixture para regenerarlo)"
}

if ($ForceFixture -or -not (Test-Path $subs)) {
    "1`n00:00:00,200 --> 00:00:01,500`nSubtitulo de prueba FFmpeg`n" |
        Set-Content -Path $subs -Encoding ascii
    Write-Host "Generado $subs"
}

Write-Step "JavaScript"
if (Get-Command node -ErrorAction SilentlyContinue) {
    node --check web/app.js
}
else {
    Write-Warning "Node no encontrado: se omite node --check."
}

Write-Step "Pruebas"
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Las pruebas fallaron."
}

Write-Step "Empaquetado (.exe)"
$env:FFGUI_DISTPATH = $DistPath
cmd /c build.bat
if ($LASTEXITCODE -ne 0) {
    throw "build.bat terminó con código $LASTEXITCODE."
}

if (-not $SkipInstaller) {
    Write-Step "Instalador"
    & (Join-Path $root "installer\build-installer.ps1") -Version $Version
}

Write-Step "Resultado"
Write-Host "Portable:   $(Join-Path $root "$DistPath\FFmpegStudio")"
if (-not $SkipInstaller) {
    Write-Host "Instalador: $(Join-Path $root "installer\Output\FFmpegStudio-Setup-$Version.exe")"
}

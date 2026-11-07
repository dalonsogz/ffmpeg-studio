#Requires -Version 5.1
<#
  Comprueba el entorno antes de trabajar en el proyecto.
  Detecta las trampas que ya han costado tiempo: TEMP sin permiso de ejecución,
  unidad distinta de C: para .NET, PowerShell 5.1, falta de FFmpeg/NSIS, etc.

  Uso:
    powershell -ExecutionPolicy Bypass -File tools\check-env.ps1
    powershell -ExecutionPolicy Bypass -File tools\check-env.ps1 -Strict   # avisos = error
#>
param([switch]$Strict)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$script:errors = 0
$script:warnings = 0

function Ok([string]$message) { Write-Host "[ OK  ] $message" -ForegroundColor Green }
function Warn([string]$message) {
    Write-Host "[AVISO] $message" -ForegroundColor Yellow
    $script:warnings++
}
function Fail([string]$message) {
    Write-Host "[ERROR] $message" -ForegroundColor Red
    $script:errors++
}

function Test-Writable([string]$directory) {
    try {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
        $probe = Join-Path $directory ("ffgui-write-" + [guid]::NewGuid().ToString("N") + ".tmp")
        Set-Content -Path $probe -Value "x" -Encoding Ascii
        Remove-Item $probe -Force
        return $true
    }
    catch {
        return $false
    }
}

Write-Host "Comprobando entorno en $root" -ForegroundColor Cyan
Write-Host ""

# --- PowerShell -----------------------------------------------------------
if ($PSVersionTable.PSVersion.Major -ge 7) {
    Ok "PowerShell $($PSVersionTable.PSVersion)"
}
else {
    Warn "PowerShell $($PSVersionTable.PSVersion): al escribir UTF-8 con Set-Content/Out-File se corrompe. Edita con Python (encoding='utf-8') o con la herramienta del agente."
}

# --- Python y dependencias ------------------------------------------------
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pyVersion = (& python --version 2>&1) -join ""
    Ok "Python: $pyVersion"

    & python -c "import webview" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Ok "pywebview instalado"
    }
    else {
        Warn "Falta pywebview: pip install -r requirements.txt"
    }

    & python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Ok "PyInstaller instalado"
    }
    else {
        Warn "Falta PyInstaller: pip install -r requirements-dev.txt (solo para empaquetar)"
    }
}
else {
    Fail "Python no está en PATH."
}

# --- Node (solo para node --check) ---------------------------------------
if (Get-Command node -ErrorAction SilentlyContinue) {
    Ok "Node: $(& node --version)"
}
else {
    Warn "Node no encontrado: el CI comprueba web/app.js con 'node --check'; en local puedes omitirlo."
}

# --- FFmpeg ---------------------------------------------------------------
$ffmpegCandidates = @()
if ($env:FFMPEG_DIR) {
    $ffmpegCandidates += (Join-Path $env:FFMPEG_DIR "ffmpeg.exe")
    $ffmpegCandidates += (Join-Path $env:FFMPEG_DIR "bin\ffmpeg.exe")
}
$ffmpegCandidates += @(
    (Join-Path $root "..\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"),
    (Join-Path $root "tools\ffmpeg\bin\ffmpeg.exe"),
    (Join-Path $root "dist\FFmpegStudio\ffmpeg\bin\ffmpeg.exe")
)
$ffmpeg = $ffmpegCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($ffmpeg) {
    $ffmpeg = (Resolve-Path $ffmpeg).Path
    Ok "FFmpeg: $ffmpeg"
    $ffprobe = Join-Path (Split-Path $ffmpeg) "ffprobe.exe"
    if (Test-Path $ffprobe) { Ok "ffprobe junto a FFmpeg" }
    else { Fail "Falta ffprobe.exe junto a $ffmpeg" }
}
else {
    Fail "No se encuentra ffmpeg.exe. Define FFMPEG_DIR o coloca FFmpeg en ..\ffmpeg-master-latest-win64-gpl\bin."
}

# --- TEMP: escritura y ejecución -----------------------------------------
$temp = [System.IO.Path]::GetTempPath()
if (Test-Writable $temp) {
    Ok "TEMP escribible: $temp"
}
else {
    Fail "TEMP no es escribible: $temp"
}

$probeExe = Join-Path $temp ("ffgui-exec-" + [guid]::NewGuid().ToString("N") + ".exe")
try {
    Copy-Item (Join-Path $env:SystemRoot "System32\hostname.exe") $probeExe -Force
    $null = & $probeExe 2>&1
    if ($LASTEXITCODE -eq 0) {
        Ok "TEMP permite ejecutar binarios"
    }
    else {
        Warn "TEMP no permite ejecutar binarios (código $LASTEXITCODE). Los instaladores NSIS deben usar _?=`$INSTDIR."
    }
}
catch {
    Warn "TEMP permite escribir pero NO ejecutar. Los instaladores NSIS deben usar _?=`$INSTDIR y no copiarse a Temp."
}
finally {
    Remove-Item $probeExe -Force -ErrorAction SilentlyContinue
}

# --- Unidad del proyecto --------------------------------------------------
$drive = [System.IO.Path]::GetPathRoot($root)
if ($drive -ieq "C:\") {
    Ok "Proyecto en $drive"
}
else {
    Warn "Proyecto en $drive (no C:): .NET puede tratar la ruta como remota. El .exe necesita FFmpegStudio.exe.config con loadFromRemoteSources."
}

# --- Carpetas del perfil --------------------------------------------------
$videos = Join-Path $env:USERPROFILE "Videos"
if (Test-Writable $videos) {
    Ok "Videos escribible"
}
else {
    Warn "Videos no es escribible: la grabación de pantalla usará otra carpeta (salida, perfil o temporal)."
}

# --- Empaquetado e instalador --------------------------------------------
if (Test-Path (Join-Path $root "dist\FFmpegStudio\FFmpegStudio.exe")) {
    Ok "dist\FFmpegStudio\FFmpegStudio.exe presente"
}
else {
    Warn "Aún no hay dist\: ejecuta build.bat para empaquetar."
}

if (Test-Path (Join-Path $root "build")) {
    Warn "Existe build\: NO ejecutes build\FFmpegStudio\FFmpegStudio.exe (intermedio roto, falla con 'Failed to load Python DLL')."
}

$nsisCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe"),
    (Join-Path $env:ProgramFiles "NSIS\makensis.exe"),
    (Join-Path $root "tools\nsis\makensis.exe")
)
$makensis = $nsisCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($makensis) {
    Ok "NSIS: $makensis"
}
else {
    Warn "NSIS no instalado: no se podrá compilar el instalador (winget install NSIS.NSIS)."
}

# --- Resumen --------------------------------------------------------------
Write-Host ""
Write-Host "Resumen: $($script:errors) error(es), $($script:warnings) aviso(s)." -ForegroundColor Cyan

if ($script:errors -gt 0) { exit 1 }
if ($Strict -and $script:warnings -gt 0) { exit 1 }
exit 0

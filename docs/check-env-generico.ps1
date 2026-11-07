#Requires -Version 5.1
<#
  Comprobación genérica de entorno para aplicaciones de escritorio en Windows.
  Copia este archivo a tools\check-env.ps1 en el proyecto nuevo y ajusta los parámetros.

  Uso (desde la raíz del proyecto):
    powershell -ExecutionPolicy Bypass -File tools\check-env.ps1
    powershell -ExecutionPolicy Bypass -File tools\check-env.ps1 `
        -AppExe "dist\MiApp\MiApp.exe" -CliTool "ffmpeg.exe" -CliVersionArg "-version" `
        -OutputDir "D:\salida" -InstallerCompiler "makensis.exe"
    powershell -ExecutionPolicy Bypass -File tools\check-env.ps1 -Strict   # avisos = error

  Detecta los problemas que más tiempo han costado en proyectos anteriores: TEMP sin permiso de
  ejecución, unidad fuera de C:, herramientas ausentes, ejecutables intermedios y carpetas no
  escribibles.
#>
param(
    [string]$AppExe,
    [string]$CliTool,
    [string]$CliVersionArg = "--version",
    [string]$OutputDir,
    [string]$InstallerCompiler = "",
    [switch]$Strict
)

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
function Info([string]$message) { Write-Host "[ INFO] $message" -ForegroundColor DarkGray }

function Test-Writable([string]$directory) {
    try {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
        $probe = Join-Path $directory ("envcheck-" + [guid]::NewGuid().ToString("N") + ".tmp")
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
    Warn "PowerShell $($PSVersionTable.PSVersion): Set-Content/Out-File corrompen UTF-8. Edita textos con Python (encoding='utf-8') o con la herramienta del agente."
}

# --- Herramientas opcionales ---------------------------------------------
if (Get-Command python -ErrorAction SilentlyContinue) {
    Ok "Python: $((& python --version 2>&1) -join '')"
}
else {
    Warn "Python no encontrado (solo necesario si el proyecto lo usa)."
}

if (Get-Command node -ErrorAction SilentlyContinue) {
    Ok "Node: $(& node --version)"
}
else {
    Info "Node no encontrado (opcional; se usa para comprobar JavaScript)."
}

# --- Herramienta externa principal ---------------------------------------
if ($CliTool) {
    $resolved = $null
    if (Test-Path $CliTool) {
        $resolved = (Resolve-Path $CliTool).Path
    }
    else {
        $command = Get-Command $CliTool -ErrorAction SilentlyContinue
        if ($command) { $resolved = $command.Source }
    }

    if ($resolved) {
        Ok "Herramienta: $resolved"
        try {
            $version = (& $resolved $CliVersionArg 2>&1 | Select-Object -First 1)
            if ($version) { Info "Versión: $version" }
        }
        catch {
            Info "No se pudo leer la versión de $resolved"
        }
    }
    else {
        Fail "No se encuentra la herramienta '$CliTool'. Instálala o ajusta el PATH."
    }
}

# --- TEMP: escritura y ejecución -----------------------------------------
$temp = [System.IO.Path]::GetTempPath()
if (Test-Writable $temp) {
    Ok "TEMP escribible: $temp"
}
else {
    Fail "TEMP no es escribible: $temp"
}

$probeExe = Join-Path $temp ("envcheck-" + [guid]::NewGuid().ToString("N") + ".exe")
try {
    Copy-Item (Join-Path $env:SystemRoot "System32\hostname.exe") $probeExe -Force
    $null = & $probeExe 2>&1
    if ($LASTEXITCODE -eq 0) {
        Ok "TEMP permite ejecutar binarios"
    }
    else {
        Warn "TEMP no permite ejecutar binarios (código $LASTEXITCODE). Evita instaladores que se copien a Temp; usa _?=`$INSTDIR."
    }
}
catch {
    Warn "TEMP permite escribir pero NO ejecutar. No dependas de ejecutar binarios copiados a Temp (instaladores NSIS: _?=`$INSTDIR)."
}
finally {
    Remove-Item $probeExe -Force -ErrorAction SilentlyContinue
}

# --- Unidad del proyecto --------------------------------------------------
$drive = [System.IO.Path]::GetPathRoot($root)
if ($drive -ieq "C:\") {
    Ok "Proyecto en C:"
}
else {
    Warn "Proyecto en $drive (no C:): .NET puede tratar la ruta como remota (loadFromRemoteSources); pruébalo desde el .exe final."
}

# --- Carpeta de salida ----------------------------------------------------
if ($OutputDir) {
    if (Test-Writable $OutputDir) {
        Ok "Carpeta de salida escribible: $OutputDir"
    }
    else {
        Fail "No se puede escribir en la carpeta de salida: $OutputDir"
    }
}

# --- Ejecutable empaquetado ----------------------------------------------
if ($AppExe) {
    if (Test-Path $AppExe) {
        Ok "Ejecutable: $AppExe"
    }
    else {
        Fail "No existe '$AppExe'. Empaqueta antes de probar."
    }

    if ($AppExe -match '[\\/]build[\\/]') {
        Warn "El .exe está dentro de build\: es intermedio y suele fallar (DLLs ausentes). Usa dist\."
    }
}

if (Test-Path (Join-Path $root "build")) {
    Warn "Existe build\: no ejecutes binarios de ahí; usa la carpeta de distribución."
}

# --- Compilador de instalador --------------------------------------------
if ($InstallerCompiler) {
    $command = Get-Command $InstallerCompiler -ErrorAction SilentlyContinue
    $toolPath = $null
    if ($command) {
        $toolPath = $command.Source
    }
    elseif ((Split-Path -Leaf $InstallerCompiler) -ieq "makensis.exe") {
        # NSIS no suele estar en PATH; se busca en sus rutas habituales.
        $candidates = @(
            (Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe"),
            (Join-Path $env:ProgramFiles "NSIS\makensis.exe"),
            (Join-Path $root "tools\nsis\makensis.exe")
        )
        $toolPath = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    }

    if ($toolPath) {
        Ok "Compilador de instalador: $toolPath"
    }
    else {
        Warn "No se encuentra '$InstallerCompiler': no se podrá compilar el instalador."
    }
}

# --- Restos de desarrollo -------------------------------------------------
foreach ($leftover in @(".tmp", "__pycache__")) {
    if (Test-Path (Join-Path $root $leftover)) {
        Info "Resto de desarrollo presente: $leftover"
    }
}

# --- Resumen --------------------------------------------------------------
Write-Host ""
Write-Host "Resumen: $($script:errors) error(es), $($script:warnings) aviso(s)." -ForegroundColor Cyan

if ($script:errors -gt 0) { exit 1 }
if ($Strict -and $script:warnings -gt 0) { exit 1 }
exit 0

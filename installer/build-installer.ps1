param(
    [string]$Version = "1.0.0",
    [string]$Nsis,
    [string]$Iscc,
    [switch]$Inno
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist\FFmpegStudio"

if (-not (Test-Path (Join-Path $dist "FFmpegStudio.exe"))) {
    throw "No existe dist\FFmpegStudio\FFmpegStudio.exe. Ejecuta build.bat primero."
}

# NSIS no crea la carpeta de salida; Inno Setup sí. La aseguramos para ambos.
$outputDir = Join-Path $PSScriptRoot "Output"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

function Find-Tool([string[]]$candidates) {
    return $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

Push-Location $PSScriptRoot
try {
    if (-not $Inno) {
        if (-not $Nsis) {
            $Nsis = Find-Tool @(
                (Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe"),
                (Join-Path $env:ProgramFiles "NSIS\makensis.exe"),
                (Join-Path $root "tools\nsis\makensis.exe")
            )
        }
        if (-not $Nsis) {
            throw "No se encontró makensis.exe. Instala NSIS 3 o pasa -Nsis <ruta>."
        }
        Write-Host "Compilando instalador $Version con NSIS ($Nsis)..."
        & $Nsis "/DAPP_VERSION=$Version" "FFmpegStudio.nsi"
        if ($LASTEXITCODE -ne 0) {
            throw "makensis terminó con código $LASTEXITCODE."
        }
        $output = Join-Path $PSScriptRoot "Output\FFmpegStudio-Setup-$Version.exe"
    }
    else {
        if (-not $Iscc) {
            $Iscc = Find-Tool @(
                (Join-Path $root "tools\InnoSetup\ISCC.exe"),
                (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
                (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
                (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
            )
        }
        if (-not $Iscc) {
            throw "No se encontró ISCC.exe. Instala Inno Setup 6 o pasa -Iscc <ruta>."
        }
        Write-Host "Compilando instalador $Version con Inno Setup ($Iscc)..."
        & $Iscc "/DMyAppVersion=$Version" "FFmpegStudio.iss"
        if ($LASTEXITCODE -ne 0) {
            throw "ISCC terminó con código $LASTEXITCODE."
        }
        $output = Join-Path $PSScriptRoot "Output\FFmpegStudio-Setup-$Version.exe"
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $output)) {
    throw "No se generó el instalador esperado: $output"
}

$size = [math]::Round((Get-Item $output).Length / 1MB, 1)
Write-Host "Listo: $output ($size MB)"

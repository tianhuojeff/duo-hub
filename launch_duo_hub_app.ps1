param(
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildScript = Join-Path $projectRoot 'build_windows_app.ps1'
$appPath = Join-Path $projectRoot 'dist\DuoHub\DuoHub.exe'

if ($Rebuild -or -not (Test-Path -LiteralPath $appPath)) {
    & $buildScript
}

if (-not (Test-Path -LiteralPath $appPath)) {
    throw "Duo Hub desktop executable not found: $appPath"
}

Start-Process -FilePath $appPath -WorkingDirectory (Split-Path -Parent $appPath)

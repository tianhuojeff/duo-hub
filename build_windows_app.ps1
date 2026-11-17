param(
    [string]$BuildPython = 'C:\Users\tianhuo\AppData\Local\DuoHubBuild\venv\Scripts\python.exe'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $projectRoot 'dist'
$workRoot = Join-Path $projectRoot 'build\pyinstaller'

if (-not (Test-Path -LiteralPath $BuildPython)) {
    throw "Desktop build Python not found: $BuildPython"
}

foreach ($target in @((Join-Path $distRoot 'DuoHub'), $workRoot)) {
    $resolvedParent = [IO.Path]::GetFullPath((Split-Path -Parent $target))
    $resolvedProject = [IO.Path]::GetFullPath($projectRoot)
    if (-not $resolvedParent.StartsWith($resolvedProject, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean path outside project: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Push-Location $projectRoot
try {
    & $BuildPython -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $distRoot `
        --workpath $workRoot `
        .\DuoHub.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$exe = Join-Path $distRoot 'DuoHub\DuoHub.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Build finished without expected executable: $exe"
}

Get-Item -LiteralPath $exe | Select-Object FullName, Length, LastWriteTime


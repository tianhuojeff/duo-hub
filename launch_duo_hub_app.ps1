param(
    [int]$Port = 5199,
    [int]$CcmrPort = 18080,
    [int]$OpenClawPort = 18789,
    [switch]$RestartGateways
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Url = "http://127.0.0.1:$Port"
$StateUrl = "$Url/api/state"
$OutLog = Join-Path $Root 'duo_hub_server.out.log'
$ErrLog = Join-Path $Root 'duo_hub_server.err.log'
$GatewayLaunchLog = Join-Path $Root 'duo_hub_gateway_launcher.log'

function Add-LocalProxyBypass {
    $local = @('127.0.0.1', 'localhost', '::1')
    $current = $env:NO_PROXY
    if (-not $current) { $current = $env:no_proxy }
    $items = @()
    if ($current) {
        $items += ($current -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
    foreach ($entry in $local) {
        if ($items -notcontains $entry) {
            $items += $entry
        }
    }
    $merged = ($items | Select-Object -Unique) -join ','
    $env:NO_PROXY = $merged
    $env:no_proxy = $merged
}

function Write-LaunchLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $GatewayLaunchLog -Value $line -Encoding UTF8
}

function Get-DuoHubRequiredPythonModules {
    $required = @()
    $source = Join-Path $Root 'duo_hub.py'
    if (Test-Path -LiteralPath $source) {
        $text = Get-Content -LiteralPath $source -Raw -ErrorAction SilentlyContinue
        if ($text -match '(?m)^\s*(from\s+flask\s+import|import\s+flask\b)') {
            $required += 'flask'
        }
    }
    if ($env:DUO_REQUIRED_PY_MODULES) {
        $required += ($env:DUO_REQUIRED_PY_MODULES -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
    return @($required | Select-Object -Unique)
}

function Test-DuoHubPython {
    param(
        [string]$Candidate,
        [string[]]$RequiredModules
    )
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate)) {
        return $false
    }

    $source = Join-Path $Root 'duo_hub.py'
    & $Candidate -m py_compile $source *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-LaunchLog "Python candidate rejected by py_compile: $Candidate"
        return $false
    }

    foreach ($module in $RequiredModules) {
        & $Candidate -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$module') else 1)" *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-LaunchLog "Python candidate missing module '$module': $Candidate"
            return $false
        }
    }

    return $true
}

function Resolve-DuoHubPython {
    $required = Get-DuoHubRequiredPythonModules
    $candidates = @()
    if ($env:DUO_PYTHON) {
        $candidates += $env:DUO_PYTHON
    }
    $candidates += @(
        (Join-Path $Root '.venv\Scripts\python.exe'),
        (Join-Path $Root 'venv\Scripts\python.exe'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    )
    $candidates += (Get-Command python -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        try {
            $resolved = (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
        } catch {
            continue
        }
        if (Test-DuoHubPython -Candidate $resolved -RequiredModules $required) {
            Write-LaunchLog "Using Duo Hub Python: $resolved"
            return $resolved
        }
    }

    $moduleText = if ($required.Count) { $required -join ', ' } else { 'stdlib only' }
    throw "No compatible Python found for Duo Hub (required: $moduleText)."
}

function Invoke-LocalState {
    try {
        $req = [System.Net.HttpWebRequest]::Create($StateUrl)
        $req.Proxy = $null
        $req.Timeout = 1500
        $req.ReadWriteTimeout = 1500
        $resp = $req.GetResponse()
        try {
            $reader = [System.IO.StreamReader]::new($resp.GetResponseStream(), [System.Text.Encoding]::UTF8)
            return $reader.ReadToEnd()
        } finally {
            $resp.Close()
        }
    } catch {
        return $null
    }
}

function Stop-PortOwner {
    Stop-LocalPortOwner -LocalPort $Port -Label 'Duo Hub'
}

function Stop-LocalPortOwner {
    param(
        [int]$LocalPort,
        [string]$Label
    )
    $owners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($ownerPid in $owners) {
        if ($ownerPid -and $ownerPid -ne $PID) {
            Write-LaunchLog "Stopping $Label process $ownerPid on port $LocalPort"
            Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-LocalPort {
    param([int]$LocalPort)
    return [bool](Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue)
}

function Wait-LocalPort {
    param(
        [int]$LocalPort,
        [int]$Seconds = 10
    )
    for ($i = 0; $i -lt ($Seconds * 2); $i++) {
        if (Test-LocalPort -LocalPort $LocalPort) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-MinimizedCommand {
    param(
        [string]$CommandName,
        [string[]]$Arguments,
        [string]$Label
    )
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) {
        Write-LaunchLog "$Label not found on PATH"
        return $false
    }

    $source = $cmd.Source
    $ext = [System.IO.Path]::GetExtension($source).ToLowerInvariant()
    if ($ext -eq '.ps1') {
        Start-Process `
            -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
            -ArgumentList (@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $source) + $Arguments) `
            -WorkingDirectory $Root `
            -WindowStyle Minimized | Out-Null
    } elseif ($ext -eq '.cmd' -or $ext -eq '.bat') {
        Start-Process `
            -FilePath "$env:SystemRoot\System32\cmd.exe" `
            -ArgumentList (@('/c', $source) + $Arguments) `
            -WorkingDirectory $Root `
            -WindowStyle Minimized | Out-Null
    } else {
        Start-Process `
            -FilePath $source `
            -ArgumentList $Arguments `
            -WorkingDirectory $Root `
            -WindowStyle Minimized | Out-Null
    }

    Write-LaunchLog "Started $Label with $source $($Arguments -join ' ')"
    return $true
}

function Ensure-Gateway {
    param(
        [string]$Label,
        [int]$LocalPort,
        [string]$CommandName,
        [string[]]$Arguments,
        [int]$WaitSeconds = 10
    )

    if (Test-LocalPort -LocalPort $LocalPort) {
        Write-LaunchLog "$Label already listening on port $LocalPort"
        return $true
    }

    if (-not (Start-MinimizedCommand -CommandName $CommandName -Arguments $Arguments -Label $Label)) {
        return $false
    }

    $ready = Wait-LocalPort -LocalPort $LocalPort -Seconds $WaitSeconds
    if ($ready) {
        Write-LaunchLog "$Label is now listening on port $LocalPort"
    } else {
        Write-LaunchLog "$Label did not open port $LocalPort within $WaitSeconds seconds"
    }
    return $ready
}

function Start-DuoHub {
    $command = "Set-Location -LiteralPath '$Root'; & '$Python' 'duo_hub.py' 1>> '$OutLog' 2>> '$ErrLog'"
    Start-Process `
        -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -ArgumentList @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $command) `
        -WorkingDirectory $Root `
        -WindowStyle Minimized | Out-Null
}

$env:DUO_PORT = [string]$Port
$env:DUO_CCMR_PORT = [string]$CcmrPort
$env:DUO_OPENCLAW_PORT = [string]$OpenClawPort
Add-LocalProxyBypass
$Python = Resolve-DuoHubPython

$CcmrArgs = @('start', '--port', [string]$CcmrPort, '--host', '127.0.0.1')
$CcmrConfig = Join-Path $Root 'models.yaml'
if (Test-Path -LiteralPath $CcmrConfig) {
    $CcmrArgs += @('--config', $CcmrConfig)
}

if (-not $env:IKUNCODE_API_KEY -and $env:IKUN_API_KEY) {
    $env:IKUNCODE_API_KEY = $env:IKUN_API_KEY
}
if ($RestartGateways) {
    Stop-LocalPortOwner -LocalPort $Port -Label 'Duo Hub'
    Stop-LocalPortOwner -LocalPort $CcmrPort -Label 'ccmr'
    Stop-LocalPortOwner -LocalPort $OpenClawPort -Label 'OpenClaw gateway'
    Start-Sleep -Seconds 1
}
Ensure-Gateway -Label 'ccmr' -LocalPort $CcmrPort -CommandName 'ccmr' -Arguments $CcmrArgs -WaitSeconds 8 | Out-Null
Ensure-Gateway -Label 'OpenClaw gateway' -LocalPort $OpenClawPort -CommandName 'openclaw' -Arguments @('gateway', 'run') -WaitSeconds 12 | Out-Null

$state = Invoke-LocalState
if ($state -and $state -notmatch '"codex"') {
    Stop-PortOwner
    Start-Sleep -Seconds 1
    $state = $null
}

if (-not $state) {
    Start-DuoHub
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        $state = Invoke-LocalState
        if ($state -and $state -match '"codex"') {
            break
        }
    }
}

$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$Chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($Chrome) {
    Start-Process -FilePath $Chrome -ArgumentList @("--proxy-bypass-list=<-loopback>;127.0.0.1;localhost;::1", "--app=$Url")
} else {
    Start-Process $Url
}

param(
    [int]$Port = 5199
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Url = "http://127.0.0.1:$Port"
$StateUrl = "$Url/api/state"
$Python = (Get-Command python -ErrorAction Stop).Source
$OutLog = Join-Path $Root 'duo_hub_server.out.log'
$ErrLog = Join-Path $Root 'duo_hub_server.err.log'

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
    $owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $owners) {
        if ($pid -and $pid -ne $PID) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-DuoHub {
    Start-Process `
        -FilePath $Python `
        -ArgumentList @('duo_hub.py') `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog | Out-Null
}

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
    "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$Chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($Chrome) {
    Start-Process -FilePath $Chrome -ArgumentList @("--app=$Url")
} else {
    Start-Process $Url
}

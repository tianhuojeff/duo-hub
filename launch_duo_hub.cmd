@echo off
chcp 65001 >nul
title Duo Hub - 三AI协作中心
color 0E

echo ============================================================
echo   Duo Hub - 三AI协作中心
echo ============================================================
echo.

:: ============================================================
:: 1. ccmr (port from env or default 8080)
:: ============================================================
if "%DUO_CCMR_PORT%"=="" set DUO_CCMR_PORT=8080
echo [1/3] ccmr (port %DUO_CCMR_PORT%)...
netstat -ano 2>nul | findstr ":%DUO_CCMR_PORT%.*LISTENING" >nul
if errorlevel 1 (
    start "ccmr" ccmr start
    timeout /t 5 /nobreak >nul
) else (
    echo   already running
)

:: ============================================================
:: 2. OpenClaw (port from env or default 18789)
:: ============================================================
if "%DUO_OPENCLAW_PORT%"=="" set DUO_OPENCLAW_PORT=18789
echo [2/3] OpenClaw (port %DUO_OPENCLAW_PORT%)...
netstat -ano 2>nul | findstr ":%DUO_OPENCLAW_PORT%.*LISTENING" >nul
if errorlevel 1 (
    start "OpenClaw" openclaw gateway run
    timeout /t 8 /nobreak >nul
) else (
    echo   already running
)

:: ============================================================
:: Codex CLI check (no gateway required)
:: ============================================================
where codex.cmd >nul 2>nul
if errorlevel 1 (
    where codex >nul 2>nul
    if errorlevel 1 (
        echo [!] Codex CLI not found in PATH
    ) else (
        echo [OK] Codex CLI found
    )
) else (
    echo [OK] Codex CLI found
)

:: ============================================================
:: 3. Duo Hub
:: ============================================================
if "%DUO_PORT%"=="" set DUO_PORT=5199
echo [3/3] Duo Hub (port %DUO_PORT%)...
cd /d "%~dp0"
start "Duo Hub" python duo_hub.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:%DUO_PORT%

echo.
echo   http://127.0.0.1:%DUO_PORT%
echo ============================================================
pause >nul

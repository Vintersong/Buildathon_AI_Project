#requires -Version 5.1
<#
  dev.ps1 - launch the FastAPI backend and the Vite frontend together.

  Usage:
      .\dev.ps1

  Opens two terminal windows:
      backend  -> http://127.0.0.1:8080  (FastAPI / uvicorn --reload)
      frontend -> http://localhost:3000  (Vite dev server, proxies /api -> :8080)

  Close a window to stop that server. Run this from anywhere; it resolves
  the project root from its own location.
#>
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# Pick a Python interpreter: project venv if present, otherwise whatever is on PATH.
$py =
    if     (Test-Path "$root\venv\Scripts\python.exe")  { "$root\venv\Scripts\python.exe" }
    elseif (Test-Path "$root\.venv\Scripts\python.exe") { "$root\.venv\Scripts\python.exe" }
    else   { "python" }

# First-run convenience: install frontend deps if they are missing.
if (-not (Test-Path "$root\node_modules")) {
    Write-Host "Installing frontend dependencies (first run)..." -ForegroundColor Yellow
    Push-Location $root
    npm install
    Pop-Location
}

$backendCmd  = "Set-Location '$root'; & '$py' -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --reload"
$frontendCmd = "Set-Location '$root'; npm run dev"

Write-Host "Backend  -> http://127.0.0.1:8080" -ForegroundColor Cyan
Write-Host "Frontend -> http://localhost:3000" -ForegroundColor Cyan

Start-Process powershell -ArgumentList '-NoExit', '-Command', $backendCmd  | Out-Null
Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontendCmd | Out-Null

Write-Host "`nLaunched both servers in separate windows. Open http://localhost:3000" -ForegroundColor Green

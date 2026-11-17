# One-command local start for Data IA v1 (BRIEF "done means").
# Usage: powershell -ExecutionPolicy Bypass -File scripts/dev_start.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path .venv)) {
  python -m venv .venv
}
& .\.venv\Scripts\python -m pip install -U pip -q
& .\.venv\Scripts\pip install -e ".[dev]" -q

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
}

$dockerOk = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
  try {
    docker compose up -d
    $dockerOk = $true
    Write-Host "Postgres (pgvector) started via docker compose."
  } catch {
    Write-Host "docker compose failed; continuing with SQLite fallback."
  }
} else {
  Write-Host "Docker not found; using SQLite (see DATABASE_URL in .env)."
}

Write-Host "Running offline cycle (stub LLM)..."
& .\.venv\Scripts\python -m data_ia.cli cycle
& .\.venv\Scripts\python -m data_ia.cli brier

Write-Host ""
Write-Host "Dashboard:  .\.venv\Scripts\streamlit run src\data_ia\dashboard\app.py"
Write-Host "Tests:      .\.venv\Scripts\pytest"
if ($dockerOk) {
  Write-Host "DB:         Postgres via docker compose"
} else {
  Write-Host "DB:         SQLite ./data/dataia.db"
}

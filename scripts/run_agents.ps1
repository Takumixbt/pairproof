# Starts Builder + Verifier provider processes in the background, logging to
# scripts/logs/. Run this before a demo/judging session; pair with
# stop_agents.ps1 to shut them down afterward. No auto-restart, no auto-start
# on boot -- this PC is only "deployed" while you choose to have it be.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$logDir = "scripts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$pidFile = "scripts\agents.pid"

if (Test-Path $pidFile) {
    Write-Host "agents.pid already exists -- run stop_agents.ps1 first if agents are already running."
    exit 1
}

$python = ".venv\Scripts\python.exe"
$verifier = Start-Process -FilePath $python -ArgumentList "-m", "agent_verifier.provider" `
    -RedirectStandardOutput "$logDir\verifier.out.log" -RedirectStandardError "$logDir\verifier.err.log" `
    -PassThru -WindowStyle Hidden
$builder = Start-Process -FilePath $python -ArgumentList "-m", "agent_builder.provider" `
    -RedirectStandardOutput "$logDir\builder.out.log" -RedirectStandardError "$logDir\builder.err.log" `
    -PassThru -WindowStyle Hidden

"$($verifier.Id)`n$($builder.Id)" | Set-Content $pidFile

Write-Host "Verifier started (PID $($verifier.Id)), logs at $logDir\verifier.*.log"
Write-Host "Builder started (PID $($builder.Id)), logs at $logDir\builder.*.log"
Write-Host "Run scripts\stop_agents.ps1 when you're done."

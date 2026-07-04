# Stops the Builder + Verifier processes started by run_agents.ps1.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$pidFile = "scripts\agents.pid"
if (-not (Test-Path $pidFile)) {
    Write-Host "No agents.pid found -- nothing to stop."
    exit 0
}

Get-Content $pidFile | ForEach-Object {
    $procId = $_.Trim()
    if ($procId -eq "") { return }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $procId -Force
        Write-Host "Stopped PID $procId"
    } else {
        Write-Host "PID $procId not running (already stopped?)"
    }
}

Remove-Item $pidFile

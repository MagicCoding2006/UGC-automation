$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop with WSL2, then run this script again.' }
if (-not (Test-Path '.env')) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    $rng.GetBytes($bytes)
    $workerToken = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    $rng.Dispose()
    (Get-Content '.env.example') -replace '^UGC_TOKEN=$', "UGC_TOKEN=$token" -replace '^UGC_WORKER_TOKEN=$', "UGC_WORKER_TOKEN=$workerToken" | Set-Content '.env' -Encoding ascii
}
docker compose up -d --build api worker
if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed. Verify Docker Desktop is running.' }
Write-Host 'ReelForge is starting at http://localhost:8000'
Write-Host 'Use UGC_TOKEN from .env to sign in. First build may take several minutes.'

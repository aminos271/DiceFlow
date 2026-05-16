$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "web"
$runRoot = Join-Path $repoRoot ".run"

$backendPidFile = Join-Path $runRoot "backend.pid"
$frontendPidFile = Join-Path $runRoot "frontend.pid"
$backendLog = Join-Path $runRoot "backend.log"
$backendErrLog = Join-Path $runRoot "backend.err.log"
$frontendLog = Join-Path $runRoot "frontend.log"
$frontendErrLog = Join-Path $runRoot "frontend.err.log"

New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

function Stop-TrackedProcess {
    param(
        [string]$PidFile
    )

    if (-not (Test-Path $PidFile)) {
        return
    }

    $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $rawPid) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $proc = Get-Process -Id ([int]$rawPid) -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $proc.Id -Force
    }

    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-MatchingProcessTree {
    param(
        [string]$ProcessName,
        [string]$CommandLinePattern
    )

    $matches = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -eq $ProcessName -and $_.CommandLine -match $CommandLinePattern }

    foreach ($match in $matches) {
        & taskkill /PID $match.ProcessId /T /F | Out-Null
    }
}

function Start-TrackedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$PidFile,
        [string]$LogFile,
        [string]$ErrLogFile
    )

    Stop-TrackedProcess -PidFile $PidFile

    $proc = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError $ErrLogFile `
        -PassThru `
        -WindowStyle Hidden

    Set-Content -Path $PidFile -Value $proc.Id
    return $proc
}

if (-not (Test-Path (Join-Path $webRoot "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $webRoot
    try {
        & npm.cmd install
    }
    finally {
        Pop-Location
    }
}

Stop-MatchingProcessTree -ProcessName "python.exe" -CommandLinePattern "uvicorn.+diceflow\.web\.server:app"
Stop-MatchingProcessTree -ProcessName "node.exe" -CommandLinePattern "vite.+5173"

$backend = Start-TrackedProcess `
    -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "diceflow.web.server:app", "--reload", "--port", "8001") `
    -WorkingDirectory $repoRoot `
    -PidFile $backendPidFile `
    -LogFile $backendLog `
    -ErrLogFile $backendErrLog

$frontend = Start-TrackedProcess `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--port", "5173") `
    -WorkingDirectory $webRoot `
    -PidFile $frontendPidFile `
    -LogFile $frontendLog `
    -ErrLogFile $frontendErrLog

Write-Host "DiceFlow web services started."
Write-Host "Backend : http://localhost:8001"
Write-Host "Frontend: http://localhost:5173"
Write-Host "Backend PID : $($backend.Id)"
Write-Host "Frontend PID: $($frontend.Id)"
Write-Host "Logs:"
Write-Host "  $backendLog"
Write-Host "  $backendErrLog"
Write-Host "  $frontendLog"
Write-Host "  $frontendErrLog"
Write-Host "Stop with: powershell -ExecutionPolicy Bypass -File .\scripts\stop-web.ps1"

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runRoot = Join-Path $repoRoot ".run"

function Stop-TrackedProcess {
    param(
        [string]$Name,
        [string]$PidFile
    )

    if (-not (Test-Path $PidFile)) {
        Write-Host "$Name is not running."
        return
    }

    $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($rawPid) {
        $proc = Get-Process -Id ([int]$rawPid) -ErrorAction SilentlyContinue
        if ($proc) {
            & taskkill /PID $proc.Id /T /F | Out-Null
            Write-Host "Stopped $Name (PID $($proc.Id))."
        }
        else {
            Write-Host "$Name PID file existed, but process was already gone."
        }
    }

    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-PortListener {
    param(
        [int]$Port
    )

    $owningPids = @(
        netstat -ano |
        Select-String "LISTENING" |
        Select-String ":$Port\s" |
        ForEach-Object {
            $parts = ($_ -replace "\s+", " ").Trim().Split(" ")
            if ($parts.Length -ge 5) {
                $parts[-1]
            }
        } |
        Where-Object { $_ } |
        Select-Object -Unique
    )

    if (-not $owningPids) {
        return
    }

    foreach ($owningPid in $owningPids) {
        if ($owningPid -and $owningPid -ne 0) {
            & taskkill /PID $owningPid /T /F | Out-Null
            Write-Host "Stopped process on port $Port (PID $owningPid)."
        }
    }
}

Stop-TrackedProcess -Name "backend" -PidFile (Join-Path $runRoot "backend.pid")
Stop-TrackedProcess -Name "frontend" -PidFile (Join-Path $runRoot "frontend.pid")
Stop-PortListener -Port 8000
Stop-PortListener -Port 5173

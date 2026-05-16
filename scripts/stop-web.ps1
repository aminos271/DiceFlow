$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runRoot = Join-Path $repoRoot ".run"

function Stop-TrackedProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [string[]]$ExpectedProcessNames = @(),
        [string]$ExpectedCommandLinePattern = ""
    )

    if (-not (Test-Path $PidFile)) {
        Write-Host "$Name is not running."
        return
    }

    $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($rawPid) {
        $pidValue = 0
        if (-not [int]::TryParse($rawPid, [ref]$pidValue)) {
            Write-Host "$Name PID file was invalid."
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            return
        }

        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
        if ($proc) {
            $nameMatches = -not $ExpectedProcessNames -or ($ExpectedProcessNames -contains $proc.Name)
            $commandLineMatches = -not $ExpectedCommandLinePattern -or ($proc.CommandLine -match $ExpectedCommandLinePattern)

            if ($nameMatches -and $commandLineMatches) {
                & taskkill /PID $proc.ProcessId /T /F | Out-Null
                Write-Host "Stopped $Name (PID $($proc.ProcessId))."
            }
            else {
                Write-Host "$Name PID file pointed to an unrelated process; ignoring stale PID $pidValue."
            }
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

function Stop-MatchingProcessTree {
    param(
        [string]$ProcessName,
        [string]$CommandLinePattern
    )

    $matches = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -eq $ProcessName -and $_.CommandLine -match $CommandLinePattern }

    foreach ($match in $matches) {
        & taskkill /PID $match.ProcessId /T /F | Out-Null
        Write-Host "Stopped matching $ProcessName (PID $($match.ProcessId))."
    }
}

Stop-TrackedProcess `
    -Name "backend" `
    -PidFile (Join-Path $runRoot "backend.pid") `
    -ExpectedProcessNames @("python.exe") `
    -ExpectedCommandLinePattern "uvicorn.+diceflow\.web\.server:app"
Stop-TrackedProcess `
    -Name "frontend" `
    -PidFile (Join-Path $runRoot "frontend.pid") `
    -ExpectedProcessNames @("cmd.exe", "node.exe") `
    -ExpectedCommandLinePattern "(npm\.cmd.+run.+dev.+--port.+5173)|(vite.+5173)"
Stop-MatchingProcessTree -ProcessName "python.exe" -CommandLinePattern "uvicorn.+diceflow\.web\.server:app"
Stop-MatchingProcessTree -ProcessName "node.exe" -CommandLinePattern "vite.+5173"
Stop-PortListener -Port 8000
Stop-PortListener -Port 8001
Stop-PortListener -Port 5173

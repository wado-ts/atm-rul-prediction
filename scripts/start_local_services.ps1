[CmdletBinding()]
param(
    [int]$StartupTimeoutSeconds = 120,
    [int]$PollIntervalSeconds = 2
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Split-Path -Parent $ScriptDir
$SequenceDir = Join-Path $AppDir 'external_services/sequence-building-service'
$InferenceDir = Join-Path $AppDir 'external_services/inference-service'
$LogDir = if ($env:LOCAL_SERVICE_LOG_DIR) { $env:LOCAL_SERVICE_LOG_DIR } else { Join-Path $ScriptDir 'logs' }
$Processes = @()

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Find-Python([string]$ServiceDir) {
    $candidates = @(
        (Join-Path $ServiceDir '.venv/Scripts/python.exe'),
        (Join-Path $ServiceDir '.venv/bin/python')
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return $python3.Source
    }

    throw "Python was not found for $ServiceDir. Create its .venv or install Python 3.11+."
}

foreach ($requiredDir in @($AppDir, $SequenceDir, $InferenceDir)) {
    if (-not (Test-Path -LiteralPath $requiredDir -PathType Container)) {
        throw "Required service directory not found: $requiredDir"
    }
}

$SequencePython = Find-Python $SequenceDir
$InferencePython = Find-Python $InferenceDir
$AppPython = Find-Python $AppDir

function Start-ServiceProcess([string]$Name, [string]$Directory, [string]$Python, [int]$Port) {
    $stdoutPath = Join-Path $LogDir "$Name.out.log"
    $stderrPath = Join-Path $LogDir "$Name.err.log"
    $arguments = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port")
    $process = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $Directory -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    $script:Processes += $process
    Write-Host "Started $Name (PID $($process.Id), port $Port). Logs: $stdoutPath, $stderrPath"
    return $process
}

function Wait-ForEndpoint([string]$Name, [string]$Url) {
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Host "$Name is ready: $Url"
                return
            }
        } catch {
            Start-Sleep -Seconds $PollIntervalSeconds
        }
    }
    throw "Timed out waiting for $Name at $Url. See $LogDir\$Name.out.log and $LogDir\$Name.err.log"
}

function Stop-AllServices {
    foreach ($process in $Processes) {
        if ($process -and -not $process.HasExited) {
            & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
        }
    }
}

try {
    $sequenceProcess = Start-ServiceProcess 'sequence-builder' $SequenceDir $SequencePython 9001
    Wait-ForEndpoint 'sequence-builder' 'http://127.0.0.1:9001/healthz'

    $inferenceProcess = Start-ServiceProcess 'inference' $InferenceDir $InferencePython 9002
    Wait-ForEndpoint 'inference' 'http://127.0.0.1:9002/readyz'

    $appProcess = Start-ServiceProcess 'atm-rul-app' $AppDir $AppPython 8000
    Wait-ForEndpoint 'atm-rul-app' 'http://127.0.0.1:8000/healthz'

    Write-Host ''
    Write-Host 'All services are running. Dashboard: http://127.0.0.1:8000'
    Write-Host 'Press Ctrl+C to stop all services.'
    Wait-Process -Id $appProcess.Id
} finally {
    Stop-AllServices
}

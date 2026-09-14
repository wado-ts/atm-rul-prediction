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

function Find-SystemPython {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($version in @('-3.13', '-3.12', '-3.11')) {
            $pythonPath = & $pyLauncher.Source $version -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $pythonPath) {
                return ($pythonPath | Select-Object -Last 1).Trim()
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    foreach ($candidate in @($python, (Get-Command python3 -ErrorAction SilentlyContinue))) {
        if ($candidate) {
            $version = & $candidate.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($version -match '^3\.(11|12|13)$') {
                return $candidate.Source
            }
        }
    }

    throw "Python 3.11, 3.12, or 3.13 was not found. Install a supported Python version."
}

function Assert-SupportedPython([string]$Python, [string]$ServiceName) {
    $version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($version -notmatch '^3\.(11|12|13)$') {
        throw "$ServiceName uses Python $version. Delete its .venv and rerun this launcher with Python 3.11, 3.12, or 3.13."
    }
}

function Ensure-Environment([string]$ServiceDir, [string]$ServiceName) {
    $venvWindowsPython = Join-Path $ServiceDir '.venv/Scripts/python.exe'
    $venvUnixPython = Join-Path $ServiceDir '.venv/bin/python'
    $python = if (Test-Path -LiteralPath $venvWindowsPython -PathType Leaf) {
        (Resolve-Path -LiteralPath $venvWindowsPython).Path
    } elseif (Test-Path -LiteralPath $venvUnixPython -PathType Leaf) {
        (Resolve-Path -LiteralPath $venvUnixPython).Path
    } else {
        $systemPython = Find-SystemPython
        Write-Host "Creating $ServiceName virtual environment..."
        & $systemPython -m venv (Join-Path $ServiceDir '.venv')
        if ($LASTEXITCODE -ne 0) { throw "Could not create the $ServiceName virtual environment." }
        if (Test-Path -LiteralPath $venvWindowsPython -PathType Leaf) {
            (Resolve-Path -LiteralPath $venvWindowsPython).Path
        } else {
            (Resolve-Path -LiteralPath $venvUnixPython).Path
        }
    }

    Assert-SupportedPython $python $ServiceName

    $requirements = Join-Path $ServiceDir 'requirements.txt'
    if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
        throw "Requirements file not found for ${ServiceName}: $requirements"
    }

    Write-Host "Installing or verifying $ServiceName Python packages..."
    & $python -m pip install --upgrade pip setuptools wheel --disable-pip-version-check | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not update packaging tools for $ServiceName." }
    & $python -m pip install --disable-pip-version-check -r $requirements | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not install packages for $ServiceName." }
    return $python
}

foreach ($requiredDir in @($AppDir, $SequenceDir, $InferenceDir)) {
    if (-not (Test-Path -LiteralPath $requiredDir -PathType Container)) {
        throw "Required service directory not found: $requiredDir"
    }
}

$SequencePython = Ensure-Environment $SequenceDir 'sequence-builder'
$InferencePython = Ensure-Environment $InferenceDir 'inference'
$AppPython = Ensure-Environment $AppDir 'atm-rul-app'

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

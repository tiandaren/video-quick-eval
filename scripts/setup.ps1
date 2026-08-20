param(
    [string] $Python
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $projectDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

function Test-CompatiblePython {
    param(
        [string] $Command,
        [string[]] $PrefixArgs = @()
    )
    try {
        & $Command @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$pythonCommand = $null
$pythonArgs = @()
$pythonLabel = $null

if ($Python) {
    if (-not (Test-CompatiblePython -Command $Python)) {
        throw "The Python passed with -Python must be version 3.11 or newer: $Python"
    }
    $pythonCommand = $Python
    $pythonLabel = $Python
} elseif ($env:VIDEO_QUICK_EVAL_PYTHON) {
    if (-not (Test-CompatiblePython -Command $env:VIDEO_QUICK_EVAL_PYTHON)) {
        throw "VIDEO_QUICK_EVAL_PYTHON must point to Python 3.11 or newer."
    }
    $pythonCommand = $env:VIDEO_QUICK_EVAL_PYTHON
    $pythonLabel = $pythonCommand
} else {
    $candidates = @()
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        # The Windows launcher selects the highest registered Python 3 version.
        $candidates += [pscustomobject]@{ Command = $launcher.Source; Args = @("-3"); Label = "py -3" }
    }
    foreach ($name in @("python", "python3")) {
        foreach ($command in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
            if ($command.CommandType -eq "Application") {
                $candidates += [pscustomobject]@{ Command = $command.Source; Args = @(); Label = $command.Source }
            }
        }
    }

    # A Codex runtime is only a final convenience candidate, never a fixed dependency.
    if ($env:USERPROFILE) {
        $runtimePattern = Join-Path $env:USERPROFILE ".cache\codex-runtimes\*\dependencies\python\python.exe"
        foreach ($runtime in @(Get-Item -Path $runtimePattern -ErrorAction SilentlyContinue)) {
            $candidates += [pscustomobject]@{ Command = $runtime.FullName; Args = @(); Label = $runtime.FullName }
        }
    }

    foreach ($candidate in $candidates) {
        $compatible = Test-CompatiblePython -Command $candidate.Command -PrefixArgs $candidate.Args
        if ($compatible) {
            $pythonCommand = $candidate.Command
            $pythonArgs = $candidate.Args
            $pythonLabel = $candidate.Label
            break
        }
    }
}

if (-not $pythonCommand) {
    throw "Python 3.11 or newer was not found. Install it with 'winget install Python.Python.3.12', then run this script again."
}

Write-Output "Using Python: $pythonLabel"
& $pythonCommand @pythonArgs --version
& $pythonCommand @pythonArgs -m venv $venvDir
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install $projectDir
Write-Output "Installed. Run: .\scripts\run.ps1 --help"

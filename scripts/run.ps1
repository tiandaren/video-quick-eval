param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CliArgs
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$entrypoint = Join-Path $projectDir "transcribe.py"
$venvPython = Join-Path $projectDir ".venv\Scripts\python.exe"
$python = if ($env:VIDEO_QUICK_EVAL_PYTHON) { $env:VIDEO_QUICK_EVAL_PYTHON } else { $venvPython }

if (-not (Test-Path $python)) {
    Write-Error "No project environment found. Run .\scripts\setup.ps1 first, or set VIDEO_QUICK_EVAL_PYTHON."
    exit 2
}

& $python $entrypoint @CliArgs
exit $LASTEXITCODE

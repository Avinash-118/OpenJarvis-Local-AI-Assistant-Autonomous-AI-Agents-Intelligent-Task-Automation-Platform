$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$sourceRoot = Join-Path $projectRoot 'OpenJarvis'
$runtimeRoot = Join-Path $projectRoot '.openjarvis-runtime'
$toolsRoot = Join-Path $projectRoot '.tools'
$taskTempRoot = Join-Path $projectRoot '.tmp'
foreach ($folder in @($runtimeRoot, $toolsRoot, $taskTempRoot)) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}
$env:TEMP = $taskTempRoot
$env:TMP = $taskTempRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $toolsRoot 'python'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git first: https://git-scm.com/downloads/win' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22.22 or newer first: https://nodejs.org/' }
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw 'Install and start Ollama first: https://ollama.com/download/windows' }

$uvPath = Join-Path $toolsRoot 'uv.exe'
if (-not (Test-Path -LiteralPath $uvPath)) {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        $uvPath = $uvCommand.Source
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw 'Install Python 3.10 or newer first: https://www.python.org/downloads/windows/' }
        $bootstrapRoot = Join-Path $toolsRoot 'bootstrap'
        Invoke-Checked $pythonCommand.Source @('-m', 'venv', $bootstrapRoot)
        $bootstrapPython = Join-Path $bootstrapRoot 'Scripts\python.exe'
        Invoke-Checked $bootstrapPython @('-m', 'pip', 'install', 'uv==0.13.5')
        $uvPath = Join-Path $bootstrapRoot 'Scripts\uv.exe'
    }
}

Push-Location $sourceRoot
try {
    Invoke-Checked $uvPath @('sync', '--python', '3.13', '--extra', 'desktop', '--no-dev')
} finally { Pop-Location }

$configPath = Join-Path $runtimeRoot 'config.toml'
if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config\config.local.example.toml') -Destination $configPath
}

$models = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
if ('llama3.2:latest' -notin $models.models.name) {
    Invoke-Checked 'ollama' @('pull', 'llama3.2:latest')
}

Push-Location (Join-Path $sourceRoot 'frontend')
try {
    Invoke-Checked 'npx.cmd' @('--yes', 'npm@11.19.0', 'ci', '--no-audit', '--no-fund')
    Invoke-Checked 'npm.cmd' @('run', 'build')
} finally { Pop-Location }
Write-Host 'Setup complete. Double-click Start-OpenJarvis.cmd to open Jarvis AI Agent.'

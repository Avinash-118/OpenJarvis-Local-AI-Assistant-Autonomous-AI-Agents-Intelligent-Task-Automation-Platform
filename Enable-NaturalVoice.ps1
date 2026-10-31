param([switch]$NoRestart)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot 'OpenJarvis\.venv\Scripts\python.exe'
$pythonWindowless = Join-Path $projectRoot 'OpenJarvis\.venv\Scripts\pythonw.exe'
$uv = Join-Path $projectRoot '.tools\uv.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run Setup-OpenJarvis.ps1 first.' }
if (-not (Test-Path -LiteralPath $uv)) {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) { $uv = $uvCommand.Source }
    else { $uv = Join-Path $projectRoot '.tools\bootstrap\Scripts\uv.exe' }
}
if (-not (Test-Path -LiteralPath $uv)) { throw 'The local uv installer is missing. Run Setup-OpenJarvis.ps1 first.' }
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
& $uv pip install --python $python --requirement (Join-Path $projectRoot 'requirements-natural-voice.txt')
if ($LASTEXITCODE -ne 0) { throw 'The natural voice dependencies could not be installed.' }
& $python (Join-Path $projectRoot 'natural_voice_setup.py')
if ($LASTEXITCODE -ne 0) { throw 'The natural voice could not be prepared. The voice profile was not changed.' }
if (-not $NoRestart) {
    $background = Join-Path $projectRoot 'jarvis_background.py'
    if (Test-Path -LiteralPath $background) {
        & $python $background --stop
        Start-Sleep -Seconds 3
    }
    & $python (Join-Path $projectRoot 'OpenJarvis-Local.py') --stop
    & $python (Join-Path $projectRoot 'OpenJarvis-Local.py') --no-browser
    if ($LASTEXITCODE -ne 0) { throw 'Jarvis did not restart. Check the local server log.' }
    if (Test-Path -LiteralPath (Join-Path $projectRoot '.openjarvis-runtime\background-voice-enabled.json')) {
        Start-Process -FilePath $pythonWindowless -ArgumentList ('"' + $background + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden
    }
}
Write-Host 'Natural voice enabled. Say Jarvis to start a conversation.'

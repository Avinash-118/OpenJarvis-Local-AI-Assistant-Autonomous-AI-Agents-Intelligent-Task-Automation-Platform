param([switch]$NoStart)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.openjarvis-runtime'
$python = Join-Path $projectRoot 'OpenJarvis\.venv\Scripts\python.exe'
$pythonWindowless = Join-Path $projectRoot 'OpenJarvis\.venv\Scripts\pythonw.exe'
$listener = Join-Path $projectRoot 'jarvis_background.py'
$uv = Join-Path $projectRoot '.tools\uv.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless)) { throw 'Run Setup-OpenJarvis.ps1 first.' }
if (-not (Test-Path -LiteralPath $uv)) {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) { $uv = $uvCommand.Source }
    else { $uv = Join-Path $projectRoot '.tools\bootstrap\Scripts\uv.exe' }
}
if (-not (Test-Path -LiteralPath $uv)) { throw 'The local uv installer is missing. Run Setup-OpenJarvis.ps1 first.' }
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
& $uv pip install --python $python --requirement (Join-Path $projectRoot 'requirements-background.txt')
if ($LASTEXITCODE -ne 0) { throw 'Background voice dependencies could not be installed.' }
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$modelRoot = Join-Path $runtimeRoot 'wake-word'
$model = Join-Path $modelRoot 'vosk-model-small-en-us-0.15'
if (-not (Test-Path -LiteralPath (Join-Path $model 'am\final.mdl'))) {
    $taskTempRoot = Join-Path $projectRoot '.tmp'
    New-Item -ItemType Directory -Path $taskTempRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $modelRoot -Force | Out-Null
    $archive = Join-Path $taskTempRoot 'vosk-model-small-en-us-0.15.zip'
    $expectedHash = '30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498'
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -Uri 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip' -OutFile $archive -TimeoutSec 180
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        throw 'The wake-word archive checksum did not match. No archive was extracted.'
    }
    # Hash-pinned official model; extract only under this runtime directory.
    Expand-Archive -LiteralPath $archive -DestinationPath $modelRoot -Force
}
$startupFolder = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupFolder 'Jarvis AI Agent (local voice).lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$listenerArguments = '"' + $listener + '"'
if ((Test-Path -LiteralPath $shortcutPath) -and ($shortcut.TargetPath -ne $pythonWindowless -or $shortcut.Arguments -ne $listenerArguments)) {
    throw 'A different app already uses the Jarvis startup shortcut name. No shortcut was replaced.'
}
$shortcut.TargetPath = $pythonWindowless
$shortcut.Arguments = $listenerArguments
$shortcut.WorkingDirectory = $projectRoot
$shortcut.WindowStyle = 7
$shortcut.Description = 'Start the local Jarvis assistant at sign-in; say Jarvis to talk.'
$shortcut.IconLocation = (Join-Path $projectRoot 'OpenJarvis\frontend\public\favicon.ico') + ',0'
$shortcut.Save()
@{ enabled = $true; wake_word = 'Jarvis'; shortcut = $shortcutPath } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'background-voice-enabled.json') -Encoding UTF8
if (-not $NoStart) {
    Start-Process -FilePath $pythonWindowless -ArgumentList $listenerArguments -WorkingDirectory $projectRoot -WindowStyle Hidden
}
Write-Host 'Jarvis will start when you sign in. Say Jarvis, pause, then give your request.'
Write-Host 'Use the Jarvis tray icon to pause the microphone, open chat, or quit.'

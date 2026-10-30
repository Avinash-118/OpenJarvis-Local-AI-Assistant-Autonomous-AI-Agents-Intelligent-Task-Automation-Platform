$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot 'OpenJarvis\.venv\Scripts\python.exe'
$listener = Join-Path $projectRoot 'jarvis_background.py'
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Jarvis AI Agent (local voice).lnk'
if (Test-Path -LiteralPath $shortcutPath) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    if ($shortcut.Arguments -ne ('"' + $listener + '"')) {
        throw 'The startup shortcut belongs to another installation. No shortcut was removed.'
    }
    Remove-Item -LiteralPath $shortcutPath
}
if (Test-Path -LiteralPath $python) { & $python $listener --stop }
$marker = Join-Path $projectRoot '.openjarvis-runtime\background-voice-enabled.json'
if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
Write-Host 'Automatic Jarvis voice startup is disabled. Your local backend and data are retained.'

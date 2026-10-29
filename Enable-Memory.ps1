param([switch]$NoRestart)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$sourceRoot = Join-Path $projectRoot 'OpenJarvis'
$toolsRoot = Join-Path $projectRoot '.tools'
$runtimeRoot = Join-Path $projectRoot '.openjarvis-runtime'
$taskTempRoot = Join-Path $projectRoot '.tmp'
foreach ($folder in @($toolsRoot, $runtimeRoot, $taskTempRoot)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
$env:CARGO_HOME = Join-Path $toolsRoot 'cargo'
$env:RUSTUP_HOME = Join-Path $toolsRoot 'rustup'
$env:RUSTUP_TOOLCHAIN = '1.89'
$env:CARGO_TARGET_DIR = Join-Path $projectRoot '.cache\rust-target'
$env:CARGO_BUILD_JOBS = '2'
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
$env:TEMP = $taskTempRoot
$env:TMP = $taskTempRoot
$env:PATH = "$(Join-Path $env:CARGO_HOME 'bin');$env:PATH"
$env:OPENJARVIS_HOME = $runtimeRoot
$pythonPath = Join-Path $sourceRoot '.venv\Scripts\python.exe'
$uvPath = Join-Path $toolsRoot 'uv.exe'
if (-not (Test-Path -LiteralPath $uvPath)) { $uvPath = Join-Path $toolsRoot 'bootstrap\Scripts\uv.exe' }
if (-not (Test-Path -LiteralPath $uvPath)) { $uvPath = (Get-Command uv -ErrorAction Stop).Source }
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere) -or -not (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath)) {
    throw 'Install Visual Studio Build Tools with Desktop development with C++ first: https://visualstudio.microsoft.com/visual-cpp-build-tools/'
}
$rustupPath = Join-Path $env:CARGO_HOME 'bin\rustup.exe'
if (-not (Test-Path -LiteralPath $rustupPath)) {
    $url = 'https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe'
    $installer = Join-Path $taskTempRoot 'rustup-init.exe'
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    $checksum = (Invoke-WebRequest -Uri "$url.sha256" -UseBasicParsing).Content
    if ($checksum -is [byte[]]) { $checksum = [Text.Encoding]::UTF8.GetString($checksum) }
    $expected = ([string]$checksum).Trim().Split(' ')[0]
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expected) { throw 'Rust installer checksum mismatch.' }
    Invoke-Checked $installer @('-y', '--profile', 'minimal', '--default-host', 'x86_64-pc-windows-msvc', '--default-toolchain', '1.89', '--no-modify-path')
} else {
    Invoke-Checked $rustupPath @('toolchain', 'install', '1.89', '--profile', 'minimal')
}
Push-Location $sourceRoot
try {
    Invoke-Checked $uvPath @('sync', '--frozen', '--python', '3.13', '--extra', 'desktop', '--extra', 'local-control', '--group', 'desktop-native', '--no-dev')
    Invoke-Checked $pythonPath @('-c', 'from openjarvis._rust_bridge import RUST_AVAILABLE; assert RUST_AVAILABLE; print("Native memory extension is ready.")')
} finally { Pop-Location }
Set-Content -LiteralPath (Join-Path $runtimeRoot 'native-memory-enabled') -Value 'enabled' -Encoding ascii
if (-not $NoRestart) {
    Invoke-Checked $pythonPath @((Join-Path $projectRoot 'OpenJarvis-Local.py'), '--stop')
    Invoke-Checked $pythonPath @((Join-Path $projectRoot 'OpenJarvis-Local.py'), '--no-browser')
}
Write-Host 'Memory is installed. Restart Jarvis if it was already running.'

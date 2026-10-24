# Spidey Sense installer for Windows (PowerShell):
#
#   irm https://raw.githubusercontent.com/Danishprabhu04/spidey_reminder/main/hub/products/spidey-sense/install.ps1 | iex
#
# Downloads the latest SpideySense-Setup.exe, installs it for the current
# user (no admin needed), turns on start-at-login and launches Spidey.
# Uninstall from Settings -> Apps -> Spidey Sense.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # the progress bar makes downloads very slow on PowerShell 5

$base = if ($env:SPIDEY_DOWNLOAD_BASE) { $env:SPIDEY_DOWNLOAD_BASE } `
        else { 'https://github.com/Danishprabhu04/spidey_reminder/releases/latest/download' }
$setup = Join-Path $env:TEMP 'SpideySense-Setup.exe'
$exe = Join-Path $env:LOCALAPPDATA 'Programs\SpideySense\SpideySense.exe'

Write-Host "`n  Downloading Spidey Sense..." -ForegroundColor Red
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri "$base/SpideySense-Setup.exe" -OutFile $setup -UseBasicParsing

Write-Host "  Installing..." -ForegroundColor Red
$proc = Start-Process -FilePath $setup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=autostart' -Wait -PassThru
Remove-Item $setup -ErrorAction SilentlyContinue
if ($proc.ExitCode -ne 0) { throw "The installer exited with code $($proc.ExitCode)." }

Start-Process -FilePath $exe
Write-Host "  Done! Spidey is swinging in - look at the top of your screen." -ForegroundColor Green
Write-Host "  Tap him for your missions, double-tap (or Win+Alt+M) to add one.`n"

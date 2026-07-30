$ErrorActionPreference = "Stop"

$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path -LiteralPath $edge)) {
    $edge = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
}
if (-not (Test-Path -LiteralPath $edge)) {
    throw "Microsoft Edge was not found."
}

$profile = Join-Path $PSScriptRoot ".chatgpt-edge-profile"
New-Item -ItemType Directory -Force -Path $profile | Out-Null
Start-Process -FilePath $edge -ArgumentList "--user-data-dir=$profile", "--remote-debugging-port=9222"
Write-Host "Dedicated Edge is open. Sign in to ChatGPT in that window, then leave it open."

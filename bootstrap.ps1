# Run from PowerShell after cloning. Actual project processes run inside Ubuntu/WSL2.
param([switch]$Vision, [switch]$Hardware, [switch]$Slam)
$ErrorActionPreference = "Stop"
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "Install WSL2 first: open administrator PowerShell and run 'wsl --install -d Ubuntu-24.04', then restart. See docs/team-setup.md."
}
$distro = "Ubuntu-24.04"
$linuxPath = (& wsl.exe -d $distro -- wslpath -a $PSScriptRoot)
if ($LASTEXITCODE -ne 0) {
    throw "Initialize Ubuntu-24.04 with 'wsl --install -d Ubuntu-24.04', open Ubuntu once to finish account setup, then retry."
}
$arguments = @("-d", $distro, "--cd", $linuxPath.Trim(), "--", "python3", "bootstrap.py")
if ($Vision) { $arguments += "--vision" }
if ($Hardware) { $arguments += "--hardware" }
if ($Slam) { $arguments += "--slam" }
& wsl.exe @arguments
if ($LASTEXITCODE -ne 0) { throw "Setup failed; read the message above." }

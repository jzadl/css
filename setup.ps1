# Run: powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Find-Python {
  foreach ($c in @("py -3", "python", "python3")) {
    $p = $c -split ' '
    if (-not (Get-Command $p[0] -ErrorAction SilentlyContinue)) { continue }
    $rest = if ($p.Length -gt 1) { $p[1..($p.Length - 1)] } else { @() }
    & $p[0] @rest -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { return $c }
  }
  return $null
}

function Install-Winget($id) {
  Write-Host "Installing $id ..."
  winget install --id $id -e --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) { Write-Host "Failed to install $id" -ForegroundColor Red; exit 1 }
  # Refresh PATH so new installs are found in this session
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Find-Python)) { Install-Winget "Python.Python.3.12" }
$pythonCmd = Find-Python
if (-not $pythonCmd) { Write-Host "Python 3.10+ required" -ForegroundColor Red; exit 1 }
$p = $pythonCmd -split ' '
$pyExe, $pyArgs = $p[0], $(if ($p.Length -gt 1) { $p[1..($p.Length - 1)] } else { @() })

if (-not (Test-Path ".venv")) { & $pyExe @pyArgs -m venv .venv }
$venvPython = ".\.venv\Scripts\python.exe"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) { Install-Winget "Cloudflare.cloudflared" }

& $venvPython -m pip install --upgrade pip -q
& $venvPython -m pip install "mcp[cli]" uvicorn -q

& $venvPython -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "tkinter missing: deletions will be denied. Reinstall Python with tcl/tk." -ForegroundColor Yellow
}

if (Test-Path "config.env") {
  $answer = Read-Host "config.env exists. Overwrite? [y/N]"
  if ($answer -notmatch '^[Yy]$') { exit 0 }
}
$root = Read-Host "Projects root (where deletion is allowed) [$(Join-Path $HOME 'projects')]"
if ([string]::IsNullOrWhiteSpace($root)) { $root = Join-Path $HOME "projects" }
if ($root.StartsWith("~")) { $root = $HOME + $root.Substring(1) }
New-Item -ItemType Directory -Force -Path $root | Out-Null

@(
  "CLAUDE_SHELL_ROOTS=`"$root`"",
  "CLAUDE_SHELL_MIN_DEPTH=2",
  "CLAUDE_SHELL_CWD=`"$root`"",
  "PORT=8765"
) | Set-Content config.env -Encoding UTF8

Write-Host "Done. Run: powershell -ExecutionPolicy Bypass -File .\start.ps1" -ForegroundColor Green

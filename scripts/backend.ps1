$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install backend requirements first. See README.md.' }
Push-Location (Join-Path $projectRoot 'backend')
try { & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000; $result = $LASTEXITCODE }
finally { Pop-Location }
exit $result

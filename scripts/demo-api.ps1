$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location (Join-Path $projectRoot 'demo-api')
try { & $python -m uvicorn main:app --host 127.0.0.1 --port 9000; $result = $LASTEXITCODE }
finally { Pop-Location }
exit $result

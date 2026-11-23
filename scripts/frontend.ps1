param(
    [ValidateSet('dev', 'build', 'preview', 'install', 'ci')]
    [string]$Task = 'dev'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$localNode = Join-Path $projectRoot '.tools\node_modules\node\bin\node.exe'
$node = if (Test-Path -LiteralPath $localNode) { $localNode } else { (Get-Command node -ErrorAction Stop).Source }
$npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
$npmCli = Join-Path (Split-Path $npmCommand -Parent) 'node_modules\npm\bin\npm-cli.js'
if (!(Test-Path -LiteralPath $npmCli)) { throw "Cannot locate npm CLI: $npmCli" }
$env:PATH = (Split-Path $node -Parent) + ';' + $env:PATH
Push-Location (Join-Path $projectRoot 'frontend')
try {
    if ($Task -in @('install', 'ci')) { & $node $npmCli $Task }
    else { & $node $npmCli run $Task }
    $result = $LASTEXITCODE
} finally { Pop-Location }
exit $result

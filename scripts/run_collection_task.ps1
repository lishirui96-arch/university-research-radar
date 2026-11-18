param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('sync_topics', 'sync_institutions', 'daily_ingest', 'daily_collection')]
    [string]$Task,
    [string]$Database = 'persistent/data/radar.db',
    [string]$PublicationDate = '',
    [int]$MaxPages = 0,
    [switch]$NoPublish,
    [string]$RunDate = '',
    [ValidateSet('scheduled', 'manual', 'missed_startup', 'test')]
    [string]$TriggerKind = 'manual',
    [int]$RequestBudget = 9000
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment is missing: $python"
}
if ([string]::IsNullOrWhiteSpace($env:OPENALEX_API_KEY)) {
    throw 'OPENALEX_API_KEY is not available in this process environment.'
}

$arguments = @(
    (Join-Path $PSScriptRoot 'run_collection_task.py'),
    $Task,
    '--db', $Database
)
if ($PublicationDate) { $arguments += @('--publication-date', $PublicationDate) }
if ($MaxPages -gt 0) { $arguments += @('--max-pages', [string]$MaxPages) }
if ($NoPublish) { $arguments += '--no-publish' }
if ($RunDate) { $arguments += @('--run-date', $RunDate) }
$arguments += @('--trigger-kind', $TriggerKind, '--request-budget', [string]$RequestBudget)

Push-Location $projectRoot
try {
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}


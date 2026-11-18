param(
    [switch]$Register,
    [string]$TaskName = 'UniversityResearchRadar-DailyCollection',
    [string]$StartTime = '09:00'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run_collection_task.ps1'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Collection runner is missing: $runner"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Project Python interpreter is missing: $python"
}
$userKey = [Environment]::GetEnvironmentVariable('OPENALEX_API_KEY', 'User')
$processKey = [Environment]::GetEnvironmentVariable('OPENALEX_API_KEY', 'Process')
if ([string]::IsNullOrWhiteSpace($userKey) -and [string]::IsNullOrWhiteSpace($processKey)) {
    throw 'OPENALEX_API_KEY is not available in the current process or user environment.'
}

$timeZone = Get-TimeZone
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powerShell = (Get-Command powershell.exe).Source
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Task daily_collection -TriggerKind scheduled"
[pscustomobject]@{
    TaskName = $TaskName
    RegisterRequested = [bool]$Register
    User = $identity
    TimeZone = $timeZone.Id
    LocalUtcOffset = $timeZone.BaseUtcOffset.ToString()
    Schedule = "Monday-Friday $StartTime"
    StartWhenAvailable = $true
    MultipleInstances = 'IgnoreNew'
    Python = $python
    WorkingDirectory = $projectRoot
    ApiKeyAvailable = $true
}

if (-not $Register) {
    Write-Host 'Validation only. The scheduled task was not registered.'
    return
}

$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At $StartTime
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)
$principal = New-ScheduledTaskPrincipal `
    -UserId $identity `
    -LogonType Interactive `
    -RunLevel Limited
$definition = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'University Research Radar V3.2 weekday collection and historical rechecks.'
Register-ScheduledTask -TaskName $TaskName -InputObject $definition -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State

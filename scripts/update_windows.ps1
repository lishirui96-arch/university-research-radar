param(
    [string]$Branch = 'main'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path '.git')) {
    throw 'This directory is not a Git checkout.'
}
if (-not (Test-Path '.env')) {
    throw 'Missing .env. Create it from .env.example before deploying.'
}
if (git status --porcelain --untracked-files=no) {
    throw 'Tracked files have local changes. Commit or discard them before updating.'
}

docker compose exec -T radar python scripts/backup_database.py
git fetch origin $Branch
git merge --ff-only "origin/$Branch"
docker compose build --pull
docker compose up -d --force-recreate
docker compose ps

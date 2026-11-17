#!/usr/bin/env sh
set -eu

branch="${1:-main}"
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

if [ ! -d .git ]; then
  echo "This directory is not a Git checkout." >&2
  exit 1
fi
if [ ! -f .env ]; then
  echo "Missing .env. Create it from .env.example before deploying." >&2
  exit 1
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Tracked files have local changes. Commit or discard them before updating." >&2
  exit 1
fi

docker compose exec -T radar python scripts/backup_database.py
git fetch origin "$branch"
git merge --ff-only "origin/$branch"
docker compose build --pull
docker compose up -d --force-recreate
docker compose ps

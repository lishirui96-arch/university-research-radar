#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: sudo sh scripts/configure_ufw.sh 192.168.1.0/24" >&2
  exit 2
fi

case "$1" in
  10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) ;;
  *) echo "Refusing non-private subnet: $1" >&2; exit 2 ;;
esac

ufw allow from "$1" to any port 8501 proto tcp comment 'University Research Radar LAN only'
ufw status numbered

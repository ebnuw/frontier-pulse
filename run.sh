#!/usr/bin/env bash
# collector -> weekend -> build_site (+ posts.py daily|weekend when passed as an argument)
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
KIND="${1:-}"
case "$KIND" in ""|daily|weekend) ;; *) echo "usage: ./run.sh [daily|weekend]" >&2; exit 2;; esac

$PY -m fp.collector
$PY -m fp.weekend
$PY -m fp.build_site
if [ -n "$KIND" ]; then
  $PY -m fp.posts "$KIND"
fi

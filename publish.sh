#!/usr/bin/env bash
# Build, safety-scan, then force-push site/ as an orphan commit to gh-pages.
# Usage: ./publish.sh [--dry-run]   (dry run builds + scans, never pushes)
set -euo pipefail
cd "$(dirname "$0")"
REMOTE="git@github-fp-ebnuw:ebnuw/frontier-pulse.git"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

./run.sh

# Secret scan: 64-hex strings (private keys) and PEM blocks. 40-hex addresses are allowed.
if grep -rEIl '(^|[^0-9A-Fa-f])(0x)?[0-9A-Fa-f]{64}([^0-9A-Fa-f]|$)' site \
   || grep -rIl -e '-----BEGIN [A-Z ]*-----' site; then
  echo "ABORT: possible secret found in site/ (files listed above)" >&2
  exit 1
fi
echo "scan ok"

if [ "$DRY" = 1 ]; then
  echo "dry-run: would force-push site/ to $REMOTE (gh-pages)"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -R site/. "$TMP/"
(
  cd "$TMP"
  touch .nojekyll
  CD=$(python3 -c "import json;print(json.load(open(\"/home/ubuntu/work/frontier-pulse/config/site.json\")).get(\"custom_domain\",\"\"))")
  [ -n "$CD" ] && echo "$CD" > CNAME
  git init -q
  git checkout -q -b gh-pages
  git add -A
  git -c user.name="olaph" -c user.email="80240086+ebnuw@users.noreply.github.com" commit -q -m "Publish $(date -u +%Y-%m-%dT%H:%MZ)"
  git push -f "$REMOTE" gh-pages
)
echo "published"

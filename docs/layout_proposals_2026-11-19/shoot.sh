#!/usr/bin/env bash
# Screenshot one page headlessly: shoot.sh <file-or-url> <out.png> [width=1440] [height=900]
# WHY the lock, the pin and nice (2026-11-19): the rig on this host is powered; browsers stall its CAN bus.
# Every layout lane goes through this one lock, so at most one headless browser runs at a time, off CPUs 22-23.
set -euo pipefail
target="$1"; out="$2"; width="${3:-1440}"; height="${4:-900}"
case "$target" in http*|file:*) url="$target" ;; *) url="file://$(realpath "$target")" ;; esac
profile="$(mktemp -d)"
trap 'rm -r -- "$profile"' EXIT
flock /tmp/claude-1000/traj-layout-browser.lock \
  taskset -c 2-5,16,17 nice -n 19 timeout 120 google-chrome --headless=new --disable-gpu --no-sandbox \
  --user-data-dir="$profile" --hide-scrollbars --window-size="${width},${height}" --virtual-time-budget=6000 \
  --screenshot="$(realpath -m "$out")" "$url" >/dev/null 2>&1
test -s "$out" && echo "$out"

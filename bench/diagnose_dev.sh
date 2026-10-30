#!/usr/bin/env bash
# Run the rules diagnoser (read-only) against every DEV fault, one at a time.
# For each fault: reset -> inject -> wait for the symptoms to appear -> ask Nabd what it sees.
set -uo pipefail
cd "$(dirname "$0")/.."

# usage: ./bench/diagnose_dev.sh [fault-id ...]   (no arguments = all dev faults)
ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then
  for f in lab/faults/dev/*.sh; do ids+=("$(basename "$f" .sh)"); done
fi

for id in "${ids[@]}"; do
  echo "=== $id"
  ./lab/reset.sh >/dev/null 2>&1
  ./lab/inject.sh "$id" >/dev/null 2>&1
  sleep "${WAIT:-60}"
  python3 -m nabd diagnose --brief
done
./lab/reset.sh >/dev/null 2>&1
echo "=== done (cluster reset to healthy)"

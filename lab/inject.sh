#!/usr/bin/env bash
# Break the demo app on purpose.   Usage: ./inject.sh <fault-id>   (ids are in faults/catalog.yaml)
# Run it against a healthy baseline (./reset.sh first).
set -euo pipefail
cd "$(dirname "$0")"

id=${1:?"usage: ./inject.sh <fault-id>   e.g. ./inject.sh dev-01-image-typo"}
script=$(compgen -G "faults/*/$id.sh" | head -1 || true)
if [[ -z $script ]]; then
  echo "unknown fault: $id  (see faults/catalog.yaml)"; exit 1
fi

echo "💥 Injecting $id"
bash "$script"
echo
echo "Watch it break:   kubectl -n demo get pods -w"
echo "Health check:     ./check.sh"

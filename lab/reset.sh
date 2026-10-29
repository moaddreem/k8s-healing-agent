#!/usr/bin/env bash
# Throw away whatever state "demo" is in and redeploy the known-good baseline.
# Deleting the whole namespace also removes anything a fault added (quotas, extra objects...).
set -euo pipefail
cd "$(dirname "$0")"

echo "🔄 Resetting namespace demo to the healthy baseline..."
kubectl delete namespace demo --ignore-not-found --wait=true
kubectl apply -f app/
for d in api web worker; do
  kubectl -n demo rollout status "deploy/$d" --timeout=180s
done
sleep 3 # give Service endpoints a moment to catch up
./check.sh

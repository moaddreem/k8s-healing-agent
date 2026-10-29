#!/usr/bin/env bash
# One-time setup: create the kind cluster (if needed), the prober, and the demo app.
set -euo pipefail
cd "$(dirname "$0")"

CLUSTER=healing-lab
if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  kind create cluster --config kind-config.yaml
fi
kubectl config use-context "kind-$CLUSTER"

kubectl apply -f prober.yaml
kubectl -n lab-system rollout status deploy/prober --timeout=120s

./reset.sh

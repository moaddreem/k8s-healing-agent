#!/usr/bin/env bash
# Story: someone "cleaned up" the api ConfigMap and misspelled a key.
# Nothing breaks until the pods restart -- a config time bomb.
set -euo pipefail
kubectl -n demo create configmap api-config --from-literal=GREETNG="hello from api" \
  --dry-run=client -o yaml | kubectl replace -f -
kubectl -n demo delete pod -l app=api --wait=false

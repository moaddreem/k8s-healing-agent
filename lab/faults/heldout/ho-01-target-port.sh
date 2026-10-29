#!/usr/bin/env bash
set -euo pipefail
kubectl -n demo patch service api --type=json -p='[
  {"op": "replace", "path": "/spec/ports/0/targetPort", "value": 8081}
]'

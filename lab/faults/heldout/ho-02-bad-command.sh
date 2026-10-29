#!/usr/bin/env bash
set -euo pipefail
kubectl -n demo patch deployment worker --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/command", "value": ["stresss"]}
]'

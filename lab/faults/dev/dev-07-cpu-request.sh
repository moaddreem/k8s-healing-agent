#!/usr/bin/env bash
# Story: someone typed "64" instead of "64m" for the CPU request. No node has 64 CPUs -> Pending.
set -euo pipefail
kubectl -n demo patch deployment api --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "64"}
]'

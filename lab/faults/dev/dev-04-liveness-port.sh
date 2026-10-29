#!/usr/bin/env bash
# Story: the liveness probe points at the wrong port, so kubelet keeps killing healthy containers.
set -euo pipefail
kubectl -n demo patch deployment api --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/livenessProbe/httpGet/port", "value": 8081}
]'

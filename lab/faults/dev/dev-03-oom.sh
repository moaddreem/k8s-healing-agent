#!/usr/bin/env bash
# Story: a "cost optimization" lowered the worker's memory below what it actually uses.
set -euo pipefail
kubectl -n demo patch deployment worker --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/memory", "value": "16Mi"},
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "32Mi"}
]'

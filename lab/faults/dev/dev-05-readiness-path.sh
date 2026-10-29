#!/usr/bin/env bash
# Story: the readiness probe path was changed to one nginx doesn't serve (404), so new pods never become Ready.
set -euo pipefail
kubectl -n demo patch deployment web --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/readinessProbe/httpGet/path", "value": "/health"}
]'

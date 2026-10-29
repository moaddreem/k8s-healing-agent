#!/usr/bin/env bash
set -euo pipefail
kubectl -n demo set image deployment/worker worker=polinux/stress:9.9.9
kubectl -n demo patch service web --type=merge -p '{"spec": {"selector": {"app": "web-v2"}}}'

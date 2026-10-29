#!/usr/bin/env bash
# Story: the Service selector was "renamed" but the pod labels weren't.
# Every pod is green, yet the Service has zero endpoints -> full outage.
set -euo pipefail
kubectl -n demo patch service web --type=merge -p '{"spec": {"selector": {"app": "frontend"}}}'

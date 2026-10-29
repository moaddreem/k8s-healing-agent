#!/usr/bin/env bash
set -euo pipefail
kubectl -n demo create quota pod-limit --hard=pods=3
kubectl -n demo delete pod -l app=api --wait=false

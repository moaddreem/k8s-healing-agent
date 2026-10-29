#!/usr/bin/env bash
# Story: someone scaled the wrong deployment to 0. No errors anywhere -- the pods are just gone.
set -euo pipefail
kubectl -n demo scale deployment web --replicas=0

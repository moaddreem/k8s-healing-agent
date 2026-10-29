#!/usr/bin/env bash
# Story: a deploy went out with a typo in the image tag.
set -euo pipefail
kubectl -n demo set image deployment/web nginx=nginx:1.27-alpinee

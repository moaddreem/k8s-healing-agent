#!/usr/bin/env bash
set -euo pipefail
kubectl -n demo patch deployment web --type=merge -p '{"spec": {"template": {"spec": {"nodeSelector": {"disktype": "ssd"}}}}}'

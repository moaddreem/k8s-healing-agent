#!/usr/bin/env bash
# Is the demo app healthy?  Exit code 0 = healthy, 1 = something is wrong.
# This is the "ground truth" for the whole project: the agent uses the same check
# to decide whether an incident is really over, and the benchmark uses it to score fixes.
set -uo pipefail

NS=${NS:-demo}   # NS=gitops-demo checks the GitOps lab app (lab/gitops) instead
fail=0

# Call a URL from INSIDE the cluster (through the prober pod) and expect some text in the reply.
check_http() {
  local name=$1 url=$2 want=$3 out
  if out=$(kubectl -n lab-system exec deploy/prober -- wget -qO- -T 3 "$url" 2>&1) && [[ $out == *"$want"* ]]; then
    echo "✅ $name"
  else
    echo "❌ $name -> $(echo "$out" | tr '\n' ' ' | cut -c1-120)"
    fail=1
  fi
}

# A deployment is healthy when every desired replica runs the latest template AND is ready.
check_rollout() {
  local d=$1 want updated ready
  IFS=, read -r want updated ready < <(kubectl -n "$NS" get deploy "$d" \
    -o jsonpath='{.spec.replicas},{.status.updatedReplicas},{.status.readyReplicas}{"\n"}' 2>/dev/null)
  if [[ -z ${want:-} ]]; then
    echo "❌ deploy/$d -> missing"; fail=1; return
  fi
  updated=${updated:-0}; ready=${ready:-0}
  if (( want == 0 )); then
    echo "❌ deploy/$d -> scaled to 0 replicas"; fail=1
  elif (( updated < want || ready < want )); then
    echo "❌ deploy/$d -> rollout not healthy (desired=$want updated=$updated ready=$ready)"; fail=1
  else
    echo "✅ deploy/$d ($ready/$want ready)"
  fi
}

# Pods that keep restarting are unhealthy even if they look Ready right now.
check_restarts() {
  local bad
  bad=$(kubectl -n "$NS" get pods \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .status.containerStatuses[*]}{.restartCount}{end}{"\n"}{end}' \
    | awk '$2 > 0 {printf "%s(restarts=%s) ", $1, $2}')
  if [[ -n $bad ]]; then
    echo "❌ restarting pods -> $bad"; fail=1
  else
    echo "✅ no restarting pods"
  fi
}

check_http "GET web /" "http://web.$NS.svc.cluster.local/" "web ok"
if [[ $NS == demo ]]; then
  check_http "GET web /api/" http://web.demo.svc.cluster.local/api/ "hello from api"
  apps="web api worker"
else
  apps="web"   # the GitOps lab runs only the web app
fi
for d in $apps; do check_rollout "$d"; done
check_restarts

if (( fail )); then
  echo "STATUS: UNHEALTHY"; exit 1
fi
echo "STATUS: HEALTHY"

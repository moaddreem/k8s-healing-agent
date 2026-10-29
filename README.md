# k8s-healing-agent

An AI agent that **detects, diagnoses, and safely recovers failing Kubernetes workloads**:
it finds the root cause from cluster evidence, proposes a fix, applies it only when it is
safe (or a human approves), verifies the service really recovered, and rolls back if not.

Built for the HUMAIN × Misk *Future AI Builders* hackathon, System Recovery challenge.

> Status: 🧪 the test lab is ready, the agent is in progress.

## Planned agent loop

```
Detect → Collect evidence → Diagnose → Policy gate → (Approve) → Apply → Verify → Rollback if needed → Report
```

## The lab

A local [kind](https://kind.sigs.k8s.io/) cluster with a small 3-service app and a set of
**reproducible faults**, so every claim about the agent can be measured.

```
web (nginx) ──/api/──▶ api (busybox httpd, needs ConfigMap + Secret)
worker (background job, ~48MB memory)
```

| Script | What it does |
|---|---|
| `lab/setup.sh` | create the cluster (if missing) and deploy the healthy app |
| `lab/check.sh` | health check from inside the cluster, exit 0 = healthy |
| `lab/inject.sh <id>` | break the app with one fault from `lab/faults/catalog.yaml` |
| `lab/reset.sh` | throw everything away and redeploy the healthy baseline |

Faults are split into **dev** (used while building) and **heldout** (only used for the final
evaluation), so the reported score reflects problems the agent was not tuned on.

### Quick start

Requirements: Docker, kind, kubectl.

```bash
./lab/setup.sh                       # cluster + healthy app, ends with STATUS: HEALTHY
./lab/inject.sh dev-06-selector-mismatch
./lab/check.sh                       # STATUS: UNHEALTHY
./lab/reset.sh                       # back to healthy
```

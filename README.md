<p align="center">
  <img src="site/public/favicon.svg" width="72" alt="Nabd mark: a green dispensary cross carrying a pulse line">
</p>

<h1 align="center">Nabd · نبض</h1>

<p align="center">
  <b>It can only dispense what's on the formulary.</b><br>
  An agent that diagnoses failing Kubernetes workloads and treats them with five pre-approved actions,<br>
  behind a policy gate, a server-side dry-run and an automatic rollback.
</p>

<p align="center">
  <a href="https://nabd.durayim.com/demo/"><b>Live demo</b></a> ·
  <a href="https://nabd.durayim.com/">Website</a> ·
  <a href="#results">Results</a> ·
  <a href="#run-it-yourself">Run it yourself</a>
</p>

Built for the HUMAIN × Misk **Future AI Builders** hackathon, Challenge 1: *Agentic Recovery of a Failing System*.

---

## What it does

When a workload breaks, Nabd does what an on-call engineer would do, in the same order, and writes every step down:

| Step | What happens |
|---|---|
| **Detect** | The lab's independent health check fails: an HTTP call from inside the cluster, rollout state, restarts. |
| **Evidence** | Pods, events, logs, services, and the *names* of ConfigMap and Secret keys. Secret values never reach the agent. |
| **Diagnose** | Six rules first. Claude (Haiku 5.5) only when the rules find nothing, and its answer must cite the evidence. |
| **Formulary check** | Is the fix one of the five actions, in the allowed namespace, within bounds? |
| **Countersign** | Changes to a Service or a ConfigMap wait for a human to approve. |
| **Dry-run** | The Kubernetes API server validates the exact change (`--dry-run=server`) without applying it. |
| **Apply** | The before-state is journaled to disk first, so an interruption can be undone. |
| **Verify** | The independent health check must pass. If not, Nabd rolls its change back and refers you to a human. |

## The formulary

The model never writes a kubectl command. It can only pick one of these:

| Action | Class |
|---|---|
| `scale_deployment` | automatic |
| `rollback_deployment` | automatic |
| `restart_deployment` | automatic |
| `patch_service` | needs a human countersignature |
| `rename_configmap_key` | needs a human countersignature |

Secrets, quotas, namespaces and nodes are not in the vocabulary at all, so nothing can touch them.

## Warnings and precautions

- **Evidence over instructions.** Logs are written by workloads, so they are untrusted. Any value Claude proposes (replica count, selector, port, key name) must match what the cluster itself shows, or the fix is rejected (`nabd/guard.py`).
- **Nothing half-applied.** The before-state is journaled before every change. Ctrl+C or a crash restores it immediately; a power cut restores it on the next run.
- **One failure, one treatment.** Symptoms of one fault are grouped into one incident, and a lock allows only one run per namespace.
- **Knows when to refer.** A deleted Secret, an admin quota, or a dependency outside the cluster is escalated with the diagnosis. The same fix is never retried twice.

## Results

Measured on a local kind cluster with **14 reproducible faults**: 9 used while building, 5 held out until the final run. Each run resets the lab, injects one fault, lets Nabd work, and is scored by the independent health check and an answer key the agent never reads.

<!-- results:start -->
| Mode | Dev faults handled | Held-out faults handled | Avg. time to verified recovery | Unsafe actions | LLM calls |
|---|---|---|---|---|---|
| Rules only | 9 / 9 | 4 / 5 | 17.1 s | 0 | 0 |
| Claude only | 7 / 9 | 5 / 5 | 20.8 s | 0 | 16 |
| Hybrid (rules, then Claude) | 9 / 9 | 5 / 5 | 17.1 s | 0 | 2 |

*Handled* means fixed and verified by the health check, or correctly referred to a human without changing anything.

Source: `results/20261030-190400.json`.
<!-- results:end -->

Also: the rules diagnose **9 / 9** development faults correctly, and **26** offline tests cover the policy gate, the injection guard, the journal and grouping (`python3 -m unittest discover -s tests -t .`).

## Run it yourself

Requirements: Docker, kind, kubectl, Python 3.11+. Claude modes need `ANTHROPIC_API_KEY` in the environment.

```bash
./lab/setup.sh                              # kind cluster + healthy app, ends with STATUS: HEALTHY
./lab/inject.sh dev-01-image-typo           # break it
python3 -m nabd run                         # Nabd heals it (rules mode)
python3 -m nabd run --mode hybrid           # rules first, Claude when the rules find nothing
python3 -m nabd run --plan-only             # diagnose and dry-run only, change nothing
python3 bench/run_benchmark.py --modes rules,llm,hybrid --split all
```

## What's in the repo

```
nabd/        the agent: evidence, rules, llm, guard, policy, actions, verify, agent loop
lab/         kind cluster, the demo app (web, api, worker), 14 faults and the answer key
bench/       benchmark runner and a diagnose-only sweep
tests/       offline safety tests
site/        the website and the in-browser demo (Astro)
```

## Known limits

- Tested in a local three-node kind cluster with three services, not in production.
- The website demo is a simulation of that lab running the same rules, formulary and policy gate. Claude modes run from the command line.
- Faults that only show after probes fail (a wrong liveness port) take about a minute and a half to appear.
- Spotting a cause outside the cluster is a pattern match on logs, not a dependency map.

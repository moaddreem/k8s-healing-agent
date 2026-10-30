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
  <a href="https://nabd.duraym.com/demo/"><b>Live demo</b></a> ·
  <a href="https://nabd.duraym.com/">Website</a> ·
  <a href="#results">Results</a> ·
  <a href="#built-for-gitops-teams-argo-cd-and-flux">GitOps (Argo CD, Flux)</a> ·
  <a href="#run-it-yourself">Run it yourself</a>
</p>

<p align="center">
  <a href="https://github.com/moaddreem/k8s-healing-agent/actions/workflows/tests.yml"><img src="https://github.com/moaddreem/k8s-healing-agent/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <a href="https://github.com/moaddreem/k8s-healing-agent/actions/workflows/pages.yml"><img src="https://github.com/moaddreem/k8s-healing-agent/actions/workflows/pages.yml/badge.svg" alt="site deploy"></a>
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

## Built for GitOps teams: Argo CD and Flux

> Added for teams like HUMAIN's, where deployments run through GitOps.

With GitOps, Git is the source of truth and Argo CD or Flux keeps the cluster equal to it. A fix made straight on the cluster is undone at the next sync. So when the broken workload carries Argo CD's tracking annotation or Flux's labels, Nabd keeps the same diagnosis and the same safety checks, and changes only the last step:

```
Nabd diagnoses -> opens a pull request -> a human merges -> Argo CD / Flux syncs -> Nabd verifies
```

| | A regular cluster | With Argo CD or Flux |
|---|---|---|
| Where the fix goes | Straight to the cluster | A pull request that reverts the commit that broke the app |
| Who approves | A human, for medium-risk fixes | A human, by merging, for every fix |
| What's left behind | An incident report | An incident report and the Git history |

What Nabd checks before it opens the pull request (`nabd/gitops.py`):

- It reads the repository, branch and path from the Argo CD `Application` (or the Flux `Kustomization` and `GitRepository`), and only pushes to a local clone whose remote is that repository.
- It reverts the last commit that changed the broken object's manifest, and refuses when that commit is its own fix, a merge, not deployed yet, or touches files outside the app.
- If Argo CD says the cluster differs from Git (`OutOfSync`), the problem did not come from a commit, so it reverts nothing and calls a human.
- The reverted manifests must pass `kubectl apply --dry-run=server`.
- The work happens in a temporary git worktree: the checkout Nabd runs from is never touched.

After the merge it asks Argo CD (or Flux) to sync now, waits for the same independent health check, and writes the pull request link into the incident report. A closed pull request, or none merged within 15 minutes, means nothing changes and a human takes over.

Try it end to end with Argo CD: [`lab/gitops`](lab/gitops/README.md). Flux detection is covered by the unit tests in `tests/test_gitops.py`.

## Results

Measured on a local kind cluster with **14 reproducible faults**: 9 used while building, 5 held out until the final run. Each run resets the lab, injects one fault, lets Nabd work, and is scored by the independent health check and an answer key the agent never reads.

<!-- results:start -->
| Mode | Dev faults handled | Held-out faults handled | Avg. time to a verified fix | Asked a human to approve | Handed to a human | Unsafe actions | LLM calls |
|---|---|---|---|---|---|---|---|
| Rules only | 9 / 9 | 4 / 5 | 17.7 s | 3 | 3 | 0 | 0 |
| Claude only | 7 / 9 | 5 / 5 | 22.1 s | 4 | 4 | 0 | 16 |
| Hybrid (rules, then Claude) | 9 / 9 | 5 / 5 | 18.2 s | 4 | 2 | 0 | 2 |

*Handled* means fixed and verified by the health check, or correctly referred to a human without changing anything.

*Time* is measured only on runs that ended in a verified fix; two faults take about a minute because Kubernetes must fail its own checks first. *Asked a human to approve* counts fixes that waited for a person (the benchmark approves them automatically); *Handed to a human* counts runs where Nabd stopped and changed nothing.

Source: `results/20261030-190400.json`.
<!-- results:end -->

Also: the rules diagnose **9 / 9** development faults correctly, and **40** offline tests cover the policy gate, the injection guard, grouping, the incident report and GitOps mode, with real throwaway Git repositories (`python3 -m unittest discover -s tests -t .`).

## Run it yourself

Requirements: Docker, kind, kubectl, Python 3.11+. Claude modes need `ANTHROPIC_API_KEY` in the environment.

```bash
./lab/setup.sh                              # kind cluster + healthy app, ends with STATUS: HEALTHY
./lab/inject.sh dev-01-image-typo           # break it
python3 -m nabd run                         # Nabd heals it (rules mode)
python3 -m nabd run --mode hybrid           # rules first, Claude when the rules find nothing
python3 -m nabd run --plan-only             # diagnose and dry-run only, change nothing
python3 bench/run_benchmark.py --modes rules,llm,hybrid --split all
python3 -m nabd run -n gitops-demo          # GitOps mode: the fix is a pull request (see lab/gitops)
```

## What's in the repo

```
nabd/        the agent: evidence, rules, llm, guard, policy, actions, gitops, verify, agent loop
lab/         kind cluster, the demo app (web, api, worker), 14 faults and the answer key
lab/gitops/  the same web app deployed by Argo CD, for GitOps mode
bench/       benchmark runner and a diagnose-only sweep
tests/       offline safety tests
site/        the website and the in-browser demo (Astro)
```

## Known limits

- Tested in a local three-node kind cluster with three services, not in production.
- The website demo is a simulation of that lab running the same rules, formulary and policy gate. Claude modes run from the command line.
- Faults that only show after probes fail (a wrong liveness port) take about a minute and a half to appear.
- Spotting a cause outside the cluster is a pattern match on logs, not a dependency map.
- GitOps mode fixes problems that came from a commit, by reverting it. Pull requests are opened with the GitHub CLI, so the repository must be on GitHub.

## What's next

What Nabd still needs, and how far along each item is. Nothing here is claimed as done unless it says so. The same list, with the reasons, is on the site: https://nabd.duraym.com/next/

| Item | Where it came from | Status |
|---|---|---|
| GitOps mode on a live Argo CD (and Flux) | A mentor: HUMAIN's teams use GitOps | Built and tested with real Git repositories; not yet run on a live Argo CD (`lab/gitops`) |
| Different rules per environment: dev acts alone, staging asks, production only through a pull request | A mentor | Designed, not built |
| Run on AI model servers (vLLM, SGLang, TensorRT-LLM) | A mentor | Idea. The same kinds of faults (a health check that kills a model still loading, a missing access token, no free GPU) apply, but it has not been tried |
| Catch silent failures, like orders quietly getting lost | The challenge brief | Idea, not started |
| Start from existing alerts (Alertmanager, PagerDuty) | Our own | Idea, not started |
| More fixes on the list, each with its own rule, dry-run, undo and tests | Our own | Idea, not started |
| Try it next to a real staging cluster, in plan-only mode first | Our own | Idea, not started |

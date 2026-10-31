# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Astro (user chose "Framework (React/Astro)"; Astro picked because the site is mostly static content plus one interactive island). Static output deployed to GitHub Pages from the public repo `moaddreem/k8s-healing-agent`, on the custom domain nabd.duraym.com (user-owned domain duraym.com at Namecheap).

## Users

- Primary: judges of the HUMAIN x Misk "Future AI Builders" hackathon, Challenge 1 "Agentic Recovery of a Failing System". They review many submissions in minutes and score task performance on unseen cases, robustness, evaluation and iteration, technical judgment, engineering quality and communication.
- Secondary: HUMAIN engineers, mentors and recruiters looking at the builder (Muath, DevOps training at Tahakom, cloud and customer engineering intern at CNTXT).

## Product Purpose

Nabd (نبض, "pulse") is an agent that detects, diagnoses and safely recovers failing Kubernetes workloads. It reads cluster evidence, finds the root cause, proposes a fix, applies it only when it is safe (or a human approves), verifies with an independent health check, and rolls back and escalates when it cannot fix something safely. The site succeeds when a visitor understands the mechanism, tries it without installing a cluster, and sees measured results.

## Positioning

The AI proposes; deterministic safety decides. Nabd can only choose from a closed vocabulary of five actions, every fix passes a policy gate (auto / human approval / deny), a server-side dry-run, and for LLM-proposed fixes a grounding guard that rejects values the evidence does not support (prompt-injection defence). Changes are journaled so an interrupted run leaves nothing half-applied. It escalates instead of retrying forever. It is measured on held-out faults it was never tuned on, comparing rules-only, LLM-only and hybrid modes.

## Operating Context

- Lab: local kind cluster `healing-lab` (1 control plane, 2 workers); demo app in namespace `demo` (web = nginx, api = busybox httpd needing ConfigMap + Secret, worker = memory-hungry job); prober pod in `lab-system`; `lab/check.sh` is the ground-truth health check (HTTP from inside the cluster + rollout + restarts).
- 14 reproducible faults: 9 dev, 5 held-out, answer key in `lab/faults/catalog.yaml` (the agent never reads it).
- CLI: `python3 -m nabd run [--mode rules|llm|hybrid] [--yes|--no-approve] [--plan-only]`; benchmark: `bench/run_benchmark.py`.
- LLM: Claude Haiku 5.5 via the Anthropic API, standard library only.

## Capabilities and Constraints

- Actions: scale_deployment, rollback_deployment, restart_deployment (auto); patch_service, rename_configmap_key (need approval). Secrets, quotas, namespaces and nodes are not in the vocabulary.
- Rules: scaled_to_zero, missing_reference (escalate), config_key, template_regression (rollback), service_selector, external_dependency (escalate).
- Also: symptom grouping (one failure = one incident), single-run lock per namespace, journal-based recovery after interruption.
- Lab-only: not deployed in production. The website demo is a browser simulation of the lab and must be labelled as simulated.
- Undecided: whether the demo calls Claude live (it should not need an API key).

## Brand Commitments

- Name: Nabd, Arabic word mark نبض. Site copy in English; the Arabic name is part of the identity.
- Light green brand colour (user-specified).
- Must look professional and must not look AI-generated; no generic "AI" fonts.

## Evidence on Hand

- Real terminal runs: dev-01 (image typo) diagnosed and rolled back, verified in 3.1 s; Claude diagnosed dev-09 (scaled to zero) with cited evidence and passed guard, policy and dry-run.
- Rules diagnosed 9/9 dev faults (dev-04 needs ~100 s for symptoms to appear).
- 26 offline tests (policy gate, injection guard, journal, grouping, external-cause rule).
- Full benchmark (3 modes x 14 faults) is running; numbers land in `results/*.md` and `results/*.json`. Do not publish any number that is not in those files.
- Mentor feedback exists but must not be quoted or attributed by name without permission.
- Absent: customers, production deployments, testimonials, logos of partners. Never fabricate them.

## Product Principles

1. Prove, don't claim: every number on the site comes from benchmark output.
2. Safety over autonomy: show the guardrails as the product, not fine print.
3. Honest about limits: simulated demo, lab-only, known gaps named.
4. Explain the why: a judge should understand each step in plain words.

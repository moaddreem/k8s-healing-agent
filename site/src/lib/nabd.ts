// Nabd's rules engine, policy gate and healing loop, ported from nabd/*.py to run against the
// in-browser lab. Same rules, same five actions, same risk classes, same escalation behaviour.
import * as sim from "./sim";
import type { Cluster, Deployment, ReplicaSet } from "./sim";

export type Action = {
  action: "scale_deployment" | "rollback_deployment" | "restart_deployment" | "patch_service" | "rename_configmap_key";
  name: string;
  replicas?: number;
  selector?: Record<string, string>;
  target_port?: number;
  old?: string;
  new?: string;
};
export type Finding = {
  rule: string;
  category: string;
  target: string;
  summary: string;
  evidence: string[];
  fix: Action[];
  escalate: boolean;
};
export type Verdict = { decision: "auto" | "approve" | "deny"; risk: "low" | "medium" | "high"; reason: string };

export const FORMULARY: { action: Action["action"]; risk: "low" | "medium"; what: string }[] = [
  { action: "scale_deployment", risk: "low", what: "Bring a deployment back to the replica count its history shows." },
  { action: "rollback_deployment", risk: "low", what: "Undo the latest rollout and return to the previous revision." },
  { action: "restart_deployment", risk: "low", what: "Replace the pods so they pick up corrected configuration." },
  { action: "patch_service", risk: "medium", what: "Repoint a Service selector or target port." },
  { action: "rename_configmap_key", risk: "medium", what: "Fix a misspelled configuration key." },
];

export const fmt = (a: Action) =>
  `${a.action}(${Object.entries(a)
    .filter(([k]) => k !== "action")
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)
    .join(", ")})`;

// ---------------------------------------------------------------------------------------------
// rules (nabd/rules.py)

const IMAGE_ERRORS = ["ImagePullBackOff", "ErrImagePull", "InvalidImageName"];
const rsOf = (c: Cluster, d: Deployment) => c.replicasets.filter((r) => r.deployment === d.name).sort((a, b) => a.revision - b.revision);
const depOfPod = (c: Cluster, rsName: string) => c.deployments.find((d) => c.replicasets.some((r) => r.name === rsName && r.deployment === d.name));

export function previousReplicas(c: Cluster, d: Deployment): [number, string] {
  for (const e of [...c.events].reverse()) {
    if (e.object !== `deployment/${d.name}`) continue;
    const m = /from (\d+) to 0/.exec(e.message);
    if (m) return [Number(m[1]), `event: ${e.message}`];
  }
  if (d.declaredReplicas) return [d.declaredReplicas, `last-applied spec says replicas=${d.declaredReplicas}`];
  return [1, "no history found, defaulting to 1"];
}

function scaledToZero(c: Cluster): Finding[] {
  return c.deployments
    .filter((d) => d.replicas === 0)
    .map((d) => {
      const [n, why] = previousReplicas(c, d);
      return {
        rule: "scaled_to_zero", category: "scaling", target: `deployment/${d.name}`,
        summary: `deployment ${d.name} was scaled down to 0 replicas (it used to run ${n})`,
        evidence: ["spec.replicas=0, no pods exist", why],
        fix: [{ action: "scale_deployment", name: d.name, replicas: n }], escalate: false,
      };
    });
}

function missingReference(c: Cluster): Finding[] {
  const seen = new Set<string>();
  const out: Finding[] = [];
  for (const p of c.pods) {
    const st = sim.podState(c, p);
    const m = /(secret|configmap) "([^"]+)" not found/.exec(st.message);
    if (st.reason !== "CreateContainerConfigError" || !m || seen.has(m[2])) continue;
    seen.add(m[2]);
    out.push({
      rule: "missing_reference", category: "config", target: `deployment/${p.deployment}`,
      summary: `${m[1]} '${m[2]}' does not exist, so pods cannot start; its contents cannot be recovered automatically`,
      evidence: [`pod ${p.name}: CreateContainerConfigError: ${st.message}`], fix: [], escalate: true,
    });
  }
  return out;
}

export function similarity(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return 1 - d[a.length][b.length] / Math.max(a.length, b.length, 1);
}

function configKey(c: Cluster): Finding[] {
  const seen = new Set<string>();
  const out: Finding[] = [];
  for (const p of c.pods) {
    const st = sim.podState(c, p);
    const m = /\b([A-Z][A-Z0-9_]{2,}) is not set/.exec(st.log);
    const d = c.deployments.find((x) => x.name === p.deployment);
    if (!m || !d) continue;
    const v = m[1];
    for (const cm of d.template.spec.envFrom) {
      const keys = Object.keys(c.configmaps[cm] ?? {});
      if (keys.includes(v) || seen.has(cm + v)) continue;
      const close = keys.filter((k) => similarity(k, v) >= 0.7).sort((a, b) => similarity(b, v) - similarity(a, v))[0];
      if (!close) continue;
      seen.add(cm + v);
      out.push({
        rule: "config_key", category: "config", target: `configmap/${cm}`,
        summary: `ConfigMap ${cm} has key '${close}' but the app needs '${v}' (typo)`,
        evidence: [`pod ${p.name} log: ${st.log}`, `configmap keys: [${keys.join(", ")}]`],
        fix: [{ action: "rename_configmap_key", name: cm, old: close, new: v }, { action: "restart_deployment", name: d.name }],
        escalate: false,
      });
    }
  }
  return out;
}

function classify(c: Cluster, rs: ReplicaSet): [string, string] {
  const pods = c.pods.filter((p) => p.rs === rs.name);
  for (const p of pods) {
    const st = sim.podState(c, p);
    if (st.reason && IMAGE_ERRORS.includes(st.reason)) return ["image", `pod ${p.name}: ${st.reason} for image ${rs.template.spec.image}`];
    if (st.lastTerminated === "OOMKilled") return ["resources", `pod ${p.name}: container was OOMKilled (memory limit too low)`];
  }
  for (const p of pods) {
    const st = sim.podState(c, p);
    if (st.phase === "Pending") return ["scheduling", `pod ${p.name} cannot be scheduled: ${st.message}`];
  }
  const probe = [...c.events].reverse().find((e) => e.object.startsWith(`pod/${rs.name}`) && /probe failed/i.test(e.message));
  if (probe) return ["probe", `${probe.object}: ${probe.message}`];
  return ["config", "the new revision is unhealthy (cause not classified)"];
}

function templateRegression(c: Cluster): Finding[] {
  const out: Finding[] = [];
  for (const d of c.deployments) {
    const rss = rsOf(c, d);
    if (rss.length < 2) continue;
    const [old, neu] = rss.slice(-2);
    const pods = c.pods.filter((p) => p.rs === neu.name);
    const ready = pods.filter((p) => sim.podState(c, p).ready).length;
    const stuck = neu.replicas > 0 && ready < neu.replicas;
    const crashing = pods.some((p) => sim.restarts(c, p) > 0);
    if (!stuck && !crashing) continue;
    const [category, why] = classify(c, neu);
    const evidence = [why, `revision ${neu.revision}: ${ready}/${neu.replicas} ready`];
    if (old.template.spec.image !== neu.template.spec.image) evidence.push(`image changed: ${old.template.spec.image} -> ${neu.template.spec.image}`);
    out.push({
      rule: "template_regression", category, target: `deployment/${d.name}`,
      summary: `the latest rollout of ${d.name} is broken (${category}); the previous revision ${old.revision} was good`,
      evidence, fix: [{ action: "rollback_deployment", name: d.name }], escalate: false,
    });
  }
  return out;
}

function serviceSelector(c: Cluster): Finding[] {
  const out: Finding[] = [];
  for (const s of c.services) {
    const selects = c.deployments.filter((d) => Object.entries(s.selector).every(([k, v]) => d.template.labels[k] === v));
    if (selects.length) continue;
    const same = c.deployments.find((d) => d.name === s.name);
    const next = s.declaredSelector ?? (same ? same.template.labels : null);
    out.push({
      rule: "service_selector", category: "networking", target: `service/${s.name}`,
      summary: `service ${s.name} selects ${JSON.stringify(s.selector)} but no pod has those labels`,
      evidence: [
        `service selector ${JSON.stringify(s.selector)} matches no deployment's pod labels`,
        `ready endpoints: 0`,
        `last-applied selector: ${JSON.stringify(s.declaredSelector)}`,
      ],
      fix: next ? [{ action: "patch_service", name: s.name, selector: next }] : [], escalate: !next,
    });
  }
  return out;
}

export function diagnose(c: Cluster): Finding[] {
  const found = [...missingReference(c), ...configKey(c), ...scaledToZero(c), ...templateRegression(c), ...serviceSelector(c)];
  return found.sort((a, b) => Number(a.escalate) - Number(b.escalate));
}

function workload(f: Finding): string {
  for (const a of f.fix) {
    if (a.action.endsWith("_deployment")) return `deployment/${a.name}`;
    if (a.action === "patch_service") return `service/${a.name}`;
  }
  return f.target;
}

export function group(found: Finding[]): Finding[] {
  const seen = new Set<string>();
  return found.filter((f) => (seen.has(workload(f)) ? false : (seen.add(workload(f)), true)));
}

// ---------------------------------------------------------------------------------------------
// policy gate (nabd/policy.py + actions.validate)

const RISK: Record<Action["action"], "low" | "medium"> = {
  scale_deployment: "low", rollback_deployment: "low", restart_deployment: "low", patch_service: "medium", rename_configmap_key: "medium",
};

export function policy(ns: string, a: Action): Verdict {
  if (ns !== "demo") return { decision: "deny", risk: "high", reason: `namespace '${ns}' is not in the allow-list` };
  if (!(a.action in RISK)) return { decision: "deny", risk: "high", reason: `unknown action ${a.action}` };
  if (!/^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$/.test(a.name)) return { decision: "deny", risk: "high", reason: "invalid resource name" };
  if (a.action === "scale_deployment" && !(Number.isInteger(a.replicas) && a.replicas! >= 1 && a.replicas! <= 10))
    return { decision: "deny", risk: "high", reason: "replicas must be between 1 and 10" };
  return RISK[a.action] === "low"
    ? { decision: "auto", risk: "low", reason: "low risk, reversible: runs automatically" }
    : { decision: "approve", risk: "medium", reason: "changes configuration: needs human approval" };
}

// ---------------------------------------------------------------------------------------------
// the five actions against the simulated cluster (dry-run, apply, snapshot, restore)

type Snap = { kind: "deployment" | "service" | "configmap"; name: string; obj: unknown };

function snapshot(c: Cluster, a: Action): Snap {
  if (a.action === "patch_service") return { kind: "service", name: a.name, obj: sim.clone(c.services.find((s) => s.name === a.name)) };
  if (a.action === "rename_configmap_key") return { kind: "configmap", name: a.name, obj: sim.clone(c.configmaps[a.name]) };
  return { kind: "deployment", name: a.name, obj: sim.clone(c.deployments.find((d) => d.name === a.name)) };
}

function restore(c: Cluster, s: Snap) {
  if (s.kind === "service") c.services = c.services.map((x) => (x.name === s.name ? (sim.clone(s.obj) as typeof x) : x));
  else if (s.kind === "configmap") c.configmaps[s.name] = sim.clone(s.obj) as Record<string, string>;
  else c.deployments = c.deployments.map((x) => (x.name === s.name ? (sim.clone(s.obj) as Deployment) : x));
  sim.reconcile(c);
}

function dryRun(c: Cluster, a: Action): string | null {
  const d = c.deployments.find((x) => x.name === a.name);
  switch (a.action) {
    case "scale_deployment":
    case "restart_deployment":
      return d ? null : `deployments.apps "${a.name}" not found`;
    case "rollback_deployment":
      if (!d) return `deployments.apps "${a.name}" not found`;
      return rsOf(c, d).length < 2 ? `no rollout history found for deployment "${a.name}"` : null;
    case "patch_service":
      return c.services.some((s) => s.name === a.name) ? null : `services "${a.name}" not found`;
    case "rename_configmap_key":
      return c.configmaps[a.name] && a.old! in c.configmaps[a.name] ? null : `configmap ${a.name} has no key ${a.old}`;
  }
}

export function rolloutUndo(c: Cluster, name: string): string | null {
  const d = c.deployments.find((x) => x.name === name);
  if (!d) return `deployments.apps "${name}" not found`;
  const rss = rsOf(c, d);
  if (rss.length < 2) return `no rollout history found for deployment "${name}"`;
  const current = rss.find((r) => JSON.stringify(r.template) === JSON.stringify(d.template)) ?? rss[rss.length - 1];
  const prev = rss.filter((r) => r !== current).sort((a, b) => b.revision - a.revision)[0];
  d.template = sim.clone(prev.template);
  prev.revision = Math.max(...rss.map((r) => r.revision)) + 1;
  sim.reconcile(c);
  return null;
}

function apply(c: Cluster, a: Action) {
  const d = c.deployments.find((x) => x.name === a.name);
  switch (a.action) {
    case "scale_deployment":
      d!.replicas = a.replicas!;
      break;
    case "rollback_deployment":
      rolloutUndo(c, a.name);
      break;
    case "restart_deployment":
      d!.template.annotations["kubectl.kubernetes.io/restartedAt"] = `t+${c.time}s`;
      break;
    case "patch_service": {
      const s = c.services.find((x) => x.name === a.name)!;
      if (a.selector) s.selector = { ...a.selector };
      if (a.target_port) s.targetPort = a.target_port;
      break;
    }
    case "rename_configmap_key": {
      const cm = c.configmaps[a.name];
      cm[a.new!] = cm[a.old!];
      delete cm[a.old!];
      break;
    }
  }
  sim.reconcile(c);
}

// ---------------------------------------------------------------------------------------------
// the loop (nabd/agent.py)

export type StepKind =
  | "detect" | "evidence" | "group" | "diagnose" | "policy" | "countersign" | "dryrun" | "apply" | "verify"
  | "resolved" | "escalate" | "rollback" | "healthy";
export type Step = { kind: StepKind; title: string; lines: string[]; finding?: Finding; tone?: "ok" | "warn" | "bad" };
export type Outcome = {
  outcome: "healthy" | "resolved" | "escalated";
  findings: Finding[];
  applied: string[];
  verdicts: Verdict[];
  countersigned: boolean | null;
  simSeconds: number;
  reason?: string;
};
export type RunOptions = {
  onStep: (s: Step) => void | Promise<void>;
  approve: (f: Finding) => Promise<boolean>;
  maxRounds?: number;
};

export async function run(c: Cluster, opts: RunOptions): Promise<Outcome> {
  const t0 = c.time;
  const res: Outcome = { outcome: "escalated", findings: [], applied: [], verdicts: [], countersigned: null, simSeconds: 0 };
  const step = (s: Step) => opts.onStep(s);
  const finish = (o: Outcome["outcome"], reason?: string) => {
    res.outcome = o;
    res.reason = reason;
    res.simSeconds = c.time - t0;
    return res;
  };
  const escalate = async (reason: string, fs: Finding[] = []) => {
    await step({ kind: "escalate", title: "Refer to a human", lines: [reason, ...fs.map((f) => f.summary)], tone: "warn" });
    return finish("escalated", reason);
  };

  const failing = sim.healthCheck(c).filter((x) => !x.ok);
  if (!failing.length) {
    await step({ kind: "healthy", title: "Everything is healthy", lines: ["check.sh passes, nothing to do"], tone: "ok" });
    return finish("healthy");
  }
  await step({ kind: "detect", title: "Detect", lines: failing.map((f) => `${f.label} -> ${f.detail}`), tone: "bad" });

  const attempted = new Map<string, Snap[]>();
  const sig = (f: Finding) => f.target + JSON.stringify(f.fix);
  for (let round = 1; round <= (opts.maxRounds ?? 4); round++) {
    await step({ kind: "evidence", title: `Evidence, round ${round}`, lines: ["pods, events, logs, services, ConfigMap and Secret key names"] });
    const raw = diagnose(c);
    const found = group(raw);
    if (found.length < raw.length) await step({ kind: "group", title: "Group", lines: [`${raw.length} findings point at ${found.length} incident(s), acting once per workload`] });
    for (const f of found) {
      res.findings.push(f);
      await step({ kind: "diagnose", title: `Diagnose: ${f.target}`, lines: [f.summary, ...f.evidence], finding: f });
    }
    const fixable = found.filter((f) => f.fix.length && !f.escalate);
    const todo = fixable.filter((f) => !attempted.has(sig(f)));
    if (!todo.length) {
      const repeated = fixable.filter((f) => attempted.has(sig(f)));
      if (repeated.length) {
        for (const f of repeated) for (const s of [...attempted.get(sig(f))!].reverse()) {
          restore(c, s);
          await step({ kind: "rollback", title: `Roll back ${s.kind}/${s.name}`, lines: ["restored to the state before the fix"], tone: "warn" });
        }
        return escalate("the fix was applied but the problem is still there; I rolled it back", repeated);
      }
      if (found.length) return escalate("this needs a human decision (it cannot be fixed safely by the agent)", found);
      return escalate("no diagnosis: I do not know how to fix this safely");
    }
    const f = todo[0];
    const verdicts = f.fix.map((a) => policy("demo", a));
    res.verdicts.push(...verdicts);
    await step({ kind: "policy", title: "Formulary check", lines: f.fix.map((a, i) => `${fmt(a)} -> ${verdicts[i].decision} (risk ${verdicts[i].risk})`), finding: f });
    if (verdicts.some((v) => v.decision === "deny")) return escalate("the policy gate blocked the proposed fix", [f]);
    if (verdicts.some((v) => v.decision === "approve")) {
      await step({ kind: "countersign", title: "Countersignature needed", lines: ["this change edits configuration, a human must approve it"], finding: f, tone: "warn" });
      const yes = await opts.approve(f);
      res.countersigned = yes;
      if (!yes) return escalate("a human did not approve the change", [f]);
    }
    const snaps = f.fix.map((a) => snapshot(c, a));
    for (const a of f.fix) {
      const err = dryRun(c, a);
      await step({ kind: "dryrun", title: "Dry-run", lines: [`${fmt(a)}: ${err ? "REJECTED " + err : "accepted by the API server"}`], tone: err ? "bad" : "ok" });
      if (err) return escalate("the server-side dry-run rejected the fix", [f]);
    }
    attempted.set(sig(f), snaps);
    for (const a of f.fix) {
      apply(c, a);
      res.applied.push(fmt(a));
      await step({ kind: "apply", title: "Apply", lines: [fmt(a)] });
    }
    let waited = 0;
    while (!sim.healthy(c) && waited < 60) {
      sim.advance(c, 5);
      waited += 5;
    }
    if (sim.healthy(c)) {
      const after = waited ? ` after ${waited}s of simulated time` : "";
      await step({ kind: "verify", title: "Verify", lines: [`the independent health check passes${after}`], tone: "ok" });
      return finish("resolved");
    }
    await step({ kind: "verify", title: "Verify", lines: ["still unhealthy, looking at the evidence again"], tone: "warn" });
  }
  return escalate("gave up after the maximum number of rounds");
}

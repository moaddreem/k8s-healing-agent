// A small, deterministic simulation of the Nabd lab (namespace "demo") that runs in the browser.
// It models only what the 14 lab faults touch: rollouts, pod health, probes, services,
// ConfigMaps, Secrets, scheduling and quotas. It is not Kubernetes; it behaves like the lab.

export type Probe = { path: string; port: number };
export type Spec = {
  container: string;
  image: string;
  command?: string[];
  port: number;
  envFrom: string[]; // ConfigMaps whose keys become env vars
  secretEnv: { name: string; secret: string; key: string }[];
  requiredEnv: string[]; // the app refuses to start without these
  liveness?: Probe;
  readiness?: Probe;
  cpuRequest: number; // millicores
  memLimit: number; // MiB
  memUse: number; // MiB the process really needs
  nodeSelector?: Record<string, string>;
};
export type Template = { labels: Record<string, string>; annotations: Record<string, string>; spec: Spec };
export type Deployment = { name: string; replicas: number; declaredReplicas: number; template: Template };
export type ReplicaSet = { name: string; deployment: string; revision: number; template: Template; replicas: number };
export type Pod = { name: string; rs: string; deployment: string; createdAt: number; ip: string };
export type Service = {
  name: string;
  selector: Record<string, string>;
  declaredSelector: Record<string, string>;
  port: number;
  targetPort: number;
};
export type KEvent = { t: number; type: "Normal" | "Warning"; reason: string; object: string; message: string; count: number };
export type Node = { name: string; cpu: number; labels: Record<string, string> };
export type Cluster = {
  time: number;
  seq: number;
  deployments: Deployment[];
  replicasets: ReplicaSet[];
  pods: Pod[];
  services: Service[];
  configmaps: Record<string, Record<string, string>>;
  declaredKeys: Record<string, string[]>;
  secrets: Record<string, string[]>;
  quota: { name: string; pods: number } | null;
  nodes: Node[];
  events: KEvent[];
};

export type PodState = {
  phase: "Running" | "Pending";
  ready: boolean;
  state: "running" | "waiting";
  reason: string | null;
  message: string;
  lastTerminated: string | null;
  crashing: boolean; // container keeps restarting
  log: string;
  warning?: { reason: string; message: string };
};

const IMAGES: Record<string, string[]> = {
  "nginx:1.27-alpine": ["nginx"],
  "busybox:1.36": ["sh", "httpd", "wget", "sleep"],
  "polinux/stress:1.0.4": ["stress", "sh"],
};
const SERVED_PATHS = ["/", "/healthz"];
const NODE_CPU = 4000;

export const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));

function hash(s: string, len = 9): string {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  const chars = "bcdfghjklmnpqrstvwxz2456789";
  let out = "";
  let n = h >>> 0;
  for (let i = 0; i < len; i++) {
    out += chars[n % chars.length];
    n = Math.floor(n / chars.length) + (i + 1) * 7919;
  }
  return out;
}

// ---------------------------------------------------------------------------------------------
// the healthy baseline (mirrors lab/app/*.yaml)

export function baseline(): Cluster {
  const c: Cluster = {
    time: 0,
    seq: 0,
    deployments: [
      {
        name: "api",
        replicas: 2,
        declaredReplicas: 2,
        template: {
          labels: { app: "api" },
          annotations: {},
          spec: {
            container: "api",
            image: "busybox:1.36",
            command: ["sh", "-c"],
            port: 8080,
            envFrom: ["api-config"],
            secretEnv: [{ name: "API_TOKEN", secret: "api-secret", key: "API_TOKEN" }],
            requiredEnv: ["GREETING", "API_TOKEN"],
            liveness: { path: "/healthz", port: 8080 },
            readiness: { path: "/healthz", port: 8080 },
            cpuRequest: 50,
            memLimit: 32,
            memUse: 6,
          },
        },
      },
      {
        name: "web",
        replicas: 2,
        declaredReplicas: 2,
        template: {
          labels: { app: "web" },
          annotations: {},
          spec: {
            container: "nginx",
            image: "nginx:1.27-alpine",
            port: 80,
            envFrom: [],
            secretEnv: [],
            requiredEnv: [],
            liveness: { path: "/healthz", port: 80 },
            readiness: { path: "/healthz", port: 80 },
            cpuRequest: 50,
            memLimit: 64,
            memUse: 12,
          },
        },
      },
      {
        name: "worker",
        replicas: 1,
        declaredReplicas: 1,
        template: {
          labels: { app: "worker" },
          annotations: {},
          spec: {
            container: "worker",
            image: "polinux/stress:1.0.4",
            command: ["stress"],
            port: 0,
            envFrom: [],
            secretEnv: [],
            requiredEnv: [],
            cpuRequest: 50,
            memLimit: 100,
            memUse: 48,
          },
        },
      },
    ],
    replicasets: [],
    pods: [],
    services: [
      { name: "api", selector: { app: "api" }, declaredSelector: { app: "api" }, port: 80, targetPort: 8080 },
      { name: "web", selector: { app: "web" }, declaredSelector: { app: "web" }, port: 80, targetPort: 80 },
    ],
    configmaps: {
      "api-config": { GREETING: "hello from api" },
      "web-nginx": { "default.conf": "server { listen 80; ... }" },
    },
    declaredKeys: { "api-config": ["GREETING"], "web-nginx": ["default.conf"] },
    secrets: { "api-secret": ["API_TOKEN"] },
    quota: null,
    nodes: [
      { name: "healing-lab-worker", cpu: NODE_CPU, labels: { "kubernetes.io/hostname": "healing-lab-worker" } },
      { name: "healing-lab-worker2", cpu: NODE_CPU, labels: { "kubernetes.io/hostname": "healing-lab-worker2" } },
    ],
    events: [],
  };
  reconcile(c);
  c.time = 360; // the app has been up for six minutes
  c.events = [];
  return c;
}

// ---------------------------------------------------------------------------------------------
// pod health: what the kubelet would report for a pod of this template

export function podState(c: Cluster, pod: Pod): PodState {
  const rs = c.replicasets.find((r) => r.name === pod.rs)!;
  const s = rs.template.spec;
  const age = c.time - pod.createdAt;
  const ok: PodState = { phase: "Running", ready: true, state: "running", reason: null, message: "", lastTerminated: null, crashing: false, log: logFor(s) };

  if (s.nodeSelector && !c.nodes.some((n) => Object.entries(s.nodeSelector!).every(([k, v]) => n.labels[k] === v))) {
    const msg = `0/3 nodes are available: 1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }, 2 node(s) didn't match Pod's node affinity/selector.`;
    return { ...ok, phase: "Pending", ready: false, state: "waiting", reason: "Unschedulable", message: msg, log: "", warning: { reason: "FailedScheduling", message: msg } };
  }
  if (s.cpuRequest > NODE_CPU) {
    const msg = `0/3 nodes are available: 1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }, 2 Insufficient cpu.`;
    return { ...ok, phase: "Pending", ready: false, state: "waiting", reason: "Unschedulable", message: msg, log: "", warning: { reason: "FailedScheduling", message: msg } };
  }
  if (!IMAGES[s.image]) {
    const msg = `Back-off pulling image "${s.image}"`;
    return {
      ...ok, ready: false, state: "waiting", reason: age < 20 ? "ErrImagePull" : "ImagePullBackOff", message: msg, log: "",
      warning: { reason: "Failed", message: `Failed to pull image "${s.image}": rpc error: code = NotFound desc = failed to pull and unpack image "docker.io/library/${s.image}": not found` },
    };
  }
  for (const e of s.secretEnv) {
    if (!c.secrets[e.secret]) {
      const msg = `secret "${e.secret}" not found`;
      return { ...ok, ready: false, state: "waiting", reason: "CreateContainerConfigError", message: msg, log: "", warning: { reason: "Failed", message: `Error: ${msg}` } };
    }
  }
  if (s.command && !IMAGES[s.image].includes(s.command[0])) {
    const msg = `failed to create containerd task: exec: "${s.command[0]}": executable file not found in $PATH`;
    return {
      ...ok, ready: false, state: "waiting", reason: "CrashLoopBackOff", message: "back-off restarting failed container", lastTerminated: "StartError",
      crashing: true, log: "", warning: { reason: "Failed", message: `Error: ${msg}` },
    };
  }
  const env = new Set<string>();
  for (const cm of s.envFrom) Object.keys(c.configmaps[cm] ?? {}).forEach((k) => env.add(k));
  for (const e of s.secretEnv) if ((c.secrets[e.secret] ?? []).includes(e.key)) env.add(e.name);
  const missing = s.requiredEnv.find((v) => !env.has(v));
  if (missing) {
    return {
      ...ok, ready: false, state: "waiting", reason: "CrashLoopBackOff", message: "back-off restarting failed container", lastTerminated: "Error",
      crashing: true, log: `FATAL: required env var ${missing} is not set`, warning: { reason: "BackOff", message: "Back-off restarting failed container" },
    };
  }
  if (s.memUse > s.memLimit) {
    return {
      ...ok, ready: false, state: "waiting", reason: "CrashLoopBackOff", message: "back-off restarting failed container", lastTerminated: "OOMKilled",
      crashing: true, log: `stress: info: [1] dispatching hogs: 0 cpu, 0 io, 1 vm, 0 hdd`, warning: { reason: "BackOff", message: "Back-off restarting failed container" },
    };
  }
  const readyOk = !s.readiness || (s.readiness.port === s.port && SERVED_PATHS.includes(s.readiness.path));
  if (s.liveness && s.liveness.port !== s.port) {
    return {
      ...ok, ready: readyOk, crashing: age > 35, lastTerminated: age > 35 ? "Error" : null,
      warning: { reason: "Unhealthy", message: `Liveness probe failed: Get "http://${pod.ip}:${s.liveness.port}${s.liveness.path}": dial tcp ${pod.ip}:${s.liveness.port}: connect: connection refused` },
    };
  }
  if (!readyOk) {
    return { ...ok, ready: false, warning: { reason: "Unhealthy", message: `Readiness probe failed: HTTP probe failed with statuscode: 404` } };
  }
  return ok;
}

function logFor(s: Spec): string {
  if (s.container === "api") return "api listening on :8080";
  if (s.container === "nginx") return `10.244.1.1 - - "GET /healthz HTTP/1.1" 200 3 "-" "kube-probe/1.37"`;
  return "stress: info: [1] dispatching hogs: 0 cpu, 0 io, 1 vm, 0 hdd";
}

export function restarts(c: Cluster, pod: Pod): number {
  const st = podState(c, pod);
  if (!st.crashing) return 0;
  const age = c.time - pod.createdAt;
  return Math.max(1, Math.floor(age / 40));
}

// ---------------------------------------------------------------------------------------------
// controllers

function event(c: Cluster, type: KEvent["type"], reason: string, object: string, message: string) {
  const prev = c.events.find((e) => e.object === object && e.reason === reason && e.message === message);
  if (prev) {
    prev.t = c.time;
    prev.count++;
    return;
  }
  c.events.push({ t: c.time, type, reason, object, message, count: 1 });
  if (c.events.length > 120) c.events.shift();
}

function sameTemplate(a: Template, b: Template) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function newPod(c: Cluster, rs: ReplicaSet): Pod {
  c.seq++;
  const name = `${rs.name}-${hash(rs.name + c.seq, 5)}`;
  return { name, rs: rs.name, deployment: rs.deployment, createdAt: c.time, ip: `10.244.${1 + (c.seq % 2)}.${10 + (c.seq % 200)}` };
}

function wouldBeReady(c: Cluster, rs: ReplicaSet): boolean {
  const probe: Pod = { name: "probe", rs: rs.name, deployment: rs.deployment, createdAt: c.time, ip: "10.244.1.99" };
  return podState(c, probe).ready;
}

export function reconcile(c: Cluster) {
  for (const d of c.deployments) {
    const mine = c.replicasets.filter((r) => r.deployment === d.name);
    let current = mine.find((r) => sameTemplate(r.template, d.template));
    if (!current) {
      const revision = Math.max(0, ...mine.map((r) => r.revision)) + 1;
      current = { name: `${d.name}-${hash(JSON.stringify(d.template))}`, deployment: d.name, revision, template: clone(d.template), replicas: 0 };
      c.replicasets.push(current);
    }
    const others = mine.filter((r) => r !== current);
    const want = new Map<ReplicaSet, number>();
    if (d.replicas === 0) {
      want.set(current, 0);
      others.forEach((r) => want.set(r, 0));
    } else {
      const activeOld = others.filter((r) => r.replicas > 0);
      if (activeOld.length === 0 || wouldBeReady(c, current)) {
        want.set(current, d.replicas);
        others.forEach((r) => want.set(r, 0));
      } else {
        want.set(current, Math.min(1, d.replicas)); // maxSurge 25% rounds up to 1, maxUnavailable rounds down to 0
        const keep = activeOld.sort((a, b) => b.revision - a.revision)[0];
        others.forEach((r) => want.set(r, r === keep ? d.replicas : 0));
      }
    }
    for (const [rs, n] of want) {
      if (rs.replicas !== n) {
        const verb = n > rs.replicas ? "up" : "down";
        event(c, "Normal", "ScalingReplicaSet", `deployment/${d.name}`, `Scaled ${verb} replica set ${rs.name} from ${rs.replicas} to ${n}`);
        rs.replicas = n;
      }
    }
  }
  // pods follow their ReplicaSets, within the namespace quota
  for (const rs of c.replicasets) {
    let pods = c.pods.filter((p) => p.rs === rs.name);
    while (pods.length > rs.replicas) {
      const victim = pods[pods.length - 1];
      c.pods = c.pods.filter((p) => p !== victim);
      pods = pods.slice(0, -1);
    }
    while (pods.length < rs.replicas) {
      if (c.quota && c.pods.length >= c.quota.pods) {
        event(
          c, "Warning", "FailedCreate", `replicaset/${rs.name}`,
          `Error creating: pods "${rs.name}-x" is forbidden: exceeded quota: ${c.quota.name}, requested: pods=1, used: pods=${c.pods.length}, limited: pods=${c.quota.pods}`,
        );
        break;
      }
      const p = newPod(c, rs);
      c.pods.push(p);
      pods.push(p);
      event(c, "Normal", "Scheduled", `pod/${p.name}`, `Successfully assigned demo/${p.name} to healing-lab-worker${c.seq % 2 ? "" : "2"}`);
    }
  }
  for (const p of c.pods) {
    const st = podState(c, p);
    if (st.warning) event(c, "Warning", st.warning.reason, `pod/${p.name}`, st.warning.message);
  }
}

export function advance(c: Cluster, seconds: number) {
  const step = 5;
  for (let t = 0; t < seconds; t += step) {
    c.time += step;
    reconcile(c);
  }
}

// ---------------------------------------------------------------------------------------------
// what the lab's check.sh sees

export function readyPods(c: Cluster, selector: Record<string, string>): Pod[] {
  return c.pods.filter((p) => {
    const rs = c.replicasets.find((r) => r.name === p.rs)!;
    return Object.entries(selector).every(([k, v]) => rs.template.labels[k] === v) && podState(c, p).ready;
  });
}

function serves(c: Cluster, svc: Service | undefined): boolean {
  if (!svc) return false;
  const pods = readyPods(c, svc.selector);
  return pods.some((p) => c.replicasets.find((r) => r.name === p.rs)!.template.spec.port === svc.targetPort);
}

export type Check = { ok: boolean; label: string; detail: string };

export function healthCheck(c: Cluster): Check[] {
  const web = c.services.find((s) => s.name === "web");
  const api = c.services.find((s) => s.name === "api");
  const webUp = serves(c, web);
  const webIp = web ? `10.96.${hash(web.name, 3).length * 60}.231` : "";
  const out: Check[] = [];
  out.push({ ok: webUp, label: "GET web /", detail: webUp ? "web ok" : `wget: can't connect to remote host (${webIp}): Connection refused` });
  const apiUp = webUp && serves(c, api);
  out.push({ ok: apiUp, label: "GET web /api/", detail: apiUp ? "hello from api" : webUp ? "wget: server returned error: HTTP/1.1 502 Bad Gateway" : `wget: can't connect to remote host (${webIp}): Connection refused` });
  for (const name of ["web", "api", "worker"]) {
    const d = c.deployments.find((x) => x.name === name)!;
    const s = deploymentStatus(c, d);
    if (d.replicas === 0) out.push({ ok: false, label: `deploy/${name}`, detail: "scaled to 0 replicas" });
    else if (s.updated < d.replicas || s.ready < d.replicas)
      out.push({ ok: false, label: `deploy/${name}`, detail: `rollout not healthy (desired=${d.replicas} updated=${s.updated} ready=${s.ready})` });
    else out.push({ ok: true, label: `deploy/${name}`, detail: `${s.ready}/${d.replicas} ready` });
  }
  const bad = c.pods.filter((p) => restarts(c, p) > 0).map((p) => `${p.name}(restarts=${restarts(c, p)})`);
  out.push({ ok: bad.length === 0, label: "no restarting pods", detail: bad.length ? `restarting pods -> ${bad.join(" ")}` : "" });
  return out;
}

export const healthy = (c: Cluster) => healthCheck(c).every((x) => x.ok);

export function deploymentStatus(c: Cluster, d: Deployment) {
  const current = c.replicasets.find((r) => r.deployment === d.name && sameTemplate(r.template, d.template));
  const pods = c.pods.filter((p) => p.deployment === d.name);
  return {
    updated: current ? c.pods.filter((p) => p.rs === current.name).length : 0,
    ready: pods.filter((p) => podState(c, p).ready).length,
    available: pods.filter((p) => podState(c, p).ready).length,
  };
}

// ---------------------------------------------------------------------------------------------
// the 14 lab faults (mirrors lab/faults/*)

export type Fault = { id: string; split: "dev" | "heldout"; title: string; story: string; apply: (c: Cluster) => void };

const dep = (c: Cluster, n: string) => c.deployments.find((d) => d.name === n)!;
const svc = (c: Cluster, n: string) => c.services.find((s) => s.name === n)!;
const deletePods = (c: Cluster, app: string) => (c.pods = c.pods.filter((p) => p.deployment !== app));

export const FAULTS: Fault[] = [
  { id: "dev-01-image-typo", split: "dev", title: "Image tag typo", story: "A deploy went out as nginx:1.27-alpinee.", apply: (c) => (dep(c, "web").template.spec.image = "nginx:1.27-alpinee") },
  { id: "dev-02-configmap-key-typo", split: "dev", title: "ConfigMap key typo", story: "Someone renamed GREETING to GREETNG.", apply: (c) => { c.configmaps["api-config"] = { GREETNG: "hello from api" }; deletePods(c, "api"); } },
  { id: "dev-03-oom", split: "dev", title: "Memory limit too low", story: "A cost cut set the worker's limit to 32Mi.", apply: (c) => (dep(c, "worker").template.spec.memLimit = 32) },
  { id: "dev-04-liveness-port", split: "dev", title: "Liveness probe on the wrong port", story: "The probe points at 8081; the app listens on 8080.", apply: (c) => (dep(c, "api").template.spec.liveness = { path: "/healthz", port: 8081 }) },
  { id: "dev-05-readiness-path", split: "dev", title: "Readiness path 404", story: "The probe asks for /health; nginx serves /healthz.", apply: (c) => (dep(c, "web").template.spec.readiness = { path: "/health", port: 80 }) },
  { id: "dev-06-selector-mismatch", split: "dev", title: "Service points at nothing", story: "The selector became app=frontend; pods are app=web.", apply: (c) => (svc(c, "web").selector = { app: "frontend" }) },
  { id: "dev-07-cpu-request", split: "dev", title: "CPU request of 64 cores", story: "Someone typed 64 instead of 64m.", apply: (c) => (dep(c, "api").template.spec.cpuRequest = 64000) },
  { id: "dev-08-missing-secret", split: "dev", title: "Secret deleted", story: "api-secret is gone and nobody knows the token.", apply: (c) => { delete c.secrets["api-secret"]; deletePods(c, "api"); } },
  { id: "dev-09-scaled-to-zero", split: "dev", title: "Scaled to zero", story: "The wrong deployment was scaled to 0.", apply: (c) => (dep(c, "web").replicas = 0) },
  { id: "ho-01-target-port", split: "heldout", title: "Service targetPort wrong", story: "api's Service sends traffic to 8081.", apply: (c) => (svc(c, "api").targetPort = 8081) },
  { id: "ho-02-bad-command", split: "heldout", title: "Command typo", story: "The worker runs stresss.", apply: (c) => (dep(c, "worker").template.spec.command = ["stresss"]) },
  { id: "ho-03-node-selector", split: "heldout", title: "No node matches", story: "web now needs disktype=ssd.", apply: (c) => (dep(c, "web").template.spec.nodeSelector = { disktype: "ssd" }) },
  { id: "ho-04-quota", split: "heldout", title: "Pod quota", story: "An admin quota allows 3 pods.", apply: (c) => { c.quota = { name: "pod-limit", pods: 3 }; deletePods(c, "api"); } },
  {
    id: "ho-05-double-fault", split: "heldout", title: "Two faults at once", story: "A bad worker image and a web selector of app=web-v2.",
    apply: (c) => { dep(c, "worker").template.spec.image = "polinux/stress:9.9.9"; svc(c, "web").selector = { app: "web-v2" }; },
  },
];

export function inject(c: Cluster, id: string) {
  const f = FAULTS.find((x) => x.id === id);
  if (!f) throw new Error(`unknown fault: ${id}`);
  f.apply(c);
  reconcile(c);
}

// ---------------------------------------------------------------------------------------------
// formatting helpers shared by the terminal

export function age(seconds: number): string {
  if (seconds < 120) return `${Math.max(0, Math.round(seconds))}s`;
  if (seconds < 7200) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

export function table(rows: string[][]): string {
  const w = rows[0].map((_, i) => Math.max(...rows.map((r) => (r[i] ?? "").length)));
  return rows.map((r) => r.map((cell, i) => (i === r.length - 1 ? cell : cell.padEnd(w[i] + 3))).join("")).join("\n");
}

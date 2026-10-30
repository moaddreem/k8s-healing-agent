// What to look at, step by step, for each fault: the commands an engineer would run and what
// to look for in their output. Pod names are read from the live simulation.
import * as sim from "./sim";
import type { Cluster } from "./sim";

export type Hint = { cmd: string; look: string };

const newestPod = (c: Cluster, dep: string) => {
  const rss = c.replicasets.filter((r) => r.deployment === dep).sort((a, b) => b.revision - a.revision);
  for (const rs of rss) {
    const p = c.pods.find((x) => x.rs === rs.name);
    if (p) return p.name;
  }
  return c.pods.find((p) => p.deployment === dep)?.name ?? `${dep}-pod`;
};

export function inspectHints(c: Cluster, fault: string): Hint[] {
  const api = newestPod(c, "api");
  const web = newestPod(c, "web");
  const worker = newestPod(c, "worker");
  const pods: Hint = { cmd: "kubectl get pods", look: "Which pods are not Running and Ready? Check STATUS and RESTARTS." };
  switch (fault) {
    case "dev-01-image-typo":
      return [pods, { cmd: "kubectl get rs -o wide", look: "Two ReplicaSets for web. Compare the IMAGES column." }, { cmd: `kubectl describe pod ${web}`, look: "The Events at the bottom say why the image cannot be pulled." }];
    case "dev-02-configmap-key-typo":
      return [pods, { cmd: `kubectl logs ${api} --previous`, look: "The app says which setting it is missing." }, { cmd: "kubectl describe cm api-config", look: "Compare the key name with what the app asked for." }];
    case "dev-03-oom":
      return [pods, { cmd: `kubectl describe pod ${worker}`, look: "Last State and its Reason, next to the memory limit." }];
    case "dev-04-liveness-port":
      return [pods, { cmd: `kubectl describe pod ${api}`, look: "The Liveness port against the container Port, and the probe Events." }];
    case "dev-05-readiness-path":
      return [pods, { cmd: `kubectl describe pod ${web}`, look: "The Readiness path, and what the probe Events say about it." }];
    case "dev-06-selector-mismatch":
      return [pods, { cmd: "kubectl get endpoints", look: "Every pod is healthy, but does the web Service have any endpoints?" }, { cmd: "kubectl describe svc web", look: "Which label does the Service select? Do the pods carry it?" }];
    case "dev-07-cpu-request":
      return [pods, { cmd: `kubectl describe pod ${api}`, look: "The CPU request, and why the scheduler cannot place the pod." }];
    case "dev-08-missing-secret":
      return [pods, { cmd: `kubectl describe pod ${api}`, look: "The Events name what the container needs and cannot find." }, { cmd: "kubectl get secrets", look: "Is it there? Could anyone but its owner know its value?" }];
    case "dev-09-scaled-to-zero":
      return [{ cmd: "kubectl get deploy", look: "Nothing is crashing. Look at READY for web." }, { cmd: "kubectl get events", look: "Who changed the replica count, and from what?" }];
    case "ho-01-target-port":
      return [pods, { cmd: "kubectl describe svc api", look: "Compare the TargetPort with the port api listens on." }, { cmd: `kubectl describe pod ${api}`, look: "The container Port." }];
    case "ho-02-bad-command":
      return [pods, { cmd: `kubectl describe pod ${worker}`, look: "The Command, and what the Events say about starting it." }];
    case "ho-03-node-selector":
      return [pods, { cmd: `kubectl describe pod ${web}`, look: "Node-Selectors, and the scheduler's message in the Events." }];
    case "ho-04-quota":
      return [pods, { cmd: "kubectl get events", look: "Why can the api ReplicaSet not create pods?" }, { cmd: "kubectl get quota", look: "Who set this limit? Should an agent remove it?" }];
    case "ho-05-double-fault":
      return [pods, { cmd: "kubectl get endpoints", look: "Something besides the pods is wrong." }, { cmd: "kubectl describe svc web", look: "Look at the selector." }];
    default:
      return [pods];
  }
}

export function verifyHints(fault: string): Hint[] {
  const check: Hint = { cmd: "check", look: "The same health check the real lab uses: every line should pass." };
  const pods: Hint = { cmd: "kubectl get pods", look: "Everything Running and Ready, no restarts." };
  const extra: Record<string, Hint> = {
    "dev-01-image-typo": { cmd: "kubectl rollout history deploy/web", look: "The rollback is a new revision; nothing was deleted." },
    "dev-02-configmap-key-typo": { cmd: "kubectl describe cm api-config", look: "The key now reads GREETING." },
    "dev-06-selector-mismatch": { cmd: "kubectl get endpoints", look: "web has endpoints again." },
    "dev-09-scaled-to-zero": { cmd: "kubectl get deploy", look: "web is back to 2/2." },
    "ho-01-target-port": { cmd: "kubectl describe svc api", look: "Unchanged in the browser: the rules alone could not fix it." },
    "ho-05-double-fault": { cmd: "kubectl get endpoints", look: "Both faults are gone." },
  };
  return [check, pods, ...(extra[fault] ? [extra[fault]] : [])];
}

// Plain-language diff of what Nabd changed.
export function changes(before: Cluster, after: Cluster): string[] {
  const out: string[] = [];
  for (const d of after.deployments) {
    const b = before.deployments.find((x) => x.name === d.name);
    if (!b) continue;
    const bs = b.template.spec;
    const as = d.template.spec;
    const id = `deployment/${d.name}`;
    if (b.replicas !== d.replicas) out.push(`${id} replicas ${b.replicas} → ${d.replicas}`);
    if (bs.image !== as.image) out.push(`${id} image ${bs.image} → ${as.image}`);
    if (bs.memLimit !== as.memLimit) out.push(`${id} memory limit ${bs.memLimit}Mi → ${as.memLimit}Mi`);
    if (bs.cpuRequest !== as.cpuRequest) out.push(`${id} CPU request ${bs.cpuRequest}m → ${as.cpuRequest}m`);
    if (bs.liveness?.port !== as.liveness?.port) out.push(`${id} liveness port ${bs.liveness?.port} → ${as.liveness?.port}`);
    if (bs.readiness?.path !== as.readiness?.path) out.push(`${id} readiness path ${bs.readiness?.path} → ${as.readiness?.path}`);
    if (JSON.stringify(bs.command) !== JSON.stringify(as.command)) out.push(`${id} command ${bs.command?.join(" ")} → ${as.command?.join(" ")}`);
    if (JSON.stringify(bs.nodeSelector ?? {}) !== JSON.stringify(as.nodeSelector ?? {})) out.push(`${id} node selector removed`);
    if (b.template.annotations["kubectl.kubernetes.io/restartedAt"] !== d.template.annotations["kubectl.kubernetes.io/restartedAt"])
      out.push(`${id} pods restarted to read the corrected configuration`);
  }
  for (const s of after.services) {
    const b = before.services.find((x) => x.name === s.name)!;
    if (JSON.stringify(b.selector) !== JSON.stringify(s.selector)) out.push(`service/${s.name} selector ${JSON.stringify(b.selector)} → ${JSON.stringify(s.selector)}`);
    if (b.targetPort !== s.targetPort) out.push(`service/${s.name} targetPort ${b.targetPort} → ${s.targetPort}`);
  }
  for (const [name, data] of Object.entries(after.configmaps)) {
    const bk = Object.keys(before.configmaps[name] ?? {}).sort().join(", ");
    const ak = Object.keys(data).sort().join(", ");
    if (bk !== ak) out.push(`configmap/${name} keys [${bk}] → [${ak}]`);
  }
  return out;
}

export const healthySummary = (c: Cluster) => sim.healthCheck(c).filter((x) => !x.ok).length;

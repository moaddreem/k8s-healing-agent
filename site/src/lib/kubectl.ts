// A kubectl-shaped command line for the simulated lab. Read commands print what kubectl would;
// write commands (scale, set image, rollout undo, delete pod) change the simulation.
import * as sim from "./sim";
import { rolloutUndo } from "./nabd";
import type { Cluster, Pod } from "./sim";

export const HELP = `Commands (namespace demo is the default):
  kubectl get pods|deploy|rs|svc|endpoints|events|cm|secrets|quota|nodes|all [-o wide]
  kubectl describe pod|deploy|svc <name>
  kubectl logs <pod> [--previous]
  kubectl rollout status|history|undo deploy/<name>
  kubectl scale deploy <name> --replicas=<n>
  kubectl set image deploy/<name> <container>=<image>
  kubectl delete pod <name>
  check            run the lab health check (lab/check.sh)
  break <fault>    inject a fault, e.g. break dev-01-image-typo   (list: faults)
  reset            back to the healthy baseline
  nabd run         let Nabd heal the namespace
  clear            clear the screen`;

const KIND: Record<string, string> = {
  po: "pods", pod: "pods", pods: "pods",
  deploy: "deployments", deployment: "deployments", deployments: "deployments",
  rs: "replicasets", replicaset: "replicasets", replicasets: "replicasets",
  svc: "services", service: "services", services: "services",
  ep: "endpoints", endpoints: "endpoints",
  ev: "events", event: "events", events: "events",
  cm: "configmaps", configmap: "configmaps", configmaps: "configmaps",
  secret: "secrets", secrets: "secrets",
  quota: "resourcequotas", resourcequota: "resourcequotas", resourcequotas: "resourcequotas",
  node: "nodes", nodes: "nodes", no: "nodes",
  all: "all",
};

function status(c: Cluster, p: Pod): string {
  const st = sim.podState(c, p);
  if (st.phase === "Pending") return "Pending";
  if (st.state === "waiting") return st.reason ?? "Waiting";
  return "Running";
}

function podsTable(c: Cluster, wide: boolean, label?: [string, string]): string {
  const pods = c.pods.filter((p) => {
    if (!label) return true;
    const rs = c.replicasets.find((r) => r.name === p.rs)!;
    return rs.template.labels[label[0]] === label[1];
  });
  if (!pods.length) return "No resources found in demo namespace.";
  const head = ["NAME", "READY", "STATUS", "RESTARTS", "AGE", ...(wide ? ["IP", "NODE"] : [])];
  return sim.table([
    head,
    ...pods.map((p, i) => {
      const st = sim.podState(c, p);
      const r = sim.restarts(c, p);
      return [
        p.name, st.ready ? "1/1" : "0/1", status(c, p), r ? `${r} (${10 + i * 7}s ago)` : "0", sim.age(c.time - p.createdAt),
        ...(wide ? [st.phase === "Pending" ? "<none>" : p.ip, st.phase === "Pending" ? "<none>" : i % 2 ? "healing-lab-worker2" : "healing-lab-worker"] : []),
      ];
    }),
  ]);
}

function deploysTable(c: Cluster): string {
  return sim.table([
    ["NAME", "READY", "UP-TO-DATE", "AVAILABLE", "AGE"],
    ...c.deployments.map((d) => {
      const s = sim.deploymentStatus(c, d);
      return [d.name, `${s.ready}/${d.replicas}`, String(s.updated), String(s.available), "6m"];
    }),
  ]);
}

function rsTable(c: Cluster, wide: boolean): string {
  return sim.table([
    ["NAME", "DESIRED", "CURRENT", "READY", "AGE", ...(wide ? ["IMAGES"] : [])],
    ...c.replicasets.map((r) => {
      const pods = c.pods.filter((p) => p.rs === r.name);
      return [r.name, String(r.replicas), String(pods.length), String(pods.filter((p) => sim.podState(c, p).ready).length), "6m", ...(wide ? [r.template.spec.image] : [])];
    }),
  ]);
}

function svcTable(c: Cluster): string {
  return sim.table([
    ["NAME", "TYPE", "CLUSTER-IP", "EXTERNAL-IP", "PORT(S)", "AGE"],
    ...c.services.map((s, i) => [s.name, "ClusterIP", i ? "10.96.186.202" : "10.96.22.22", "<none>", `${s.port}/TCP`, "6m"]),
  ]);
}

function epTable(c: Cluster): string {
  return sim.table([
    ["NAME", "ENDPOINTS", "AGE"],
    ...c.services.map((s) => {
      const pods = sim.readyPods(c, s.selector);
      return [s.name, pods.length ? pods.map((p) => `${p.ip}:${s.targetPort}`).join(",") : "<none>", "6m"];
    }),
  ]);
}

function eventsTable(c: Cluster): string {
  if (!c.events.length) return "No events found in demo namespace.";
  return sim.table([
    ["LAST SEEN", "TYPE", "REASON", "OBJECT", "MESSAGE"],
    ...[...c.events].sort((a, b) => a.t - b.t).slice(-25).map((e) => [sim.age(c.time - e.t), e.type, e.reason, e.object, e.message]),
  ]);
}

function describePod(c: Cluster, name: string): string {
  const p = c.pods.find((x) => x.name === name);
  if (!p) return `Error from server (NotFound): pods "${name}" not found`;
  const rs = c.replicasets.find((r) => r.name === p.rs)!;
  const s = rs.template.spec;
  const st = sim.podState(c, p);
  const lines = [
    `Name:             ${p.name}`,
    `Namespace:        demo`,
    `Node:             ${st.phase === "Pending" ? "<none>" : "healing-lab-worker"}`,
    `Labels:           app=${rs.template.labels.app}`,
    `Status:           ${st.phase}`,
    `IP:               ${st.phase === "Pending" ? "" : p.ip}`,
    `Controlled By:    ReplicaSet/${rs.name}`,
    `Containers:`,
    `  ${s.container}:`,
    `    Image:          ${s.image}`,
    ...(s.command ? [`    Command:        ${s.command.join(" ")}`] : []),
    ...(s.port ? [`    Port:           ${s.port}/TCP`] : []),
    `    State:          ${st.state === "running" ? "Running" : "Waiting"}`,
    ...(st.reason ? [`      Reason:       ${st.reason}`] : []),
    ...(st.lastTerminated ? [`    Last State:     Terminated`, `      Reason:       ${st.lastTerminated}`] : []),
    `    Ready:          ${st.ready ? "True" : "False"}`,
    `    Restart Count:  ${sim.restarts(c, p)}`,
    `    Limits:         memory: ${s.memLimit}Mi`,
    `    Requests:       cpu: ${s.cpuRequest >= 1000 ? s.cpuRequest / 1000 : s.cpuRequest + "m"}`,
    ...(s.liveness ? [`    Liveness:       http-get http://:${s.liveness.port}${s.liveness.path}`] : []),
    ...(s.readiness ? [`    Readiness:      http-get http://:${s.readiness.port}${s.readiness.path}`] : []),
    ...(s.envFrom.length ? [`    Environment Variables from:`, ...s.envFrom.map((cm) => `      ${cm}  ConfigMap`)] : []),
    ...(s.secretEnv.length ? [`    Environment:`, ...s.secretEnv.map((e) => `      ${e.name}:  <set to the key '${e.key}' in secret '${e.secret}'>`)] : []),
    ...(s.nodeSelector ? [`Node-Selectors:   ${Object.entries(s.nodeSelector).map(([k, v]) => `${k}=${v}`).join(",")}`] : []),
    `Events:`,
  ];
  const evs = c.events.filter((e) => e.object === `pod/${p.name}`);
  if (!evs.length) lines.push("  <none>");
  else lines.push(sim.table([["  Type", "Reason", "Age", "Message"], ...evs.map((e) => [`  ${e.type}`, e.reason, sim.age(c.time - e.t), e.message])]));
  return lines.join("\n");
}

function describeDeploy(c: Cluster, name: string): string {
  const d = c.deployments.find((x) => x.name === name);
  if (!d) return `Error from server (NotFound): deployments.apps "${name}" not found`;
  const s = sim.deploymentStatus(c, d);
  const rss = c.replicasets.filter((r) => r.deployment === d.name).sort((a, b) => b.revision - a.revision);
  const current = rss.find((r) => JSON.stringify(r.template) === JSON.stringify(d.template));
  const stuck = s.updated < d.replicas || s.ready < d.replicas;
  return [
    `Name:                   ${d.name}`,
    `Namespace:              demo`,
    `Selector:               app=${d.template.labels.app}`,
    `Replicas:               ${d.replicas} desired | ${s.updated} updated | ${c.pods.filter((p) => p.deployment === d.name).length} total | ${s.available} available`,
    `StrategyType:           RollingUpdate`,
    `Pod Template:`,
    `  Labels:  app=${d.template.labels.app}`,
    `  Containers:`,
    `   ${d.template.spec.container}:`,
    `    Image:  ${d.template.spec.image}`,
    `Conditions:`,
    `  Type           Status  Reason`,
    `  Progressing    ${stuck && d.replicas > 0 ? "False   ProgressDeadlineExceeded" : "True    NewReplicaSetAvailable"}`,
    `OldReplicaSets:  ${rss.filter((r) => r !== current && r.replicas > 0).map((r) => `${r.name} (${r.replicas}/${r.replicas} replicas created)`).join(", ") || "<none>"}`,
    `NewReplicaSet:   ${current ? `${current.name} (${current.replicas}/${current.replicas} replicas created)` : "<none>"}`,
    `Events:`,
    ...c.events.filter((e) => e.object === `deployment/${d.name}`).slice(-6).map((e) => `  ${e.type}  ${e.reason}  ${sim.age(c.time - e.t)}  ${e.message}`),
  ].join("\n");
}

function describeSvc(c: Cluster, name: string): string {
  const s = c.services.find((x) => x.name === name);
  if (!s) return `Error from server (NotFound): services "${name}" not found`;
  const pods = sim.readyPods(c, s.selector);
  return [
    `Name:              ${s.name}`,
    `Namespace:         demo`,
    `Selector:          ${Object.entries(s.selector).map(([k, v]) => `${k}=${v}`).join(",")}`,
    `Type:              ClusterIP`,
    `Port:              <unset>  ${s.port}/TCP`,
    `TargetPort:        ${s.targetPort}/TCP`,
    `Endpoints:         ${pods.length ? pods.map((p) => `${p.ip}:${s.targetPort}`).join(",") : "<none>"}`,
  ].join("\n");
}

function logs(c: Cluster, name: string, previous: boolean): string {
  const p = c.pods.find((x) => x.name === name);
  if (!p) return `error: pods "${name}" not found`;
  const st = sim.podState(c, p);
  if (st.state === "waiting" && !st.crashing)
    return `Error from server (BadRequest): container "${c.replicasets.find((r) => r.name === p.rs)!.template.spec.container}" in pod "${p.name}" is waiting to start: ${st.reason}`;
  if (previous && !st.crashing) return `Error from server (BadRequest): previous terminated container in pod "${p.name}" not found`;
  return st.log || "(no output)";
}

function rollout(c: Cluster, verb: string, target: string): string {
  const name = target.replace(/^(deploy|deployment|deployments)\//, "");
  const d = c.deployments.find((x) => x.name === name);
  if (!d) return `Error from server (NotFound): deployments.apps "${name}" not found`;
  if (verb === "status") {
    const s = sim.deploymentStatus(c, d);
    if (s.updated >= d.replicas && s.ready >= d.replicas) return `deployment "${name}" successfully rolled out`;
    return `Waiting for deployment "${name}" rollout to finish: ${s.updated} out of ${d.replicas} new replicas have been updated...\nerror: deployment "${name}" exceeded its progress deadline`;
  }
  if (verb === "history") {
    const rss = c.replicasets.filter((r) => r.deployment === name).sort((a, b) => a.revision - b.revision);
    return `deployment.apps/${name}\n` + sim.table([["REVISION", "CHANGE-CAUSE"], ...rss.map((r) => [String(r.revision), "<none>"])]);
  }
  if (verb === "undo") {
    const err = rolloutUndo(c, name);
    return err ? `error: ${err}` : `deployment.apps/${name} rolled back`;
  }
  return `error: unknown rollout command "${verb}"`;
}

export function kubectl(c: Cluster, args: string[]): string {
  const flags = args.filter((a) => a.startsWith("-"));
  const words = args.filter((a, i) => !a.startsWith("-") && !(i > 0 && ["-n", "--namespace", "-o", "-l", "-c"].includes(args[i - 1])));
  const ns = args[args.indexOf("-n") + 1] ?? args[args.indexOf("--namespace") + 1];
  if ((args.includes("-n") || args.includes("--namespace")) && ns !== "demo") return `No resources found in ${ns} namespace. (this simulation models namespace demo)`;
  const wide = args.includes("wide") || flags.includes("-owide");
  const [verb, a1, a2] = words;
  switch (verb) {
    case "get": {
      const kind = KIND[a1 ?? ""];
      const labelArg = args[args.indexOf("-l") + 1];
      const label = args.includes("-l") && labelArg?.includes("=") ? (labelArg.split("=") as [string, string]) : undefined;
      if (a2 && kind === "pods") return podsTable({ ...c, pods: c.pods.filter((p) => p.name === a2) }, wide) || `Error from server (NotFound): pods "${a2}" not found`;
      switch (kind) {
        case "pods": return podsTable(c, wide, label);
        case "deployments": return deploysTable(c);
        case "replicasets": return rsTable(c, wide);
        case "services": return svcTable(c);
        case "endpoints": return epTable(c);
        case "events": return eventsTable(c);
        case "configmaps": return sim.table([["NAME", "DATA", "AGE"], ["kube-root-ca.crt", "1", "6m"], ...Object.entries(c.configmaps).map(([n, d]) => [n, String(Object.keys(d).length), "6m"])]);
        case "secrets": return Object.keys(c.secrets).length ? sim.table([["NAME", "TYPE", "DATA", "AGE"], ...Object.entries(c.secrets).map(([n, k]) => [n, "Opaque", String(k.length), "6m"])]) : "No resources found in demo namespace.";
        case "resourcequotas": return c.quota ? sim.table([["NAME", "AGE", "REQUEST", "LIMIT"], [c.quota.name, "1m", `pods: ${c.pods.length}/${c.quota.pods}`, ""]]) : "No resources found in demo namespace.";
        case "nodes": return sim.table([["NAME", "STATUS", "ROLES", "AGE", "VERSION"], ["healing-lab-control-plane", "Ready", "control-plane", "10h", "v1.37.0"], ...c.nodes.map((n) => [n.name, "Ready", "<none>", "10h", "v1.37.0"])]);
        case "all": return [podsTable(c, false), svcTable(c), deploysTable(c), rsTable(c, false)].join("\n\n");
        default: return `error: the server doesn't have a resource type "${a1 ?? ""}"`;
      }
    }
    case "describe": {
      const kind = KIND[a1 ?? ""];
      if (!a2) return "error: you must specify the name of the resource to describe";
      if (kind === "pods") return describePod(c, a2);
      if (kind === "deployments") return describeDeploy(c, a2);
      if (kind === "services") return describeSvc(c, a2);
      if (kind === "configmaps") {
        const data = c.configmaps[a2];
        if (!data) return `Error from server (NotFound): configmaps "${a2}" not found`;
        return [`Name:         ${a2}`, `Namespace:    demo`, `Data`, `====`, ...Object.entries(data).flatMap(([k, v]) => [`${k}:`, `----`, v, ""])].join("\n");
      }
      if (kind === "secrets") {
        const keys = c.secrets[a2];
        if (!keys) return `Error from server (NotFound): secrets "${a2}" not found`;
        return [`Name:         ${a2}`, `Namespace:    demo`, `Type:  Opaque`, `Data`, `====`, ...keys.map((k) => `${k}:  <hidden>`)].join("\n");
      }
      return `error: describe supports pod, deploy, svc, cm and secret in this simulation`;
    }
    case "logs":
      return a1 ? logs(c, a1, args.includes("--previous") || args.includes("-p")) : "error: expected 'logs POD_NAME'";
    case "rollout":
      return a1 && a2 ? rollout(c, a1, a2) : "error: expected 'rollout status|history|undo deploy/NAME'";
    case "scale": {
      const name = (a2 ?? a1 ?? "").replace(/^(deploy|deployment|deployments)\//, "");
      const n = Number((args.find((a) => a.startsWith("--replicas=")) ?? "").split("=")[1]);
      const d = c.deployments.find((x) => x.name === name);
      if (!d) return `Error from server (NotFound): deployments.apps "${name}" not found`;
      if (!Number.isInteger(n) || n < 0) return "error: --replicas=COUNT is required";
      d.replicas = n;
      sim.reconcile(c);
      return `deployment.apps/${name} scaled`;
    }
    case "set": {
      if (a1 !== "image") return "error: only 'set image' is supported in this simulation";
      const name = (a2 ?? "").replace(/^(deploy|deployment|deployments)\//, "");
      const pair = words[3] ?? "";
      const d = c.deployments.find((x) => x.name === name);
      if (!d) return `Error from server (NotFound): deployments.apps "${name}" not found`;
      const [container, image] = pair.split("=");
      if (container !== d.template.spec.container || !image) return `error: unable to find container named "${container}"`;
      d.template.spec.image = image;
      sim.reconcile(c);
      return `deployment.apps/${name} image updated`;
    }
    case "delete": {
      if (KIND[a1 ?? ""] !== "pods" || !a2) return "error: only 'delete pod NAME' is supported in this simulation";
      if (!c.pods.some((p) => p.name === a2)) return `Error from server (NotFound): pods "${a2}" not found`;
      c.pods = c.pods.filter((p) => p.name !== a2);
      sim.reconcile(c);
      return `pod "${a2}" deleted`;
    }
    case undefined:
      return HELP;
    default:
      return `error: unknown command "${verb}" for "kubectl"\n\n${HELP}`;
  }
}

"""Evidence collector: the agent's eyes. Read-only.

Everything is summarised into plain dicts so the rules and the LLM read the same facts.
Secrets: only key NAMES are listed (through a go-template), their values never reach this process.
"""
import json
from datetime import datetime, timezone

from . import kube

LAST_APPLIED = "kubectl.kubernetes.io/last-applied-configuration"
REVISION = "deployment.kubernetes.io/revision"
SKIP_CONFIGMAPS = {"kube-root-ca.crt"}


def _declared(obj):
    """The spec the object was last `kubectl apply`-ed with, i.e. what its owner *intended*."""
    raw = (obj["metadata"].get("annotations") or {}).get(LAST_APPLIED)
    return json.loads(raw) if raw else {}


def _owner(obj):
    refs = obj["metadata"].get("ownerReferences") or []
    return refs[0]["name"] if refs else None


def _selects(selector, labels):
    return bool(selector) and all(labels.get(k) == v for k, v in selector.items())


def _config_refs(containers):
    configmaps, secrets = set(), set()
    for c in containers:
        for ef in c.get("envFrom") or []:
            if "configMapRef" in ef:
                configmaps.add(ef["configMapRef"]["name"])
            if "secretRef" in ef:
                secrets.add(ef["secretRef"]["name"])
        for e in c.get("env") or []:
            ref = e.get("valueFrom") or {}
            if "configMapKeyRef" in ref:
                configmaps.add(ref["configMapKeyRef"]["name"])
            if "secretKeyRef" in ref:
                secrets.add(ref["secretKeyRef"]["name"])
    return sorted(configmaps), sorted(secrets)


def _replicaset(r):
    meta = r["metadata"]
    return {
        "name": meta["name"],
        "owner": _owner(r),
        "revision": int((meta.get("annotations") or {}).get(REVISION, 0)),
        "desired": r["spec"].get("replicas", 0),
        "ready": r.get("status", {}).get("readyReplicas", 0),
        "images": [c["image"] for c in r["spec"]["template"]["spec"]["containers"]],
    }


def _deployment(d, replicasets):
    spec, status = d["spec"], d.get("status", {})
    containers = spec["template"]["spec"]["containers"]
    declared = _declared(d).get("spec", {})
    progressing = next((c for c in status.get("conditions", []) if c["type"] == "Progressing"), {})
    configmaps, secrets = _config_refs(containers)
    name = d["metadata"]["name"]
    return {
        "name": name,
        "desired": spec.get("replicas", 1),
        "updated": status.get("updatedReplicas", 0),
        "ready": status.get("readyReplicas", 0),
        "images": [c["image"] for c in containers],
        "container_ports": sorted({p["containerPort"] for c in containers for p in c.get("ports") or []}),
        "pod_labels": spec["template"]["metadata"].get("labels", {}),
        "selector": spec["selector"].get("matchLabels", {}),
        "configmaps": configmaps,
        "secrets": secrets,
        "declared_replicas": declared.get("replicas"),
        "declared_images": [
            c["image"] for c in declared.get("template", {}).get("spec", {}).get("containers", [])
        ],
        "progress": {
            "status": progressing.get("status"),
            "reason": progressing.get("reason"),
            "message": progressing.get("message"),
        },
        "replicasets": sorted((r for r in replicasets if r["owner"] == name), key=lambda r: r["revision"]),
    }


def _pod(p):
    meta, status = p["metadata"], p.get("status", {})
    containers = []
    for c in status.get("containerStatuses") or []:
        state = c.get("state") or {}
        kind = next(iter(state), None)
        detail = (state.get(kind) or {}) if kind else {}
        last = (c.get("lastState") or {}).get("terminated") or {}
        containers.append(
            {
                "name": c["name"],
                "image": c["image"],
                "ready": c["ready"],
                "restarts": c["restartCount"],
                "state": kind,
                "reason": detail.get("reason"),
                "message": (detail.get("message") or "")[:300],
                "last_terminated_reason": last.get("reason"),
                "last_exit_code": last.get("exitCode"),
            }
        )
    scheduled = next((c for c in status.get("conditions", []) if c["type"] == "PodScheduled"), {})
    return {
        "name": meta["name"],
        "labels": meta.get("labels", {}),
        "replicaset": _owner(p),
        "phase": status.get("phase"),
        "unschedulable": scheduled.get("message") if scheduled.get("status") == "False" else None,
        "containers": containers,
    }


def _service(s, slices, deployments):
    name = s["metadata"]["name"]
    selector = s["spec"].get("selector") or {}
    ready = sum(
        1
        for sl in slices
        if (sl["metadata"].get("labels") or {}).get("kubernetes.io/service-name") == name
        for e in sl.get("endpoints") or []
        if (e.get("conditions") or {}).get("ready") is not False
    )
    return {
        "name": name,
        "selector": selector,
        "declared_selector": _declared(s).get("spec", {}).get("selector"),
        "ports": [{"port": x.get("port"), "targetPort": x.get("targetPort")} for x in s["spec"].get("ports", [])],
        "ready_endpoints": ready,
        "selects_deployments": [d["name"] for d in deployments if _selects(selector, d["pod_labels"])],
    }


def _events(items):
    out = []
    for e in items:
        obj = e.get("involvedObject", {})
        out.append(
            {
                "time": e.get("lastTimestamp") or e.get("eventTime") or e["metadata"]["creationTimestamp"],
                "type": e.get("type"),
                "reason": e.get("reason"),
                "object": f"{obj.get('kind', '').lower()}/{obj.get('name')}",
                "message": (e.get("message") or "")[:300],
            }
        )
    out.sort(key=lambda x: x["time"] or "")
    return out[-80:]


def _logs(ns, pods):
    out = {}
    for p in pods:
        for c in p["containers"]:
            if c["restarts"] > 0 or c["reason"] in ("CrashLoopBackOff", "Error"):
                text = kube.pod_logs(ns, p["name"], c["name"], previous=True) if c["restarts"] > 0 else ""
                text = text or kube.pod_logs(ns, p["name"], c["name"])
                if text:
                    out.setdefault(p["name"], {})[c["name"]] = text
    return out


def _secret_keys(ns):
    template = 'go-template={{range .items}}{{.metadata.name}}:{{range $k, $v := .data}} {{$k}}{{end}}{{"\\n"}}{{end}}'
    rc, out, _ = kube.kubectl("get", "secrets", "-n", ns, "-o", template)
    result = []
    for line in out.splitlines() if rc == 0 else []:
        name, _, keys = line.partition(":")
        if name:
            result.append({"name": name.strip(), "keys": keys.split()})
    return result


def collect(ns="demo"):
    replicasets = [_replicaset(r) for r in kube.get_json(ns, "replicasets")["items"]]
    deployments = [_deployment(d, replicasets) for d in kube.get_json(ns, "deployments")["items"]]
    pods = [
        _pod(p)
        for p in kube.get_json(ns, "pods")["items"]
        if p["metadata"].get("deletionTimestamp") is None
    ]
    slices = kube.get_json(ns, "endpointslices.discovery.k8s.io")["items"]
    return {
        "namespace": ns,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "deployments": deployments,
        "pods": pods,
        "services": [_service(s, slices, deployments) for s in kube.get_json(ns, "services")["items"]],
        "events": _events(kube.get_json(ns, "events")["items"]),
        "logs": _logs(ns, pods),
        "configmaps": [
            {
                "name": c["metadata"]["name"],
                "keys": sorted((c.get("data") or {}).keys()),
                "declared_keys": sorted((_declared(c).get("data") or {}).keys()),
            }
            for c in kube.get_json(ns, "configmaps")["items"]
            if c["metadata"]["name"] not in SKIP_CONFIGMAPS
        ],
        "secrets": _secret_keys(ns),
        "resourcequotas": [
            {"name": q["metadata"]["name"], "hard": q["spec"].get("hard"), "used": q.get("status", {}).get("used")}
            for q in kube.get_json(ns, "resourcequotas")["items"]
        ],
    }


def brief(ev):
    """A short human-readable picture of the namespace."""
    lines = []
    for d in ev["deployments"]:
        lines.append(
            f"deployment/{d['name']:<7} desired={d['desired']} updated={d['updated']} ready={d['ready']} "
            f"revisions={len(d['replicasets'])} image={','.join(d['images'])}"
        )
    for s in ev["services"]:
        lines.append(f"service/{s['name']:<9} ready_endpoints={s['ready_endpoints']} selector={s['selector']}")
    for p in ev["pods"]:
        for c in p["containers"] or [{"state": p["phase"], "reason": p["unschedulable"], "restarts": 0}]:
            lines.append(f"pod/{p['name']:<26} {c['state']}/{c['reason']} restarts={c['restarts']}")
    return "\n".join(lines)

"""Rules diagnoser: turns cluster evidence into a root cause and a safe fix, with no AI.

Written from the 9 *dev* faults only. The held-out faults are never used to tune these rules.
Every diagnosis is a dict:
  rule, category, target, summary, evidence[], fix[], escalate, confidence, source
`fix` is a list of actions from the closed action vocabulary (see actions.py), never raw kubectl.
"""
import difflib
import re

SCALE_DOWN = re.compile(r"from (\d+) to 0")
NOT_FOUND = re.compile(r'(secret|configmap) "([^"]+)" not found')
NOT_SET = re.compile(r"\b([A-Z][A-Z0-9_]{2,}) is not set")
IMAGE_ERRORS = {"ImagePullBackOff", "ErrImagePull", "InvalidImageName"}
EXTERNAL_ERROR = re.compile(r"connection refused|timed out|no such host|could not resolve|ECONNREFUSED|ETIMEDOUT", re.I)
EXTERNAL_HOST = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:com|net|org|io|sa|dev|cloud|ai|app))\b", re.I)


def _dx(rule, category, target, summary, evidence, fix=None, escalate=False, confidence=0.9):
    return {
        "rule": rule,
        "category": category,
        "target": target,
        "summary": summary,
        "evidence": evidence,
        "fix": fix or [],
        "escalate": escalate,
        "confidence": confidence,
        "source": "rules",
    }


def _deployment_of(ev, pod):
    for d in ev["deployments"]:
        if any(r["name"] == pod["replicaset"] for r in d["replicasets"]):
            return d
    return None


# --- rule 1: a deployment was scaled to zero (dev-09) ---------------------------------------
def _previous_replicas(ev, d):
    for e in reversed(ev["events"]):
        if e["object"] == f"deployment/{d['name']}":
            m = SCALE_DOWN.search(e["message"])
            if m:
                return int(m.group(1)), f"event: {e['message']}"
    if d["declared_replicas"]:
        return d["declared_replicas"], f"last-applied spec says replicas={d['declared_replicas']}"
    return 1, "no history found, defaulting to 1"


def scaled_to_zero(ev):
    out = []
    for d in ev["deployments"]:
        if d["desired"] != 0:
            continue
        replicas, why = _previous_replicas(ev, d)
        out.append(
            _dx(
                "scaled_to_zero",
                "scaling",
                f"deployment/{d['name']}",
                f"deployment {d['name']} was scaled down to 0 replicas (it used to run {replicas})",
                ["spec.replicas=0, no pods exist", why],
                [{"action": "scale_deployment", "name": d["name"], "replicas": replicas}],
            )
        )
    return out


# --- rule 2: a referenced Secret/ConfigMap does not exist (dev-08) -> human ------------------
def missing_reference(ev):
    seen, out = set(), []
    for p in ev["pods"]:
        for c in p["containers"]:
            m = NOT_FOUND.search(c["message"] or "")
            if c["reason"] != "CreateContainerConfigError" or not m:
                continue
            kind, name = m.groups()
            if (kind, name) in seen:
                continue
            seen.add((kind, name))
            d = _deployment_of(ev, p)
            out.append(
                _dx(
                    "missing_reference",
                    "config",
                    f"deployment/{d['name']}" if d else f"pod/{p['name']}",
                    f"{kind} '{name}' does not exist, so pods cannot start; its contents cannot be recovered automatically",
                    [f"pod {p['name']}: CreateContainerConfigError: {c['message']}"],
                    escalate=True,
                    confidence=0.95,
                )
            )
    return out


# --- rule 3: a config key is misspelled (dev-02) ---------------------------------------------
def config_key(ev):
    seen, out = set(), []
    for p in ev["pods"]:
        d = _deployment_of(ev, p)
        for log in ev["logs"].get(p["name"], {}).values():
            m = NOT_SET.search(log)
            if not m or not d:
                continue
            var = m.group(1)
            for cm_name in d["configmaps"]:
                cm = next((c for c in ev["configmaps"] if c["name"] == cm_name), None)
                if not cm or var in cm["keys"] or (cm_name, var) in seen:
                    continue
                close = difflib.get_close_matches(var, cm["keys"], n=1, cutoff=0.7)
                if not close:
                    continue
                seen.add((cm_name, var))
                out.append(
                    _dx(
                        "config_key",
                        "config",
                        f"configmap/{cm_name}",
                        f"ConfigMap {cm_name} has key '{close[0]}' but the app needs '{var}' (typo)",
                        [f"pod {p['name']} log: {log.splitlines()[-1]}", f"configmap keys: {cm['keys']}"],
                        [
                            {"action": "rename_configmap_key", "name": cm_name, "old": close[0], "new": var},
                            {"action": "restart_deployment", "name": d["name"]},
                        ],
                    )
                )
    return out


# --- rule 4: a new revision of a deployment is broken -> roll back (dev-01/03/04/05/07) -------
def _classify(ev, rs_name, pods):
    for p in pods:
        for c in p["containers"]:
            if c["reason"] in IMAGE_ERRORS:
                return "image", f"pod {p['name']}: {c['reason']} for image {c['image']}"
            if "OOMKilled" in (c["reason"], c["last_terminated_reason"]):
                return "resources", f"pod {p['name']}: container was OOMKilled (memory limit too low)"
    for p in pods:
        if p["phase"] == "Pending" and p["unschedulable"]:
            return "scheduling", f"pod {p['name']} cannot be scheduled: {p['unschedulable']}"
    for e in ev["events"]:
        if e["object"].startswith(f"pod/{rs_name}") and "probe failed" in e["message"].lower():
            return "probe", f"{e['object']}: {e['message']}"
    return "config", "the new revision is unhealthy (cause not classified)"


def template_regression(ev):
    out = []
    for d in ev["deployments"]:
        rss = d["replicasets"]
        if len(rss) < 2:
            continue
        old, new = rss[-2], rss[-1]
        pods = [p for p in ev["pods"] if p["replicaset"] == new["name"]]
        stuck = new["desired"] > 0 and new["ready"] < new["desired"]
        crashing = any(c["restarts"] > 0 for p in pods for c in p["containers"])
        if not (stuck or crashing):
            continue
        category, why = _classify(ev, new["name"], pods)
        evidence = [why, f"revision {new['revision']}: {new['ready']}/{new['desired']} ready"]
        if old["images"] != new["images"]:
            evidence.append(f"image changed: {old['images']} -> {new['images']}")
        out.append(
            _dx(
                "template_regression",
                category,
                f"deployment/{d['name']}",
                f"the latest rollout of {d['name']} is broken ({category}); the previous revision {old['revision']} was good",
                evidence,
                [{"action": "rollback_deployment", "name": d["name"]}],
            )
        )
    return out


# --- rule 5: a Service points at nothing (dev-06) -------------------------------------------
def service_selector(ev):
    out = []
    for s in ev["services"]:
        if not s["selector"] or s["selects_deployments"]:
            continue
        target = next((d for d in ev["deployments"] if d["name"] == s["name"]), None)
        new_selector = s["declared_selector"] or (target["selector"] if target else None)
        evidence = [
            f"service selector {s['selector']} matches no deployment's pod labels",
            f"ready endpoints: {s['ready_endpoints']}",
        ]
        if s["declared_selector"]:
            evidence.append(f"last-applied selector: {s['declared_selector']}")
        out.append(
            _dx(
                "service_selector",
                "networking",
                f"service/{s['name']}",
                f"service {s['name']} selects {s['selector']} but no pod has those labels",
                evidence,
                [{"action": "patch_service", "name": s["name"], "selector": new_selector}] if new_selector else [],
                escalate=not new_selector,
            )
        )
    return out


# --- rule 6: the logs blame something outside the cluster -> human --------------------------
def external_dependency(ev):
    seen, out = set(), []
    for p in ev["pods"]:
        d = _deployment_of(ev, p)
        for log in ev["logs"].get(p["name"], {}).values():
            for line in log.splitlines():
                if not EXTERNAL_ERROR.search(line):
                    continue
                for host in EXTERNAL_HOST.findall(line):
                    if host.lower() in seen:
                        continue
                    seen.add(host.lower())
                    out.append(
                        _dx(
                            "external_dependency",
                            "external",
                            f"deployment/{d['name']}" if d else f"pod/{p['name']}",
                            f"pod {p['name']} cannot reach {host}, which is outside the cluster; "
                            "nothing inside Kubernetes can fix that",
                            [f"log: {line.strip()[:200]}"],
                            escalate=True,
                            confidence=0.7,
                        )
                    )
    return out


RULES = [missing_reference, config_key, scaled_to_zero, template_regression, service_selector, external_dependency]


def diagnose(ev):
    """All findings, fixable ones first (escalations are handled last)."""
    found = [dx for rule in RULES for dx in rule(ev)]
    return sorted(found, key=lambda d: d["escalate"])

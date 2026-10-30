"""The closed action vocabulary.

Nabd (rules or LLM) can only ever ask for one of these actions. Raw kubectl text is never
accepted, so a model that hallucinates cannot run `kubectl delete`. Each action knows how to
build its own kubectl commands and how to snapshot/restore what it touches (for auto-rollback).
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import kube

NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")
KEY = re.compile(r"^[-._a-zA-Z0-9]+$")

SPECS = {
    "scale_deployment": {"kind": "deployment", "risk": "low", "fields": {"name", "replicas"}},
    "rollback_deployment": {"kind": "deployment", "risk": "low", "fields": {"name"}},
    "restart_deployment": {"kind": "deployment", "risk": "low", "fields": {"name"}},
    "patch_service": {"kind": "service", "risk": "medium", "fields": {"name", "selector", "target_port"}},
    "rename_configmap_key": {"kind": "configmap", "risk": "medium", "fields": {"name", "old", "new"}},
}


def fmt(a):
    args = ", ".join(f"{k}={v}" for k, v in a.items() if k != "action")
    return f"{a['action']}({args})"


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def validate(a):
    """Return an error string, or None when the action is well-formed."""
    if not isinstance(a, dict) or a.get("action") not in SPECS:
        return f"unknown action {a.get('action') if isinstance(a, dict) else a!r}"
    spec = SPECS[a["action"]]
    extra = set(a) - spec["fields"] - {"action"}
    if extra:
        return f"unexpected fields {sorted(extra)}"
    if not NAME.match(str(a.get("name", ""))):
        return "invalid resource name"
    if a["action"] == "scale_deployment" and not _is_int(a.get("replicas")):
        return "replicas must be an integer"
    if a["action"] == "patch_service":
        sel, port = a.get("selector"), a.get("target_port")
        if sel is None and port is None:
            return "patch_service needs a selector or a target_port"
        if sel is not None and not (
            isinstance(sel, dict) and sel and all(isinstance(k, str) and isinstance(v, str) for k, v in sel.items())
        ):
            return "selector must be a non-empty map of strings"
        if port is not None and not (_is_int(port) and 0 < port < 65536):
            return "target_port must be between 1 and 65535"
    if a["action"] == "rename_configmap_key" and not (KEY.match(str(a.get("old", ""))) and KEY.match(str(a.get("new", "")))):
        return "invalid key name"
    return None


def commands(ns, a):
    """The kubectl commands that implement the action (each one supports --dry-run=server)."""
    n, kind = a["name"], a["action"]
    if kind == "scale_deployment":
        return [["scale", "deployment", n, f"--replicas={a['replicas']}", "-n", ns]]
    if kind == "rollback_deployment":
        return [["rollout", "undo", f"deployment/{n}", "-n", ns]]
    if kind == "restart_deployment":
        # same thing `kubectl rollout restart` does, written as a patch so --dry-run=server works
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        patch = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": stamp}}}}}
        return [["patch", "deployment", n, "-n", ns, "-p", json.dumps(patch)]]
    if kind == "patch_service":
        ops = []
        if a.get("selector"):
            ops.append({"op": "replace", "path": "/spec/selector", "value": a["selector"]})
        if a.get("target_port"):
            ops.append({"op": "replace", "path": "/spec/ports/0/targetPort", "value": a["target_port"]})
        return [["patch", "service", n, "-n", ns, "--type=json", "-p", json.dumps(ops)]]
    if kind == "rename_configmap_key":
        data = kube.get_json(ns, "configmap", n).get("data") or {}
        if a["old"] not in data:
            raise kube.KubeError(f"configmap {n} has no key {a['old']}")
        ops = [
            {"op": "add", "path": f"/data/{a['new']}", "value": data[a["old"]]},
            {"op": "remove", "path": f"/data/{a['old']}"},
        ]
        return [["patch", "configmap", n, "-n", ns, "--type=json", "-p", json.dumps(ops)]]
    raise kube.KubeError(f"no implementation for {kind}")


def _run(ns, a, extra=()):
    for cmd in commands(ns, a):
        rc, out, err = kube.kubectl(*cmd, *extra)
        if rc != 0:
            return False, (err or out).strip()
    return True, ""


def dry_run(ns, a):
    return _run(ns, a, ["--dry-run=server"])


def apply(ns, a):
    return _run(ns, a)


def snapshot(ns, a):
    kind = SPECS[a["action"]]["kind"]
    return {"kind": kind, "name": a["name"], "obj": kube.get_json(ns, kind, a["name"])}


def restore(ns, snap):
    """Put an object back exactly as it was before the fix (the auto-rollback)."""
    obj = json.loads(json.dumps(snap["obj"]))
    meta = obj["metadata"]
    for k in ("resourceVersion", "uid", "creationTimestamp", "managedFields", "generation"):
        meta.pop(k, None)
    (meta.get("annotations") or {}).pop("deployment.kubernetes.io/revision", None)
    obj.pop("status", None)
    rc, out, err = kube.kubectl("replace", "-f", "-", "-n", ns, input_text=json.dumps(obj))
    return rc == 0, (err or out).strip()


# The "before" state is written to disk before any change, so even a crash or Ctrl+C in the middle of a
# multi-step fix can be undone on the next run: Nabd never leaves a half-applied change behind.
def _journal_path():
    return Path(os.environ.get("NABD_HOME") or Path.home() / ".nabd") / "journal.json"


def journal_save(ns, snaps):
    path = _journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"namespace": ns, "snapshots": snaps}))


def journal_load():
    path = _journal_path()
    return json.loads(path.read_text()) if path.exists() else None


def journal_clear():
    _journal_path().unlink(missing_ok=True)

"""Policy gate: what Nabd may do alone, what needs a human, and what is never allowed.

  auto     low-risk, reversible actions (scale, roll back, restart)
  approve  medium risk (edits to Services or ConfigMaps): a human must say yes
  deny     anything outside the allow-listed namespace or the action vocabulary, or out of bounds

Secrets, quotas, namespaces and nodes are not in the vocabulary at all, so they can never be touched.
"""
from . import actions

ALLOWED_NAMESPACES = {"demo", "gitops-demo"}
MAX_REPLICAS = 10


def _verdict(decision, risk, reason):
    return {"decision": decision, "risk": risk, "reason": reason}


def check(ns, action):
    if ns not in ALLOWED_NAMESPACES:
        return _verdict("deny", "high", f"namespace '{ns}' is not in the allow-list")
    error = actions.validate(action)
    if error:
        return _verdict("deny", "high", error)
    if action["action"] == "scale_deployment" and not 1 <= action["replicas"] <= MAX_REPLICAS:
        return _verdict("deny", "high", f"replicas must be between 1 and {MAX_REPLICAS}")
    risk = actions.SPECS[action["action"]]["risk"]
    if risk == "low":
        return _verdict("auto", risk, "low risk, reversible: runs automatically")
    return _verdict("approve", risk, "changes configuration: needs human approval")

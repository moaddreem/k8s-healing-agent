"""Incident report: a Markdown record of what Nabd saw, decided and changed.

Written after every run that found a problem. It is what the on-call engineer reads when Nabd
escalates, and the audit trail for every change the agent made.
"""
import re
from pathlib import Path

from .actions import fmt

REPORTS = Path(__file__).resolve().parent.parent / "reports"
OUTCOME = {"resolved": "Resolved", "escalated": "Escalated to a human", "plan": "Plan only, nothing applied"}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def write(res, transcript, findings, started, health_output, directory=None):
    """Write the report and return its path."""
    directory = Path(directory) if directory else REPORTS
    directory.mkdir(parents=True, exist_ok=True)
    target = findings[0]["target"] if findings else "no-diagnosis"
    path = directory / f"{started:%Y%m%d-%H%M%S}-{_UNSAFE.sub('-', target)}.md"

    applied = ", ".join(f"`{a}`" for a in res["applied"]) or "none"
    lines = [
        f"# Incident report: {target}",
        "",
        "| | |",
        "|---|---|",
        f"| Outcome | {OUTCOME.get(res['outcome'], res['outcome'])} |",
        f"| Namespace | `{res['namespace']}` |",
        f"| Mode | {res['mode']} |",
        f"| Started | {started:%Y-%m-%d %H:%M:%S} UTC |",
        f"| Duration | {res['seconds']} s |",
        f"| Changes applied | {applied} |",
        f"| Human approvals asked | {res['approvals']} |",
        f"| LLM calls | {res['llm_calls']} |",
        "",
    ]
    if res.get("escalation"):
        lines += ["## Why a human is needed", "", res["escalation"], ""]
        if res.get("rolled_back"):
            lines += ["Nabd rolled its own change back, so the cluster is as it was before the run.", ""]
        elif not res["applied"]:
            lines += ["Nabd did not change anything in the cluster.", ""]

    lines += ["## Diagnosis", ""]
    seen = set()
    for f in findings:
        key = (f["target"], f["rule"], f["summary"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{f['target']}** ({f['category']}, `{f['source']}:{f['rule']}`): {f['summary']}")
        lines += [f"  - {e}" for e in f["evidence"]]
        if f["fix"]:
            lines.append(f"  - proposed fix: {', '.join(f'`{fmt(a)}`' for a in f['fix'])}")
    if not findings:
        lines.append("No rule or model produced a diagnosis.")

    lines += ["", "## Timeline", "", "```", *transcript, "```", ""]
    lines += ["## Health check after the run", "", "```", health_output.strip() or "(no output)", "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

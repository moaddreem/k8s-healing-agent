"""The incident loop.

Detect -> Evidence -> Diagnose -> Policy gate -> (Approve) -> Dry-run -> Apply -> Verify -> Rollback -> Report
It never retries the same fix twice: if a fix did not help it is rolled back and a human is called.
When Argo CD or Flux deploys the app, Apply becomes a pull request in Git instead (see gitops.py).
"""
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import actions, evidence, gitops, guard, kube, policy, report, rules, verify

REPO = Path(__file__).resolve().parent.parent


def _sig(dx):
    return (dx["target"], tuple(json.dumps(a, sort_keys=True) for a in dx["fix"]))


def _workload(dx):
    """What a finding would change. Two findings about the same workload are one incident."""
    for a in dx["fix"]:
        if a["action"].endswith("_deployment"):
            return f"deployment/{a['name']}"
        if a["action"] == "patch_service":
            return f"service/{a['name']}"
    return dx["target"]


def _group(found):
    """One failure shows up as many symptoms: keep the first (most specific) finding per workload."""
    kept, seen = [], set()
    for d in found:
        key = _workload(d)
        if key not in seen:
            seen.add(key)
            kept.append(d)
    return kept


def _lock(ns):
    """Only one Nabd run may handle a namespace at a time, so one failure cannot start many fixers."""
    path = Path(os.environ.get("NABD_HOME") or Path.home() / ".nabd") / f"{ns}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _diagnose(ev, mode):
    """-> (findings, number of LLM calls)."""
    if mode == "rules":
        return rules.diagnose(ev), 0
    from . import llm

    if mode == "llm":
        return llm.diagnose(ev), 1
    found = rules.diagnose(ev)
    return (found, 0) if found else (llm.diagnose(ev), 1)


def _ask(approval, say):
    if approval == "yes":
        say("        approval: granted automatically (--yes)")
        return True
    if approval == "no":
        say("        approval: refused (--no-approve)")
        return False
    if not sys.stdin.isatty():
        say("        approval: no human available, refusing")
        return False
    return input("        ✋ Approve this change? [y/N] ").strip().lower() in ("y", "yes")


def run(ns="demo", mode="rules", approval="ask", plan_only=False, max_rounds=4, settle=60, say=print, write_report=True,
        gitops_repo=REPO, merge_timeout=900):
    t0 = time.time()
    started = datetime.now(timezone.utc)
    transcript, findings = [], []
    print_line = say

    def say(line):  # every line also goes into the incident report
        transcript.append(line)
        print_line(line)

    res = {
        "mode": mode,
        "namespace": ns,
        "outcome": None,
        "seconds": None,
        "diagnoses": [],
        "applied": [],
        "approvals": 0,
        "blocked": 0,
        "llm_calls": 0,
        "escalation": None,
        "rolled_back": False,
        "grouped": 0,
    }

    def step(icon, text):
        say(f"[{time.time() - t0:5.1f}s] {icon} {text}")

    def finish():
        if lock:
            lock.close()  # releases the namespace for the next run
        res["seconds"] = round(time.time() - t0, 1)
        if write_report and res["outcome"] in ("resolved", "escalated", "plan"):
            _, health_output = verify.check(ns)
            path = report.write(res, transcript, findings, started, health_output)
            res["report"] = str(path)
            print_line(f"📝 REPORT: {path}")
        return res

    def escalate(reason, dxs=()):
        res["outcome"], res["escalation"] = "escalated", reason
        step("🧑‍⚕️", f"ESCALATING TO A HUMAN: {reason}")
        for d in dxs:
            say(f"        diagnosis: {d['summary']}")
        return finish()

    def undo(entry):
        for snap in reversed(entry["snaps"]):
            ok, err = actions.restore(ns, snap)
            step("↩️ ", f"ROLLBACK {snap['kind']}/{snap['name']}: {'restored' if ok else 'FAILED ' + err}")
        res["rolled_back"] = True

    def through_git(owner, dx):
        """The GitOps path: the same diagnosis, but the fix is a pull request and the approval is its merge."""
        tool = gitops.TOOL[owner["tool"]]
        res["gitops"] = f"{tool} (app '{owner['app']}')"
        step("🔀", f"GITOPS: {owner['kind']}/{owner['name']} is deployed by {res['gitops']}. "
                   "A change made on the cluster would be undone at the next sync, so the fix goes to Git")
        fix = None
        try:
            fix = gitops.prepare(owner, dx, gitops_repo)
            step("🌿", f"GIT: the last change to {', '.join(fix['files'])} is {fix['sha'][:7]} "
                       f"\"{fix['subject']}\" by {fix['author']}: reverting it on branch {fix['branch']}")
            ok, err = gitops.dry_run(fix)
            step("🧪", f"DRY-RUN the reverted manifests: {'ok' if ok else 'REJECTED ' + err}")
            if not ok:
                return escalate("the server-side dry-run rejected the reverted manifests", [dx])
            if plan_only:
                step("📝", "plan-only mode: the pull request was NOT opened")
                res["outcome"] = "plan"
                return finish()
            title = f"Nabd: fix {dx['target']} by reverting {fix['sha'][:7]}"
            url = res["pull_request"] = gitops.publish(fix, title, gitops.pr_body(dx, fix, owner))
            step("📬", f"PULL REQUEST: {url}")
            res["approvals"] += 1
            step("✋", "APPROVAL: waiting for a human to review and merge the pull request")
            state = gitops.wait_merged(url, fix["worktree"], merge_timeout)
        except (gitops.GitOpsError, kube.KubeError) as e:
            return escalate(f"could not prepare the fix in Git: {e}", [dx])
        finally:
            if fix:
                gitops.discard(gitops_repo, fix)
        if state == "CLOSED":
            return escalate("a human closed the pull request without merging it", [dx])
        if state != "MERGED":
            return escalate(f"nobody merged the pull request in time, it is still open: {url}", [dx])
        step("✋", "APPROVAL: the pull request was merged")
        res["applied"].append(f"git revert {fix['sha'][:7]} ({url})")
        ok, err = gitops.request_sync(owner)
        step("🔄", f"SYNC: asked {tool} to deploy the merged commit now" if ok else f"SYNC: could not nudge {tool} ({err}), waiting for its next poll")
        step("⏳", f"VERIFY: waiting for {tool} to deploy and the health check to pass")
        healthy, _ = verify.wait_healthy(max(settle, 300), ns=ns)
        if healthy:
            step("✅", "VERIFIED: the independent health check passes")
            res["outcome"] = "resolved"
            return finish()
        return escalate("the pull request was merged and deployed, but the app is still unhealthy", [dx])

    step("🫀", f"Nabd is watching namespace '{ns}' (mode: {mode})")
    lock = _lock(ns)
    if lock is None:
        step("🔒", "another Nabd run is already handling this namespace, not starting a second one")
        res["outcome"] = "busy"
        return finish()
    pending = actions.journal_load()
    if pending and pending["namespace"] == ns:
        step("♻️ ", "an earlier run was interrupted in the middle of a change: restoring the previous state first")
        for snap in reversed(pending["snapshots"]):
            ok, err = actions.restore(ns, snap)
            step("↩️ ", f"ROLLBACK {snap['kind']}/{snap['name']}: {'restored' if ok else 'FAILED ' + err}")
        actions.journal_clear()
    healthy, out = verify.check(ns)
    if healthy:
        step("✅", "everything is healthy, nothing to do")
        res["outcome"] = "healthy"
        return finish()
    failing = [line for line in out.splitlines() if line.startswith("❌")]
    step("🚨", f"DETECT: unhealthy, {len(failing)} failing check(s)")
    for line in failing:
        say(f"        {line}")

    attempted = {}
    for rnd in range(1, max_rounds + 1):
        step("🔍", f"EVIDENCE (round {rnd}): pods, events, logs, services")
        ev = evidence.collect(ns)
        found, calls = _diagnose(ev, mode)
        res["llm_calls"] += calls
        raw = len(found)
        found = _group(found)
        if len(found) < raw:
            res["grouped"] += raw - len(found)
            step("🧩", f"GROUP: {raw} findings point at {len(found)} incident(s), acting once per workload")
        for d in found:
            findings.append(d)
            res["diagnoses"].append(
                {"round": rnd, "source": d["source"], "rule": d["rule"], "category": d["category"],
                 "target": d["target"], "escalate": d["escalate"]}
            )
            step("🧠", f"DIAGNOSE [{d['source']}:{d['rule']}] {d['target']} -> {d['category']}")
            say(f"        {d['summary']}")
            for line in d["evidence"]:
                say(f"        - {line}")

        fixable = [d for d in found if d["fix"] and not d["escalate"]]
        todo = [d for d in fixable if _sig(d) not in attempted]
        if not todo:
            repeated = [d for d in fixable if _sig(d) in attempted]
            if repeated:
                for d in repeated:
                    undo(attempted[_sig(d)])
                return escalate("the fix was applied but the problem is still there; I rolled it back", repeated)
            if found:
                return escalate("this needs a human decision (it cannot be fixed safely by the agent)", found)
            return escalate("no diagnosis: I do not know how to fix this safely")

        dx = todo[0]
        if dx["source"] == "llm":
            problems = guard.check(ev, dx)
            for problem in problems:
                step("🚫", f"GUARD: {problem}")
            if problems:
                res["blocked"] += 1
                return escalate("the LLM proposed a fix that the evidence does not support (possible prompt injection)", [dx])
        verdicts = [policy.check(ns, a) for a in dx["fix"]]
        for a, v in zip(dx["fix"], verdicts):
            step("🛡️ ", f"POLICY {actions.fmt(a)} -> {v['decision']} (risk {v['risk']}): {v['reason']}")
        if any(v["decision"] == "deny" for v in verdicts):
            res["blocked"] += 1
            return escalate("the policy gate blocked the proposed fix", [dx])
        owner = gitops.find_manager(ns, dx)
        if owner:
            return through_git(owner, dx)
        if any(v["decision"] == "approve" for v in verdicts):
            res["approvals"] += 1
            approved = _ask(approval, say)
            step("✋", f"APPROVAL: {'granted' if approved else 'refused'}")
            if not approved:
                return escalate("a human did not approve the change", [dx])

        try:
            snaps = [actions.snapshot(ns, a) for a in dx["fix"]]
            for a in dx["fix"]:
                ok, err = actions.dry_run(ns, a)
                step("🧪", f"DRY-RUN {actions.fmt(a)}: {'ok' if ok else 'REJECTED ' + err}")
                if not ok:
                    return escalate("the server-side dry-run rejected the fix", [dx])
        except kube.KubeError as e:
            return escalate(f"could not prepare the fix: {e}", [dx])

        if plan_only:
            step("📝", "plan-only mode: the fix was NOT applied")
            res["outcome"] = "plan"
            return finish()

        entry = attempted[_sig(dx)] = {"dx": dx, "snaps": snaps}
        actions.journal_save(ns, snaps)
        try:
            for a in dx["fix"]:
                ok, err = actions.apply(ns, a)
                step("🔧", f"APPLY {actions.fmt(a)}: {'ok' if ok else 'FAILED ' + err}")
                if not ok:
                    undo(entry)
                    actions.journal_clear()
                    return escalate("applying the fix failed, nothing is left half-applied", [dx])
                res["applied"].append(actions.fmt(a))
        except BaseException:
            undo(entry)
            actions.journal_clear()
            raise
        actions.journal_clear()

        step("⏳", "VERIFY: waiting for the health check to pass")
        healthy, out = verify.wait_healthy(settle, ns=ns)
        if healthy:
            step("✅", "VERIFIED: the independent health check passes")
            res["outcome"] = "resolved"
            return finish()
        step("⚠️ ", "still unhealthy, looking at the evidence again")

    return escalate("gave up after the maximum number of rounds")

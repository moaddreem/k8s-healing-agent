"""GitOps mode: when Argo CD or Flux deploys an app, Nabd fixes Git, not the cluster.

With GitOps, Git is the source of truth. A patch made straight on the cluster is undone at the next
sync, or leaves the cluster quietly different from Git. So for an app that Argo CD or Flux deploys,
Nabd keeps the same diagnosis and the same safety rules, but the fix becomes a pull request that
reverts the commit that broke the app. A human merging the pull request is the approval; Argo CD or
Flux deploys it; Nabd checks the result with the same health check as always.

Nabd never touches the checkout it runs from: the fix is made in a temporary git worktree.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from . import actions, kube

ARGO_TRACKING = "argocd.argoproj.io/tracking-id"  # Argo CD 3.x tracks what it deploys with this annotation
ARGO_INSTANCE = "argocd.argoproj.io/instance"
FLUX_NAME = "kustomize.toolkit.fluxcd.io/name"
FLUX_NAMESPACE = "kustomize.toolkit.fluxcd.io/namespace"
ARGO_NAMESPACE = os.environ.get("NABD_ARGOCD_NAMESPACE", "argocd")
TOOL = {"argocd": "Argo CD", "flux": "Flux"}
SIGNATURE = "Nabd:"  # every commit Nabd writes starts with this, so it never reverts its own fix
IDENTITY = {"GIT_AUTHOR_NAME": "Nabd", "GIT_AUTHOR_EMAIL": "nabd@localhost",
            "GIT_COMMITTER_NAME": "Nabd", "GIT_COMMITTER_EMAIL": "nabd@localhost"}


class GitOpsError(RuntimeError):
    pass


def manager(obj):
    """Who deploys this object? -> {"tool", "app", "namespace"} for Argo CD or Flux, else None."""
    meta = obj.get("metadata") or {}
    annotations, labels = meta.get("annotations") or {}, meta.get("labels") or {}
    tracking = annotations.get(ARGO_TRACKING)
    if tracking:
        app = tracking.split(":", 1)[0]
        ns, _, name = app.rpartition("_")  # an app outside the Argo CD namespace is written "<ns>_<app>"
        return {"tool": "argocd", "app": name, "namespace": ns or ARGO_NAMESPACE}
    if labels.get(ARGO_INSTANCE):
        return {"tool": "argocd", "app": labels[ARGO_INSTANCE], "namespace": ARGO_NAMESPACE}
    if labels.get(FLUX_NAME):
        return {"tool": "flux", "app": labels[FLUX_NAME], "namespace": labels.get(FLUX_NAMESPACE, "flux-system")}
    return None  # app.kubernetes.io/instance alone is not enough: Helm sets it too


def find_manager(ns, dx):
    """The GitOps tool that deploys what this fix would change, or None (then Nabd fixes the cluster as usual)."""
    for a in dx["fix"]:
        kind = actions.SPECS[a["action"]]["kind"]
        try:
            owner = manager(kube.get_json(ns, kind, a["name"]))
        except kube.KubeError:
            continue
        if owner:
            return {**owner, "kind": kind, "name": a["name"]}
    return None


def source(owner):
    """Where the app lives in Git -> {"url", "branch", "path"}, read from the Argo CD Application or Flux Kustomization."""
    if owner["tool"] == "argocd":
        app = kube.get_json(owner["namespace"], "applications.argoproj.io", owner["app"])
        spec, sync = app["spec"], (app.get("status") or {}).get("sync") or {}
        src = spec.get("source") or (spec.get("sources") or [{}])[0]
        return {"url": src.get("repoURL", ""), "branch": src.get("targetRevision") or "HEAD", "path": _clean_path(src.get("path")),
                "in_sync": sync.get("status") != "OutOfSync", "deployed": sync.get("revision")}
    spec = kube.get_json(owner["namespace"], "kustomizations.kustomize.toolkit.fluxcd.io", owner["app"])["spec"]
    ref = spec["sourceRef"]
    repo = kube.get_json(ref.get("namespace", owner["namespace"]), "gitrepositories.source.toolkit.fluxcd.io", ref["name"])
    owner["flux_source"] = (ref.get("namespace", owner["namespace"]), ref["name"])
    return {"url": repo["spec"]["url"], "branch": (repo["spec"].get("ref") or {}).get("branch", "HEAD"), "path": _clean_path(spec.get("path"))}


def _clean_path(path):
    path = re.sub(r"^\./", "", (path or "").strip()).strip("/")
    return "" if path == "." else path


def _git(repo, *args, check=True, env=None):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120,
                       env={**os.environ, **(env or {})})
    if check and p.returncode != 0:
        raise GitOpsError(f"git {' '.join(args[:2])}: {(p.stderr or p.stdout).strip()}")
    return p.stdout.strip()


def normal_url(url):
    """https://github.com/a/b.git and git@github.com:a/b are the same repository."""
    url = re.sub(r"^[a-z+]+://", "", url.strip().lower())
    url = re.sub(r"^[^@/]+@", "", url).replace(":", "/", 1)
    return re.sub(r"(\.git)?/*$", "", url)


def _remote(repo, url):
    """The remote of the local clone that points at the app's repository."""
    for name in _git(repo, "remote").split():
        if normal_url(_git(repo, "remote", "get-url", name)) == normal_url(url):
            return name
    raise GitOpsError(f"the clone at {repo} has no remote for {url}, so Nabd cannot propose a fix there")


def _branch(repo, remote, rev):
    if rev in ("", "HEAD"):
        head = _git(repo, "ls-remote", "--symref", remote, "HEAD").splitlines()
        return head[0].split()[1].removeprefix("refs/heads/") if head and head[0].startswith("ref:") else "main"
    if not _git(repo, "ls-remote", "--heads", remote, rev):
        raise GitOpsError(f"the app is pinned to '{rev}', which is not a branch; a pull request cannot change it")
    return rev


def declares(text, kind, name):
    """Does this YAML file declare <kind>/<name>? (A small reader: Nabd has no YAML dependency.)"""
    for doc in re.split(r"^---[ \t]*$", text, flags=re.M):
        k = re.search(r"^kind:[ \t]*(\S+)", doc, re.M)
        block = re.search(r"^metadata:[ \t]*\n((?:[ \t]+\S.*\n?)+)", doc, re.M)
        if not (k and block) or k.group(1).lower() != kind:
            continue
        indent = re.match(r"[ \t]+", block.group(1)).group(0)
        n = re.search(rf"^{indent}name:[ \t]*['\"]?([^'\"\s#]+)", block.group(1), re.M)
        if n and n.group(1) == name:
            return True
    return False


def _is_ancestor(repo, older, newer):
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer], capture_output=True).returncode == 0


def revert_last_change(repo, base, app_path, targets, reason, deployed=None):
    """On a new branch in a temporary worktree, revert the commit that last changed `targets`.

    base: the ref the app is deployed from (e.g. origin/gitops-lab). targets: [(kind, name)].
    deployed: the commit the GitOps tool says is running, when it says so.
    Refuses (GitOpsError) when the commit is Nabd's own, a merge, not deployed yet, or reaches outside the app.
    """
    files = _git(repo, "ls-tree", "-r", "--name-only", base, "--", app_path or ".").splitlines()
    owned = [
        f for f in files
        if f.endswith((".yaml", ".yml")) and any(declares(_git(repo, "show", f"{base}:{f}"), k, n) for k, n in targets)
    ]
    wanted = ", ".join(f"{k}/{n}" for k, n in targets)
    if not owned:
        raise GitOpsError(f"no file under '{app_path or '.'}' declares {wanted}")
    line = _git(repo, "log", "-1", "--format=%H%x09%an%x09%s", base, "--", *owned)
    sha, author, subject = line.split("\t", 2)
    if subject.startswith(SIGNATURE):
        raise GitOpsError(f"the last change to {wanted} is Nabd's own fix ({sha[:7]}), so a human has to look")
    if len(_git(repo, "rev-list", "--parents", "-n", "1", sha).split()) > 2:
        raise GitOpsError(f"commit {sha[:7]} is a merge, so a human has to choose what to revert")
    if deployed and not _is_ancestor(repo, sha, deployed):
        raise GitOpsError(f"commit {sha[:7]} is not deployed yet (the cluster runs {deployed[:7]}), so it cannot be what broke the app")
    changed = _git(repo, "show", "--name-only", "--format=", sha).splitlines()
    outside = [f for f in changed if app_path and not f.startswith(app_path + "/")]
    if outside:
        raise GitOpsError(f"commit {sha[:7]} also changes files outside the app ({', '.join(outside)}), so reverting it is not a small, safe fix")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fix = {"sha": sha, "author": author, "subject": subject, "files": owned, "changed": changed,
           "branch": f"nabd/revert-{sha[:7]}-{stamp}", "worktree": tempfile.mkdtemp(prefix="nabd-gitops-")}
    _git(repo, "worktree", "add", "--quiet", "-b", fix["branch"], fix["worktree"], base)
    try:
        _git(fix["worktree"], "revert", "--no-commit", sha)
        message = f'{SIGNATURE} revert "{subject}"\n\nThis reverts commit {sha}.\n\nDiagnosis: {reason}\n'
        _git(fix["worktree"], "commit", "--quiet", "-m", message, env=IDENTITY)
    except GitOpsError:
        discard(repo, fix)
        raise
    return fix


def prepare(owner, dx, repo):
    """Find the app in Git, fetch it, and prepare the revert on a new local branch (nothing is pushed)."""
    src = source(owner)
    if not src.get("in_sync", True):
        raise GitOpsError(f"{TOOL[owner['tool']]} says the cluster differs from Git, so the problem did not come from a commit "
                          "and there is nothing to revert; someone may have changed the cluster by hand")
    remote = _remote(repo, src["url"])
    branch = _branch(repo, remote, src["branch"])
    _git(repo, "fetch", "--quiet", remote, branch)
    targets = [(actions.SPECS[a["action"]]["kind"], a["name"]) for a in dx["fix"]]
    fix = revert_last_change(repo, f"{remote}/{branch}", src["path"], targets, dx["summary"], src.get("deployed"))
    fix.update(remote=remote, base=branch, url=src["url"], path=src["path"])
    return fix


def dry_run(fix):
    """Send the reverted manifests to the API server with --dry-run=server: would the cluster accept them?"""
    for f in fix["changed"]:
        rc, out, err = kube.kubectl("apply", "--dry-run=server", "-f", str(Path(fix["worktree"]) / f))
        if rc != 0:
            return False, (err or out).strip()
    return True, ""


def pr_body(dx, fix, owner):
    tool = TOOL[owner["tool"]]
    return "\n".join([
        f"**Nabd found a broken app and proposes this fix.** Merging this pull request is the approval: "
        f"{tool} will deploy it, then Nabd checks that the app is healthy again.",
        "",
        "### What is wrong",
        f"- **{dx['target']}**: {dx['summary']}",
        *[f"  - {e}" for e in dx["evidence"]],
        "",
        "### The fix",
        f"Revert `{fix['sha'][:7]}` \"{fix['subject']}\" by {fix['author']}, the last change to "
        + ", ".join(f"`{f}`" for f in fix["files"]) + ".",
        "",
        "### Checks Nabd already ran",
        "- The reverted manifests pass a server-side dry-run on the cluster.",
        "- The reverted commit only changes files of this app.",
        "",
        "_Opened by Nabd (نبض): https://nabd.duraym.com_",
    ])


def _gh(*args, cwd):
    gh = os.environ.get("NABD_GH", "gh")
    if not shutil.which(gh):
        raise GitOpsError("the GitHub CLI (gh) is not installed, so the pull request cannot be opened")
    p = subprocess.run([gh, *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise GitOpsError(f"gh {args[0]} {args[1]}: {(p.stderr or p.stdout).strip()}")
    return p.stdout.strip()


def publish(fix, title, body):
    """Push the branch and open the pull request. -> its URL."""
    _git(fix["worktree"], "push", "--quiet", fix["remote"], f"HEAD:refs/heads/{fix['branch']}")
    out = _gh("pr", "create", "--base", fix["base"], "--head", fix["branch"], "--title", title, "--body", body, cwd=fix["worktree"])
    return out.splitlines()[-1]


def wait_merged(url, cwd, timeout, interval=10):
    """Wait for a human to merge or close the pull request. -> MERGED, CLOSED or OPEN (timed out)."""
    start = time.time()
    while True:
        state = _gh("pr", "view", url, "--json", "state", "-q", ".state", cwd=cwd)
        if state in ("MERGED", "CLOSED") or time.time() - start > timeout:
            return state
        time.sleep(interval)


def request_sync(owner):
    """Ask Argo CD or Flux to read Git now instead of at its next poll (what `argocd app get --refresh`
    and `flux reconcile` do). It is an annotation on the GitOps object and changes nothing the app runs."""
    if owner["tool"] == "argocd":
        targets = [("applications.argoproj.io", owner["namespace"], owner["app"], "argocd.argoproj.io/refresh=normal")]
    else:
        stamp = f"reconcile.fluxcd.io/requestedAt={datetime.now(timezone.utc).isoformat(timespec='seconds')}"
        src_ns, src_name = owner.get("flux_source") or (owner["namespace"], owner["app"])
        targets = [("gitrepositories.source.toolkit.fluxcd.io", src_ns, src_name, stamp),
                   ("kustomizations.kustomize.toolkit.fluxcd.io", owner["namespace"], owner["app"], stamp)]
    for kind, ns, name, note in targets:
        rc, out, err = kube.kubectl("annotate", kind, name, "-n", ns, note, "--overwrite")
        if rc != 0:
            return False, (err or out).strip()
    return True, ""


def discard(repo, fix, keep_branch=False):
    """Remove the temporary worktree (and the local branch, unless it should stay for a human)."""
    _git(repo, "worktree", "remove", "--force", fix["worktree"], check=False)
    shutil.rmtree(fix["worktree"], ignore_errors=True)
    if not keep_branch:
        _git(repo, "branch", "-D", fix["branch"], check=False)

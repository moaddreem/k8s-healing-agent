"""GitOps mode: who deploys an object, and the fix as a revert of the commit that broke the app.

Offline: a throwaway Git repository, no cluster and no GitHub.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nabd import gitops

WEB = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: gitops-demo
  labels:
    app: web
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: nginx
          image: {image}
---
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: gitops-demo
spec:
  selector:
    app: web
"""
GOOD, BAD = "nginx:1.27-alpine", "nginx:1.27-alpinee"
DEV = {"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@example.com",
       "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@example.com",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class WhoDeploysIt(unittest.TestCase):
    def test_argo_cd_tracking_annotation_names_the_application(self):
        obj = {"metadata": {"annotations": {gitops.ARGO_TRACKING: "nabd-gitops:apps/Deployment:gitops-demo/web"}}}
        self.assertEqual(gitops.manager(obj), {"tool": "argocd", "app": "nabd-gitops", "namespace": "argocd"})

    def test_flux_labels_name_the_kustomization(self):
        obj = {"metadata": {"labels": {gitops.FLUX_NAME: "apps", gitops.FLUX_NAMESPACE: "flux-system"}}}
        self.assertEqual(gitops.manager(obj), {"tool": "flux", "app": "apps", "namespace": "flux-system"})

    def test_a_plain_or_helm_object_is_not_gitops(self):
        self.assertIsNone(gitops.manager({"metadata": {"labels": {"app.kubernetes.io/instance": "web"}}}))
        self.assertIsNone(gitops.manager({}))

    def test_repository_urls_match_across_https_and_ssh(self):
        a = gitops.normal_url("https://github.com/moaddreem/k8s-healing-agent.git")
        self.assertEqual(a, gitops.normal_url("git@github.com:moaddreem/k8s-healing-agent"))
        self.assertNotEqual(a, gitops.normal_url("https://github.com/someone-else/k8s-healing-agent"))

    def test_finds_which_file_declares_an_object(self):
        text = WEB.format(image=GOOD)
        self.assertTrue(gitops.declares(text, "deployment", "web"))
        self.assertTrue(gitops.declares(text, "service", "web"))
        self.assertFalse(gitops.declares(text, "configmap", "web"))
        self.assertFalse(gitops.declares(text, "deployment", "api"))


class RevertTheBadCommit(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, DEV)
        env.start()
        self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "--quiet", "--initial-branch=main")
        self.commit({"app/web.yaml": WEB.format(image=GOOD)}, "Add the web app")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True).stdout

    def commit(self, files, message):
        for name, text in files.items():
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text(text)
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)

    def revert(self):
        return gitops.revert_last_change(self.repo, "main", "app", [("deployment", "web")], "the latest rollout of web is broken")

    def test_reverts_the_commit_that_broke_the_app_on_its_own_branch(self):
        self.commit({"app/web.yaml": WEB.format(image=BAD)}, "Update web image")
        self.commit({"README.md": "docs\n"}, "Fix a typo in the docs")  # newer, but unrelated
        deployed = self.git("rev-parse", "HEAD").strip()
        fix = gitops.revert_last_change(self.repo, "main", "app", [("deployment", "web")], "broken", deployed=deployed)
        try:
            self.assertEqual(fix["subject"], "Update web image")
            self.assertEqual(fix["files"], ["app/web.yaml"])
            fixed = (Path(fix["worktree"]) / "app/web.yaml").read_text()
            self.assertIn(f"image: {GOOD}\n", fixed)
            self.assertNotIn(BAD, fixed)
            message = self.git("log", "-1", "--format=%an|%s", fix["branch"]).strip()
            self.assertEqual(message, 'Nabd|Nabd: revert "Update web image"')
            # the checkout Nabd runs from is untouched: still on main, still broken
            self.assertIn(BAD, (self.repo / "app/web.yaml").read_text())
            self.assertEqual(self.git("branch", "--show-current").strip(), "main")
        finally:
            gitops.discard(self.repo, fix)
        self.assertFalse(Path(fix["worktree"]).exists())
        self.assertNotIn(fix["branch"], self.git("branch"))

    def test_refuses_a_commit_that_reaches_outside_the_app(self):
        self.commit({"app/web.yaml": WEB.format(image=BAD), "infra/database.yaml": "kind: StatefulSet\n"}, "Big change")
        with self.assertRaisesRegex(gitops.GitOpsError, "outside the app"):
            self.revert()

    def test_never_reverts_its_own_fix(self):
        self.commit({"app/web.yaml": WEB.format(image=BAD)}, 'Nabd: revert "Update web image"')
        with self.assertRaisesRegex(gitops.GitOpsError, "Nabd's own fix"):
            self.revert()

    def test_never_reverts_a_commit_that_is_not_deployed_yet(self):
        deployed = self.git("rev-parse", "HEAD").strip()
        self.commit({"app/web.yaml": WEB.format(image=BAD)}, "Update web image")
        with self.assertRaisesRegex(gitops.GitOpsError, "not deployed yet"):
            gitops.revert_last_change(self.repo, "main", "app", [("deployment", "web")], "broken", deployed=deployed)

    def test_says_so_when_no_file_declares_the_object(self):
        with self.assertRaisesRegex(gitops.GitOpsError, "declares deployment/api"):
            gitops.revert_last_change(self.repo, "main", "app", [("deployment", "api")], "broken")


class TheAgentGoesThroughGit(unittest.TestCase):
    """The whole loop with the cluster and GitHub replaced by stand-ins: the fix must be a pull request."""
    DX = {"target": "deployment/web", "category": "image", "source": "rules", "rule": "template_regression",
          "summary": "the latest rollout of web is broken (image)", "evidence": [f"image changed: {GOOD} -> {BAD}"],
          "fix": [{"action": "rollback_deployment", "name": "web"}], "escalate": False}
    OWNER = {"tool": "argocd", "app": "nabd-gitops", "namespace": "argocd", "kind": "deployment", "name": "web"}
    URL = "https://github.com/example/repo/pull/7"

    def run_agent(self, merge_state):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fix = {"sha": "abc1234def", "author": "Dev", "subject": "Update web image", "files": ["app/web.yaml"],
               "changed": ["app/web.yaml"], "branch": "nabd/revert-abc1234", "worktree": tmp.name}
        from nabd import actions, agent, evidence, rules, verify

        patches = [
            mock.patch.dict(os.environ, {"NABD_HOME": tmp.name}),
            mock.patch.object(verify, "check", return_value=(False, "❌ deploy/web -> rollout not healthy")),
            mock.patch.object(verify, "wait_healthy", return_value=(True, "STATUS: HEALTHY")),
            mock.patch.object(evidence, "collect", return_value={}),
            mock.patch.object(rules, "diagnose", return_value=[dict(self.DX)]),
            mock.patch.object(gitops, "find_manager", return_value=dict(self.OWNER)),
            mock.patch.object(gitops, "prepare", return_value=fix),
            mock.patch.object(gitops, "dry_run", return_value=(True, "")),
            mock.patch.object(gitops, "publish", return_value=self.URL),
            mock.patch.object(gitops, "wait_merged", return_value=merge_state),
            mock.patch.object(gitops, "request_sync", return_value=(True, "")),
            mock.patch.object(gitops, "discard"),
            mock.patch.object(actions, "apply", side_effect=AssertionError("patched the cluster directly")),
            mock.patch.object(actions, "dry_run", side_effect=AssertionError("dry-ran a cluster patch")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return agent.run("gitops-demo", say=lambda line: None, write_report=False, gitops_repo=tmp.name)

    def test_a_merged_pull_request_resolves_the_incident(self):
        res = self.run_agent("MERGED")
        self.assertEqual(res["outcome"], "resolved")
        self.assertEqual(res["pull_request"], self.URL)
        self.assertEqual(res["applied"], [f"git revert abc1234 ({self.URL})"])
        self.assertEqual(res["approvals"], 1)
        self.assertIn("Argo CD", res["gitops"])

    def test_a_closed_pull_request_changes_nothing(self):
        res = self.run_agent("CLOSED")
        self.assertEqual(res["outcome"], "escalated")
        self.assertIn("closed the pull request", res["escalation"])
        self.assertEqual(res["applied"], [])


if __name__ == "__main__":
    unittest.main()

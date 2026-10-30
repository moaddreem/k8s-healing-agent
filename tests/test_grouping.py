"""One failure must not trigger many actions. Offline tests (no cluster needed)."""
import os
import tempfile
import unittest

from nabd import agent


def finding(target, *fix, escalate=False):
    return {"target": target, "fix": list(fix), "escalate": escalate}


class Grouping(unittest.TestCase):
    def test_two_symptoms_of_one_workload_become_one_incident(self):
        typo = finding(
            "configmap/api-config",
            {"action": "rename_configmap_key", "name": "api-config", "old": "GREETNG", "new": "GREETING"},
            {"action": "restart_deployment", "name": "api"},
        )
        crashing = finding("deployment/api", {"action": "rollback_deployment", "name": "api"})
        self.assertEqual(agent._group([typo, crashing]), [typo])

    def test_different_workloads_stay_separate(self):
        web = finding("service/web", {"action": "patch_service", "name": "web", "selector": {"app": "web"}})
        worker = finding("deployment/worker", {"action": "rollback_deployment", "name": "worker"})
        self.assertEqual(agent._group([web, worker]), [web, worker])

    def test_a_service_and_a_deployment_with_the_same_name_are_not_confused(self):
        svc = finding("service/web", {"action": "patch_service", "name": "web", "selector": {"app": "web"}})
        dep = finding("deployment/web", {"action": "rollback_deployment", "name": "web"})
        self.assertEqual(len(agent._group([svc, dep])), 2)


class OneRunAtATime(unittest.TestCase):
    def test_a_second_run_on_the_same_namespace_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["NABD_HOME"] = tmp
            try:
                first = agent._lock("demo")
                self.assertIsNotNone(first)
                self.assertIsNone(agent._lock("demo"))
                first.close()
                again = agent._lock("demo")
                self.assertIsNotNone(again)
                again.close()
            finally:
                del os.environ["NABD_HOME"]


if __name__ == "__main__":
    unittest.main()

"""The safety promises, as tests. Run: python3 -m unittest discover -s tests -t . -v"""
import unittest

from nabd import actions, policy


def decision(action, ns="demo"):
    return policy.check(ns, action)["decision"]


class PolicyGate(unittest.TestCase):
    def test_low_risk_actions_run_automatically(self):
        self.assertEqual(decision({"action": "rollback_deployment", "name": "web"}), "auto")
        self.assertEqual(decision({"action": "scale_deployment", "name": "web", "replicas": 2}), "auto")
        self.assertEqual(decision({"action": "restart_deployment", "name": "api"}), "auto")

    def test_config_and_network_changes_need_a_human(self):
        self.assertEqual(decision({"action": "patch_service", "name": "web", "selector": {"app": "web"}}), "approve")
        self.assertEqual(
            decision({"action": "rename_configmap_key", "name": "api-config", "old": "GREETNG", "new": "GREETING"}),
            "approve",
        )

    def test_other_namespaces_are_off_limits(self):
        self.assertEqual(decision({"action": "rollback_deployment", "name": "coredns"}, ns="kube-system"), "deny")

    def test_actions_outside_the_vocabulary_are_denied(self):
        for name in ("delete_namespace", "delete_secret", "exec", "kubectl"):
            self.assertEqual(decision({"action": name, "name": "demo"}), "deny", name)

    def test_raw_kubectl_text_is_never_accepted(self):
        self.assertEqual(decision({"action": "kubectl", "cmd": "delete ns demo"}), "deny")
        self.assertEqual(decision({"action": "rollback_deployment", "name": "web", "cmd": "delete ns demo"}), "deny")

    def test_shell_tricks_in_names_are_denied(self):
        self.assertEqual(decision({"action": "rollback_deployment", "name": "web; rm -rf /"}), "deny")
        self.assertEqual(decision({"action": "rollback_deployment", "name": "../secret"}), "deny")

    def test_scaling_must_stay_in_bounds(self):
        for replicas in (0, -1, 1000):
            self.assertEqual(decision({"action": "scale_deployment", "name": "web", "replicas": replicas}), "deny")
        self.assertEqual(decision({"action": "scale_deployment", "name": "web", "replicas": True}), "deny")

    def test_service_patch_needs_something_to_patch(self):
        self.assertEqual(decision({"action": "patch_service", "name": "web"}), "deny")
        self.assertEqual(decision({"action": "patch_service", "name": "web", "target_port": 70000}), "deny")


class ActionVocabulary(unittest.TestCase):
    def test_every_action_is_valid_with_good_input(self):
        self.assertIsNone(actions.validate({"action": "rollback_deployment", "name": "web"}))

    def test_secrets_and_quotas_are_not_in_the_vocabulary(self):
        for forbidden in ("secret", "resourcequota", "namespace", "node"):
            self.assertNotIn(forbidden, {s["kind"] for s in actions.SPECS.values()})


if __name__ == "__main__":
    unittest.main()

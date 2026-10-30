"""The incident report records outcome, diagnosis, changes and timeline. Offline, no cluster."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nabd import report

STARTED = datetime(2026, 10, 31, 10, 20, 5, tzinfo=timezone.utc)


def result(**over):
    base = {
        "outcome": "resolved", "namespace": "demo", "mode": "rules", "seconds": 3.1,
        "applied": ["rollback_deployment(name=web)"], "approvals": 0, "llm_calls": 0,
        "escalation": None, "rolled_back": False,
    }
    base.update(over)
    return base


def finding(**over):
    base = {
        "target": "deployment/web", "category": "image", "source": "rules", "rule": "template_regression",
        "summary": "the latest rollout of web is broken (image)",
        "evidence": ["image changed: nginx:1.27-alpine -> nginx:1.27-alpinee"],
        "fix": [{"action": "rollback_deployment", "name": "web"}],
    }
    base.update(over)
    return base


class IncidentReport(unittest.TestCase):
    def write(self, res, findings, health):
        with tempfile.TemporaryDirectory() as tmp:
            path = report.write(res, ["[  0.0s] DETECT: unhealthy"], findings, STARTED, health, directory=tmp)
            return path.name, Path(path).read_text(encoding="utf-8")

    def test_a_resolved_incident_records_what_happened(self):
        name, text = self.write(result(), [finding()], "STATUS: HEALTHY")
        self.assertTrue(name.startswith("20261031-102005-deployment-web"))
        for part in ("Resolved", "deployment/web", "`rollback_deployment(name=web)`", "nginx:1.27-alpinee", "## Timeline", "STATUS: HEALTHY"):
            self.assertIn(part, text)

    def test_an_escalation_says_why_and_that_nothing_changed(self):
        res = result(outcome="escalated", applied=[], escalation="this needs a human decision")
        f = finding(target="deployment/api", rule="missing_reference", category="config", fix=[], summary="secret 'api-secret' does not exist")
        _, text = self.write(res, [f], "STATUS: UNHEALTHY")
        self.assertIn("## Why a human is needed", text)
        self.assertIn("this needs a human decision", text)
        self.assertIn("did not change anything", text)


if __name__ == "__main__":
    unittest.main()

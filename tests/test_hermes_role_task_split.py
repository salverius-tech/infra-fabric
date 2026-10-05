from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "infra/ansible/roles/hermes/tasks"
EXPECTED = (
    ("preflight.yml", "Validate Hermes required variables"),
    ("host-runtime.yml", "Install Caddy package and service prerequisites"),
    ("application-runtime.yml", "Install Hermes landing page"),
    ("configuration.yml", "Verify active Hermes messaging imports"),
    ("verification.yml", "Flush Hermes service restarts before endpoint checks"),
)


class HermesRoleTaskSplitTests(unittest.TestCase):
    def test_main_imports_ordered_task_groups(self) -> None:
        manifest = yaml.safe_load((TASKS / "main.yml").read_text(encoding="utf-8"))
        imported = [task["ansible.builtin.import_tasks"] for task in manifest]

        self.assertEqual(imported, [name for name, _ in EXPECTED])
        for filename, first_task in EXPECTED:
            tasks = yaml.safe_load((TASKS / filename).read_text(encoding="utf-8"))
            self.assertIsInstance(tasks, list)
            self.assertTrue(tasks)
            self.assertEqual(tasks[0]["name"], first_task)


if __name__ == "__main__":
    unittest.main()

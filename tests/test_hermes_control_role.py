from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PARENT_TASKS = ROOT / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml"
CONTROL_TASKS = ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "tasks" / "main.yml"
CONTROL_API_ENV = ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "templates" / "api.env.j2"
GATEWAY_UNIT = ROOT / "infra" / "ansible" / "roles" / "hermes" / "templates" / "hermes-gateway.service.j2"


class HermesControlRoleTests(unittest.TestCase):
    def test_parent_configures_control_after_caddy_is_active(self) -> None:
        text = PARENT_TASKS.read_text(encoding="utf-8")
        self.assertLess(text.index("Verify Hermes Caddy service is active"), text.index("Configure optional Hermes Control companion stack"))
        self.assertLess(text.index("Configure optional Hermes Control companion stack"), text.index("Verify Hermes Control HTTPS health through Caddy"))

    def test_control_role_enforces_pinned_source_and_readiness(self) -> None:
        text = CONTROL_TASKS.read_text(encoding="utf-8")
        for fragment in (
            "hermes_control_source_ref is match('^[0-9a-f]{40}$')",
            "Flush Hermes Control service changes before readiness checks",
            "bridge socket accepts connections",
            "Verify authenticated Hermes Control diagnostics",
        ):
            self.assertIn(fragment, text)
        self.assertIn("no_log: true", text)
        self.assertIn("changed_when: true\n  notify: Restart hermes gateway", text)
        self.assertIn("CONTROL_API_REQUIRE_TASK_APPROVAL=1", CONTROL_API_ENV.read_text(encoding="utf-8"))
        self.assertIn("EnvironmentFile=-/etc/hermes-control/plugin.env", GATEWAY_UNIT.read_text(encoding="utf-8"))

    def test_restore_stops_are_inside_failure_safe_block(self) -> None:
        restore = (ROOT / "infra" / "ansible" / "playbooks" / "service-state-restore.yml").read_text(encoding="utf-8")
        block_start = restore.index("    - block:\n        - name: Stop managed system services before restore")
        self.assertLess(block_start, restore.index("      always:"))
        self.assertLess(restore.index("Stop managed user services before restore"), restore.index("      always:"))

    def test_control_role_yaml_is_parseable(self) -> None:
        self.assertIsInstance(yaml.safe_load(CONTROL_TASKS.read_text(encoding="utf-8")), list)


if __name__ == "__main__":
    unittest.main()

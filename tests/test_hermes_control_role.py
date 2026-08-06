from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT_TASKS = ROOT / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml"
CONTROL_TASKS = (
    ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "tasks" / "main.yml"
)
CONTROL_API_ENV = (
    ROOT
    / "infra"
    / "ansible"
    / "roles"
    / "hermes_control"
    / "templates"
    / "control-api.env.j2"
)
CONTROL_PLUGIN_ENV = (
    ROOT
    / "infra"
    / "ansible"
    / "roles"
    / "hermes_control"
    / "templates"
    / "plugin.env.j2"
)
CONTROL_DEFAULTS = (
    ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "defaults" / "main.yml"
)
CONTROL_ARGUMENT_SPECS = (
    ROOT
    / "infra"
    / "ansible"
    / "roles"
    / "hermes_control"
    / "meta"
    / "argument_specs.yml"
)
PARENT_ARGUMENT_SPECS = (
    ROOT / "infra" / "ansible" / "roles" / "hermes" / "meta" / "argument_specs.yml"
)
GATEWAY_UNIT = (
    ROOT
    / "infra"
    / "ansible"
    / "roles"
    / "hermes"
    / "templates"
    / "hermes-gateway.service.j2"
)
CADDYFILE = (
    ROOT / "infra" / "ansible" / "roles" / "hermes" / "templates" / "Caddyfile.j2"
)
OPERATIONS_DOC = ROOT / "docs" / "hermes-control-operations.md"


class HermesControlRoleTests(unittest.TestCase):
    def test_parent_configures_control_after_caddy_is_active(self) -> None:
        text = PARENT_TASKS.read_text(encoding="utf-8")
        self.assertLess(
            text.index("Verify Hermes Caddy service is active"),
            text.index("Configure optional Hermes Control companion stack"),
        )
        self.assertLess(
            text.index("Configure optional Hermes Control companion stack"),
            text.index("Verify Hermes Control HTTPS health through Caddy"),
        )

    def test_parent_control_diagnostics_use_templated_private_header(self) -> None:
        tasks = yaml.safe_load(PARENT_TASKS.read_text(encoding="utf-8"))
        diagnostic = next(
            task
            for task in tasks
            if task.get("name")
            == "Verify Hermes Control HTTPS diagnostics through Caddy"
        )
        header = diagnostic["ansible.builtin.command"]["argv"][10]
        self.assertEqual(header, "Authorization: Bearer {{ hermes_control_api_token }}")
        self.assertNotIn("***", header)
        self.assertTrue(diagnostic["no_log"])
        self.assertEqual(
            __import__("jinja2")
            .Template(header)
            .render(hermes_control_api_token="rendered-secret"),
            "Authorization: Bearer rendered-secret",
        )

    def test_hermes_control_and_parent_role_specs_cover_the_control_contract(
        self,
    ) -> None:
        child_options = yaml.safe_load(
            CONTROL_ARGUMENT_SPECS.read_text(encoding="utf-8")
        )["argument_specs"]["main"]["options"]
        parent_options = yaml.safe_load(
            PARENT_ARGUMENT_SPECS.read_text(encoding="utf-8")
        )["argument_specs"]["main"]["options"]
        defaults = yaml.safe_load(CONTROL_DEFAULTS.read_text(encoding="utf-8"))
        expected = {
            "hermes_runtime_user",
            "hermes_control_source_checkout_path",
            "hermes_control_install_dir",
            "hermes_control_config_dir",
            "hermes_control_state_dir",
            "hermes_control_api_host",
            "hermes_control_api_port",
            "hermes_control_domain",
            "hermes_control_require_task_approval",
            "hermes_control_source_url",
            "hermes_control_source_ref",
            "hermes_control_api_token",
            "hermes_control_bridge_token",
            "hermes_control_plugin_socket",
            "hermes_control_workspace_root",
            "hermes_control_project_roots",
        }
        self.assertTrue(expected <= set(child_options))
        self.assertTrue(set(defaults) <= set(child_options))
        self.assertTrue({"hermes_control_enabled", *expected} <= set(parent_options))
        self.assertEqual(child_options["hermes_control_api_port"]["type"], "int")
        self.assertEqual(
            child_options["hermes_control_require_task_approval"]["type"], "bool"
        )
        self.assertEqual(child_options["hermes_control_project_roots"]["type"], "list")
        self.assertIn(
            "hermes_control_project_roots is not string",
            CONTROL_TASKS.read_text(encoding="utf-8"),
        )
        for secret in ("hermes_control_api_token", "hermes_control_bridge_token"):
            self.assertTrue(child_options[secret]["required"])
            self.assertIn("never log", child_options[secret]["description"])

    def test_control_role_enforces_pinned_source_and_readiness(self) -> None:
        text = CONTROL_TASKS.read_text(encoding="utf-8")
        for fragment in (
            "ansible.builtin.git:",
            'version: "{{ hermes_control_source_ref }}"',
            "hermes_control_source_ref is match('^[0-9a-f]{40}$')",
            '.venv/bin/hermes-control"',
            "preflight",
            "install",
            "hermes_control_install_dir",
            "Align Hermes Control systemd units with the configured Hermes user",
            "Allow Hermes Control installer checkout for the runtime user",
            "Flush Hermes Control service changes before readiness checks",
            "bridge socket accepts connections",
            "Verify authenticated Hermes Control diagnostics",
        ):
            self.assertIn(fragment, text)
        self.assertIn("no_log: true", text)
        self.assertIn(".venv/bin/hermes-control", text)
        self.assertIn("changed_when: true\n  no_log: true\n  notify:", text)
        self.assertIn(
            "CONTROL_API_REQUIRE_TASK_APPROVAL=1",
            CONTROL_API_ENV.read_text(encoding="utf-8"),
        )
        self.assertNotIn("default(", CONTROL_API_ENV.read_text(encoding="utf-8"))
        self.assertIn(
            "EnvironmentFile=-/etc/hermes-mobile-control/plugin.env",
            GATEWAY_UNIT.read_text(encoding="utf-8"),
        )

    def test_restore_stops_are_inside_failure_safe_block(self) -> None:
        restore = (
            ROOT / "infra" / "ansible" / "playbooks" / "service-state-restore.yml"
        ).read_text(encoding="utf-8")
        block_start = restore.index(
            "- name: Restore service state with failure-safe service recovery\n      block:\n        - name: Stop managed system services before restore"
        )
        self.assertNotIn(
            "- name: Restore service state with failure-safe service recovery\n      tags:",
            restore,
        )
        self.assertLess(block_start, restore.index("      always:"))
        self.assertLess(
            restore.index("Stop managed user services before restore"),
            restore.index("      always:"),
        )

    def test_control_role_exposes_only_loopback_api_through_private_caddy(self) -> None:
        caddy = CADDYFILE.read_text(encoding="utf-8")
        self.assertIn("{% if hermes_control_enabled | default(false) %}", caddy)
        self.assertIn(
            "reverse_proxy {{ hermes_control_api_host | default('127.0.0.1') }}:{{ hermes_control_api_port | default(8787) }}",
            caddy,
        )
        self.assertIn("{{ hermes_control_domain }} {", caddy)
        self.assertIn("tls {", caddy)
        self.assertIn(
            "hermes_control_api_host == '127.0.0.1'",
            CONTROL_TASKS.read_text(encoding="utf-8"),
        )

    def test_control_environment_views_keep_tokens_scoped(self) -> None:
        api = CONTROL_API_ENV.read_text(encoding="utf-8")
        bridge = CONTROL_API_ENV.read_text(encoding="utf-8")
        plugin = CONTROL_PLUGIN_ENV.read_text(encoding="utf-8")
        self.assertIn("CONTROL_API_TOKEN={{ hermes_control_api_token }}", api)
        self.assertIn(
            "CONTROL_API_HERMES_PLUGIN_TOKEN={{ hermes_control_bridge_token }}", api
        )
        self.assertIn(
            "HERMES_CONTROL_EXTENSION_TOKEN={{ hermes_control_bridge_token }}", bridge
        )
        self.assertNotIn("hermes_control_bridge_token", plugin)
        self.assertIn("CONTROL_API_TOKEN={{ hermes_control_api_token }}", plugin)
        self.assertIn(
            "hermes-mobile-control-api", CONTROL_TASKS.read_text(encoding="utf-8")
        )

    def test_operations_doc_covers_deployed_verification_and_recovery(self) -> None:
        operations = OPERATIONS_DOC.read_text(encoding="utf-8")
        for marker in (
            "Five-state verification",
            "Rotation and rollback",
            "HERMES_PLUGINS_DEBUG=1",
            "HERMES_CONTROL_SOURCE_REF",
            "Do not expose port 8787",
        ):
            self.assertIn(marker, operations)

    def test_control_role_yaml_is_parseable(self) -> None:
        self.assertIsInstance(
            yaml.safe_load(CONTROL_TASKS.read_text(encoding="utf-8")), list
        )

    @unittest.skipUnless(
        shutil.which("ansible-playbook"), "ansible-playbook is required"
    )
    def test_control_role_rejects_non_normalized_workspace_paths(self) -> None:
        cases = (
            ("/srv/../outside", ["/srv/project"]),
            ("/srv", ["/srv/./project"]),
            ("/srv/", ["/srv/project"]),
            ("/srv", ["/srv/project/"]),
        )
        for workspace_root, project_roots in cases:
            with self.subTest(
                workspace_root=workspace_root, project_roots=project_roots
            ):
                play = yaml.safe_dump(
                    [
                        {
                            "hosts": "localhost",
                            "gather_facts": False,
                            "vars": {
                                "hermes_runtime_user": "nobody",
                                "hermes_control_domain": "control.example.internal",
                                "hermes_control_source_url": "https://example.invalid/hermes-control.git",
                                "hermes_control_source_ref": "0" * 40,
                                "hermes_control_api_token": "test-placeholder",
                                "hermes_control_bridge_token": "test-placeholder",
                                "hermes_control_workspace_root": workspace_root,
                                "hermes_control_project_roots": project_roots,
                            },
                            "tasks": [
                                {
                                    "ansible.builtin.include_role": {
                                        "name": "hermes_control"
                                    }
                                }
                            ],
                        }
                    ],
                    sort_keys=False,
                )
                result = subprocess.run(
                    [
                        "ansible-playbook",
                        "-i",
                        "localhost,",
                        "-c",
                        "local",
                        "/dev/stdin",
                    ],
                    cwd=ROOT,
                    input=play,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "normalized workspace/project roots", result.stdout + result.stderr
                )


if __name__ == "__main__":
    unittest.main()

"""Static regression contract for public-safe Ansible convergence behavior."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "check-direct-service-ansible.py"
ROLES = ROOT / "infra" / "ansible" / "roles"
STANDARD_TAGS = {
    "validation",
    "packages",
    "config",
    "service",
    "health",
    "backup",
    "restore",
}


def load_role_contract(role: str) -> tuple[dict[str, Any], dict[str, Any]]:
    defaults_path = ROLES / role / "defaults" / "main.yml"
    specs_path = ROLES / role / "meta" / "argument_specs.yml"
    defaults = yaml.safe_load(defaults_path.read_text(encoding="utf-8")) or {}
    specs = yaml.safe_load(specs_path.read_text(encoding="utf-8"))["argument_specs"][
        "main"
    ]["options"]
    return defaults, specs


class AnsibleConvergenceContractTests(unittest.TestCase):
    @staticmethod
    def load_helper():
        spec = importlib.util.spec_from_file_location(
            "check_direct_service_ansible_contract", HELPER
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_every_role_default_has_a_typed_argument_spec(self) -> None:
        for defaults_path in sorted(ROLES.glob("*/defaults/main.yml")):
            role = defaults_path.parents[1].name
            specs_path = defaults_path.parents[1] / "meta" / "argument_specs.yml"
            self.assertTrue(specs_path.is_file(), role)
            defaults, specs = load_role_contract(role)
            self.assertEqual(set(defaults) - set(specs), set(), role)

    def test_projection_consumers_expose_compatibility_defaults_in_specs(self) -> None:
        # These roles own public defaults while the remainder of their inputs arrive
        # through the canonical projection.  Keep both declarations synchronized.
        expected = {
            "hermes": {"hermes_default_soul_sha256"},
            "onramp_host": {"onramp_host_allow_passwordless_sudo"},
            "sssf": {
                "sssf_data_device",
                "sssf_max_concurrent_runs",
                "sssf_pi_path",
                "sssf_provider",
                "sssf_uv_path",
                "sssf_visualizer_command",
            },
        }
        for role, keys in expected.items():
            defaults, specs = load_role_contract(role)
            self.assertTrue(keys <= set(defaults), role)
            self.assertTrue(keys <= set(specs), role)

    def test_static_checker_rejects_non_executable_tags_and_nested_play_tasks(
        self,
    ) -> None:
        helper = self.load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            playbook = root / "infra/ansible/playbooks/contract.yml"
            playbook.parent.mkdir(parents=True)
            playbook.write_text(
                """---
- name: Parent tag must not be inherited
  hosts: localhost
  tags: [config]
  pre_tasks:
    - name: Untagged nested command
      ansible.builtin.command: ["true"]
  tasks:
    - name: Untagged dynamic transport
      ansible.builtin.include_tasks: child.yml
    - name: Two approved tags
      tags: [config, health]
      ansible.builtin.debug:
        msg: bad
    - name: Nested command without idempotence
      block:
        - name: Imperative nested command
          tags: [service]
          ansible.builtin.command: ["true"]
  post_tasks:
    - name: Post task
      tags: [health]
      ansible.builtin.debug:
        msg: ok
  handlers:
    - name: Handler task
      tags: [service]
      ansible.builtin.debug:
        msg: ok
""",
                encoding="utf-8",
            )
            original_repo = helper.REPO
            helper.REPO = root
            try:
                with self.assertRaises(helper.CheckError) as error:
                    helper.check_mode_static()
            finally:
                helper.REPO = original_repo
        output = str(error.exception)
        self.assertIn("non-executable-tag", output)
        self.assertIn("dynamic-transport-tags", output)
        self.assertIn("untagged-task", output)
        self.assertIn("multiple-standard-tags", output)
        self.assertIn("command-no-idempotence", output)
        self.assertEqual(helper.STANDARD_TAGS, STANDARD_TAGS)
        self.assertFalse(
            helper.command_task_has_idempotence(
                {"ansible.builtin.command": {"argv": ["tool"]}, "when": "enabled"}
            )
        )
        self.assertTrue(
            helper.command_task_has_idempotence(
                {"ansible.builtin.command": {"argv": ["tool"]}, "changed_when": False}
            )
        )
        self.assertTrue(
            helper.command_task_has_idempotence(
                {
                    "ansible.builtin.command": {"argv": ["tool"]},
                    "args": {"creates": "/sentinel"},
                }
            )
        )

    def test_rendered_tailscale_tags_have_exactly_one_category(self) -> None:
        result = subprocess.run(
            [
                "ansible-playbook",
                "-i",
                "localhost,",
                "infra/ansible/playbooks/tailscale-client.yml",
                "--list-tasks",
                "--check",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        rendered_task_count = 0
        for line in result.stdout.splitlines():
            if (
                "TAGS:" not in line
                or line.lstrip().startswith("play #")
                or "Validating arguments against arg spec" in line
            ):
                continue
            rendered_task_count += 1
            rendered_tags = line.split("TAGS:", 1)[1].strip().strip("[]")
            tags = {tag.strip() for tag in rendered_tags.split(",") if tag.strip()}
            self.assertLessEqual(tags, STANDARD_TAGS, line)
            self.assertEqual(len(tags), 1, line)
        self.assertGreater(rendered_task_count, 0)

    def test_dynamic_transports_load_only_the_requested_tagged_descendant(self) -> None:
        """`always` selects the loader without inheriting its child task tags."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            children = root / "children.yml"
            children.write_text(
                """---
- name: Dynamic config descendant
  tags: [config]
  ansible.builtin.debug:
    msg: config
- name: Dynamic service descendant
  tags: [service]
  ansible.builtin.debug:
    msg: service
- name: Dynamic health descendant
  tags: [health]
  ansible.builtin.debug:
    msg: health
""",
                encoding="utf-8",
            )
            playbook = root / "transport.yml"
            playbook.write_text(
                """---
- hosts: localhost
  gather_facts: false
  connection: local
  tasks:
    - name: Dynamic transport
      tags: [always]
      ansible.builtin.include_tasks: children.yml
""",
                encoding="utf-8",
            )
            for selected in ("health", "config", "service"):
                result = subprocess.run(
                    [
                        "ansible-playbook",
                        "-i",
                        "localhost,",
                        str(playbook),
                        "--check",
                        "--tags",
                        selected,
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                self.assertIn(f"Dynamic {selected} descendant", result.stdout)
                for unrelated in {"health", "config", "service"} - {selected}:
                    self.assertNotIn(f"Dynamic {unrelated} descendant", result.stdout)

    def test_tailscale_forwarding_is_safe_in_disabled_and_enabled_check_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_sysctl = Path(tmp) / "bin" / "sysctl"
            fake_sysctl.parent.mkdir()
            fake_sysctl.write_text(
                '#!/bin/sh\n[ "$1" = "-n" ] && printf \'0\\n\'\n', encoding="utf-8"
            )
            fake_sysctl.chmod(0o755)
            playbook = Path(tmp) / "tailscale-check.yml"
            playbook.write_text(
                f"""---
- hosts: localhost
  gather_facts: false
  connection: local
  environment:
    PATH: {fake_sysctl.parent}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  roles:
    - role: tailscale_client
""",
                encoding="utf-8",
            )
            base_args = [
                "ansible-playbook",
                "-i",
                "localhost,",
                str(playbook),
                "--check",
                "--tags",
                "config",
                "--start-at-task",
                "Configure IPv4 forwarding in Tailscale client LXC",
                "-e",
                "tailscale_client_vmid=100 tailscale_client_enable_ip_forwarding=true ansible_distribution_release=bookworm",
            ]
            disabled = subprocess.run(
                [*base_args, "-e", "tailscale_client_enabled=false"],
                cwd=ROOT,
                env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROLES)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            self.assertIn(
                "Configure IPv4 forwarding in Tailscale client LXC]", disabled.stdout
            )
            self.assertNotIn("changed: [localhost]", disabled.stdout)
            self.assertNotIn(
                "Read active IPv4 forwarding state in Tailscale client LXC] ***\nok:",
                disabled.stdout,
            )

            enabled = subprocess.run(
                [*base_args, "-e", "tailscale_client_enabled=true"],
                cwd=ROOT,
                env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROLES)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(enabled.returncode, 0, enabled.stdout + enabled.stderr)
            self.assertIn(
                "Read active IPv4 forwarding state in Tailscale client LXC] ***\nok:",
                enabled.stdout,
            )
            self.assertIn(
                "Converge active IPv4 forwarding state in Tailscale client LXC] ***\nskipping:",
                enabled.stdout,
            )

    def test_tailscale_uses_native_modules_for_persistent_state(self) -> None:
        tasks = yaml.safe_load(
            (ROLES / "tailscale_client/tasks/main.yml").read_text(encoding="utf-8")
        )
        forwarding = next(
            task
            for task in tasks
            if task.get("name") == "Configure IPv4 forwarding in Tailscale client LXC"
        )
        live_probe = next(
            task
            for task in tasks
            if task.get("name")
            == "Read active IPv4 forwarding state in Tailscale client LXC"
        )
        live_convergence = next(
            task
            for task in tasks
            if task.get("name")
            == "Converge active IPv4 forwarding state in Tailscale client LXC"
        )
        service = next(
            task
            for task in tasks
            if task.get("name") == "Ensure tailscaled is enabled and running"
        )
        self.assertIn("ansible.builtin.copy", forwarding)
        self.assertEqual(
            forwarding["ansible.builtin.copy"]["dest"],
            "/etc/sysctl.d/99-tailscale-client.conf",
        )
        self.assertEqual(
            forwarding["when"],
            [
                "tailscale_client_enabled | default(false) | bool",
                "tailscale_client_enable_ip_forwarding | default(true) | bool",
            ],
        )
        self.assertEqual(
            live_probe["ansible.builtin.command"]["argv"],
            ["sysctl", "-n", "net.ipv4.ip_forward"],
        )
        self.assertFalse(live_probe["changed_when"])
        self.assertFalse(live_probe["check_mode"])
        self.assertEqual(
            live_convergence["ansible.builtin.command"]["argv"],
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
        )
        self.assertEqual(
            live_convergence["changed_when"],
            "tailscale_client_ipv4_forwarding.stdout | default('') | trim != '1'",
        )
        self.assertIn(
            "tailscale_client_ipv4_forwarding.stdout | default('') | trim != '1'",
            live_convergence["when"],
        )
        self.assertEqual(
            service["ansible.builtin.systemd_service"],
            {"name": "tailscaled", "enabled": True, "state": "started"},
        )


if __name__ == "__main__":
    unittest.main()

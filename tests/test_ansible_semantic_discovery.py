from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ansible_semantic_discovery.py"
spec = importlib.util.spec_from_file_location("ansible_semantic_discovery", SCRIPT)
assert spec and spec.loader
ansible_semantic_discovery = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ansible_semantic_discovery
spec.loader.exec_module(ansible_semantic_discovery)


class AnsibleSemanticDiscoveryTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        repo = Path(temp.name)
        inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
        inventory.parent.mkdir(parents=True)
        inventory.write_text(
            "all:\n"
            "  hosts:\n"
            "    pve:\n"
            "      ansible_host: proxmox.example.internal\n"
            "  vars:\n"
            "    forgejo_domain: git.example.internal\n"
            "    forgejo_secret_key: SECRET_SENTINEL_DO_NOT_PRINT\n"
            "    forgejo_runtime:\n"
            "      type: lxc\n"
            "    one_time_bootstrap: true\n"
            "    dynamic_endpoint: \"{{ lookup('env', 'DYNAMIC_SECRET') }}\"\n",
            encoding="utf-8",
        )
        role = repo / "infra" / "ansible" / "roles" / "forgejo"
        (role / "tasks").mkdir(parents=True)
        (role / "templates").mkdir()
        (role / "tasks" / "main.yml").write_text(
            "- name: Configure Forgejo\n"
            "  ansible.builtin.template:\n"
            "    src: app.ini.j2\n"
            "    dest: /etc/forgejo/app.ini\n"
            "  when: forgejo_runtime.type == 'lxc'\n"
            "- name: Debug public value without exposing inline credentials\n"
            "  ansible.builtin.debug:\n"
            "    msg: \"forgejo_domain={{ forgejo_domain }} password=INLINE_SECRET_SENTINEL\"\n",
            encoding="utf-8",
        )
        (role / "templates" / "app.ini.j2").write_text(
            "ROOT_URL={{ forgejo_domain }}/\n"
            "SECRET={{ forgejo_secret_key }}\n",
            encoding="utf-8",
        )
        (repo / "infra" / "ansible" / "playbooks").mkdir(parents=True)
        (repo / "infra" / "ansible" / "playbooks" / "forgejo.yml").write_text(
            "- hosts: forgejo\n  roles:\n    - forgejo\n",
            encoding="utf-8",
        )
        return temp, repo

    def test_report_is_value_free_and_traces_consumers(self) -> None:
        temp, repo = self.make_repo()
        with temp:
            report = ansible_semantic_discovery.discover_ansible(repo)
            rendered = json.dumps(ansible_semantic_discovery.render_report(report), sort_keys=True)
        observations = {item.key: item for item in report.observations}
        self.assertEqual(observations["forgejo_domain"].classification, "mapped")
        self.assertEqual(
            observations["forgejo_domain"].canonical_path,
            "services.forgejo.endpoints.public_names",
        )
        self.assertTrue(observations["forgejo_domain"].consumers)
        nested = observations["forgejo_runtime.type"]
        self.assertTrue(nested.consumers)
        self.assertTrue(observations["dynamic_endpoint"].dynamic)
        expressions = "\\n".join(reference.expression for reference in observations["forgejo_domain"].consumers)
        self.assertIn("<redacted>", expressions)
        self.assertNotIn("INLINE_SECRET_SENTINEL", expressions)
        self.assertTrue(observations["forgejo_secret_key"].secret)
        self.assertEqual(observations["forgejo_secret_key"].classification, "secret/provider")
        self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", rendered)
        self.assertIn("candidate_generation_allowed", rendered)
        self.assertNotIn('"candidate_generation_allowed": true', rendered)

    def test_unknown_and_lifecycle_values_remain_review_required(self) -> None:
        temp, repo = self.make_repo()
        with temp:
            report = ansible_semantic_discovery.discover_ansible(repo)
        observations = {item.key: item for item in report.observations}
        self.assertEqual(observations["one_time_bootstrap"].classification, "operational/review")
        self.assertTrue(observations["one_time_bootstrap"].disposition.startswith("review-required"))
        self.assertEqual(observations["all.hosts.pve.ansible_host"].classification, "operational/review")

    def test_private_values_inventory_is_rejected(self) -> None:
        temp, repo = self.make_repo()
        with temp:
            private = repo / "values" / "ansible" / "inventory" / "local.yml"
            private.parent.mkdir(parents=True)
            private.write_text("all: {}\n", encoding="utf-8")
            with self.assertRaises(ansible_semantic_discovery.DiscoveryError):
                ansible_semantic_discovery.discover_ansible(repo, private)

    def test_inventory_outside_repository_is_rejected(self) -> None:
        temp, repo = self.make_repo()
        with temp:
            outside = Path(temp.name).parent / f"{Path(temp.name).name}-outside.yml"
            outside.write_text("all: {}\n", encoding="utf-8")
            with self.assertRaises(ansible_semantic_discovery.DiscoveryError):
                ansible_semantic_discovery.discover_ansible(repo, outside)


if __name__ == "__main__":
    unittest.main()

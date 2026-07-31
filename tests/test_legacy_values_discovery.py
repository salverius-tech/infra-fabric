from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "legacy_values_discovery.py"
spec = importlib.util.spec_from_file_location("legacy_values_discovery", SCRIPT)
assert spec and spec.loader
legacy_values_discovery = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = legacy_values_discovery
spec.loader.exec_module(legacy_values_discovery)

CLI_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "legacy-values-discovery.py"
cli_spec = importlib.util.spec_from_file_location("legacy_values_discovery_cli", CLI_SCRIPT)
assert cli_spec and cli_spec.loader
legacy_values_discovery_cli = importlib.util.module_from_spec(cli_spec)
sys.modules[cli_spec.name] = legacy_values_discovery_cli
cli_spec.loader.exec_module(legacy_values_discovery_cli)


class LegacyValuesDiscoveryTests(unittest.TestCase):
    def make_values(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        values = Path(temp.name) / "values"
        (values / "ansible" / "inventory").mkdir(parents=True)
        (values / ".env").write_text(
            "TECHNITIUM_API_URL=http://192.0.2.53:5380/api\n"
            "TECHNITIUM_API_TOKEN=SECRET_SENTINEL_DO_NOT_PRINT\n"
            "SERVER_NAME=DNS.Example.Internal.\n",
            encoding="utf-8",
        )
        (values / "terraform.tfvars").write_text(
            'technitium_api_url = "http://192.0.2.53:5380/api"\n'
            'forgejo_server_name = "Git.Example.Internal."\n'
            'unmapped_public_key = "review-me"\n',
            encoding="utf-8",
        )
        (values / "settings.local.json").write_text('{"services": ["technitium"]}\n', encoding="utf-8")
        (values / "dns-records.local.json").write_text('{"dns.example.internal": "192.0.2.53"}\n', encoding="utf-8")
        (values / "ansible" / "inventory" / "local.yml").write_text("all:\n  hosts:\n    edge:\n", encoding="utf-8")
        return temp, values

    def test_repository_scaffold_admits_bounded_forgejo_runtime_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = legacy_values_discovery.discover_legacy(
                Path(temp_dir),
                repo=Path(__file__).resolve().parents[1],
                ansible_inventory=Path(__file__).resolve().parents[1] / "scaffold/ansible/inventory/local.yml",
            )
        admission = legacy_values_discovery.runtime_importer_admission(report)
        self.assertTrue(admission["admitted"])
        self.assertEqual(admission["status"], "complete")
        self.assertEqual(admission["missing"], [])
        self.assertEqual(admission["invalid"], [])
        self.assertEqual(admission["conflicts"], [])
        runtime = next(item for item in report.observations if item.key == "forgejo_runtime")
        self.assertEqual(runtime.classification, "mapped")
        self.assertEqual(runtime.proposed_path, "resources.guests.forgejo.runtime")

    def test_bounded_public_ansible_importer_admits_forgejo_domain_only(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    forgejo_domain: git.example.internal\n    forgejo_version: 12.0.4\n    forgejo_root_url: https://git.example.internal\n    forgejo_bootstrap_admin_email: review@example.internal\n    forgejo_download_base: '{% dynamic %}'\n    forgejo_ssh_port: 22\n    forgejo_enable_caddy: true\n    forgejo_configure_system_ssh: true\n    forgejo_write_initial_config: false\n    forgejo_bootstrap_enabled: true\n    forgejo_actions_enabled: true\n    forgejo_actions_default_url: https://data.forgejo.org\n"
                "  hosts:\n    edge:\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(observations[("forgejo_domain", "mapped")].value, ["git.example.internal"])
        self.assertEqual(observations[("forgejo_version", "mapped")].value, "12.0.4")
        self.assertEqual(observations[("forgejo_root_url", "mapped")].value, "https://git.example.internal/")
        for key in (
            "forgejo_enable_caddy",
            "forgejo_ssh_port",
            "forgejo_configure_system_ssh",
            "forgejo_write_initial_config",
            "forgejo_bootstrap_enabled",
            "forgejo_actions_enabled",
            "forgejo_actions_default_url",
        ):
            self.assertEqual(observations[(key, "mapped")].key, key)
        self.assertEqual(
            observations[("forgejo_bootstrap_admin_email", "mapped")].proposed_path,
            "services.forgejo.configuration.bootstrap_admin_email",
        )
        self.assertTrue(
            any(
                item.key == "forgejo_download_base"
                and item.classification == "unsupported"
                and item.value_type == "dynamic-expression"
                and item.value is None
                for item in report.observations
            )
        )
        self.assertFalse(report.mapping_ready)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_records_admitted_dynamic_values_without_evaluating(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    forgejo_domain: '{{ inventory_hostname }}'\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observation = next(item for item in report.observations if item.key == "forgejo_domain")
        self.assertEqual(observation.classification, "unsupported")
        self.assertEqual(observation.value_type, "dynamic-expression")
        self.assertEqual(observation.dynamic_reference, "inventory_hostname")
        self.assertFalse(observation.dynamic_reference_available)
        self.assertEqual(observation.dynamic_reference_chain, ("forgejo_domain", "inventory_hostname"))
        self.assertEqual(observation.dynamic_resolution, "missing")
        self.assertIsNone(observation.value)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_reports_resolved_dynamic_chain_without_admitting_it(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    forgejo_domain: '{{ forgejo_root_url }}'\n    forgejo_root_url: 'https://forgejo.example.internal'\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observation = next(item for item in report.observations if item.key == "forgejo_domain")
        self.assertEqual(observation.dynamic_reference_chain, ("forgejo_domain", "forgejo_root_url"))
        self.assertEqual(observation.dynamic_resolution, "resolved")
        self.assertTrue(observation.dynamic_reference_available)
        rendered = legacy_values_discovery.render_migration_report(report)
        self.assertEqual(rendered["dynamic_resolution"], {"count": 1, "available_count": 1, "missing_count": 0, "cycle_count": 0, "resolved_count": 1})
        rendered_observation = next(item for item in rendered["observations"] if item["key"] == "forgejo_domain")
        self.assertEqual(rendered_observation["dynamic_reference_chain"], ["forgejo_domain", "forgejo_root_url"])
        self.assertEqual(rendered_observation["dynamic_resolution"], "resolved")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_reports_dynamic_reference_cycles(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    forgejo_domain: '{{ forgejo_root_url }}'\n    forgejo_root_url: '{{ forgejo_domain }}'\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observation = next(item for item in report.observations if item.key == "forgejo_domain")
        self.assertEqual(observation.dynamic_reference_chain, ("forgejo_domain", "forgejo_root_url", "forgejo_domain"))
        self.assertEqual(observation.dynamic_resolution, "cycle")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_technitium_release_fields(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_discovery_version: '15.2.0'\n"
                "    technitium_portable_sha256: 2e39fb8d0718475790cc025e083a1bcfd837a5e79e4a1d0ed775881bd90287ef\n"
                "    TECHNITIUM_API_TOKEN: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("technitium_discovery_version", "mapped")].proposed_path,
            "services.technitium.release.version",
        )
        self.assertEqual(observations[("technitium_discovery_version", "mapped")].value, "15.2.0")
        self.assertEqual(
            observations[("technitium_portable_sha256", "mapped")].proposed_path,
            "services.technitium.release.checksum",
        )
        self.assertEqual(observations[("technitium_portable_sha256", "mapped")].value, "2e39fb8d0718475790cc025e083a1bcfd837a5e79e4a1d0ed775881bd90287ef")
        self.assertEqual(observations[("TECHNITIUM_API_TOKEN", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_conflicts_with_legacy_domain(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                (values / ".env").read_text(encoding="utf-8") + "FORGEJO_DOMAIN=other.example.internal\n",
                encoding="utf-8",
            )
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    forgejo_domain: git.example.internal\n", encoding="utf-8")
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        self.assertTrue(any(conflict["canonical_path"] == "services.forgejo.endpoints.public_names" for conflict in report.conflicts))

    def test_bounded_ansible_importer_admits_forgejo_runner_release_version(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_version: '12.7.3'\n"
                "    FORGEJO_RUNNER_REGISTRATION_SECRET: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("forgejo_runner_version", "mapped")].proposed_path,
            "services.forgejo_runner.release.version",
        )
        self.assertEqual(observations[("forgejo_runner_version", "mapped")].value, "12.7.3")
        self.assertEqual(observations[("FORGEJO_RUNNER_REGISTRATION_SECRET", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_forgejo_runner_scalar_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_url: 'https://git.example.internal/'\n"
                "    forgejo_runner_name: homelab-deploy\n"
                "    forgejo_runner_scope: owner/homelab-infra-values\n"
                "    forgejo_runner_label: homelab-deploy\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "forgejo_runner_url": "services.forgejo_runner.configuration.url",
            "forgejo_runner_name": "services.forgejo_runner.configuration.name",
            "forgejo_runner_scope": "services.forgejo_runner.configuration.scope",
            "forgejo_runner_label": "services.forgejo_runner.configuration.label",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_infisical_scalar_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    infisical_vmid: 110\n"
                "    infisical_data_dir: /var/lib/infisical\n"
                "    infisical_postgres_user: infisical\n"
                "    infisical_postgres_db: infisical\n"
                "    infisical_domain: infisical.example.internal\n"
                "    infisical_version: 'v0.162.3@sha256:"
                + "a" * 64
                + "'\n"
                "    INFISICAL_ENCRYPTION_KEY: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "infisical_vmid": "resources.guests.infisical.identity.vmid",
            "infisical_data_dir": "services.infisical.configuration.data_dir",
            "infisical_postgres_user": "services.infisical.configuration.postgres_user",
            "infisical_postgres_db": "services.infisical.configuration.postgres_db",
            "infisical_domain": "services.infisical.endpoints.public_names",
            "infisical_version": "services.infisical.release.version",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(observations[("INFISICAL_ENCRYPTION_KEY", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_root_and_site_aware_layouts_have_equivalent_report_only_discovery(self) -> None:
        temp, values = self.make_values()
        with temp:
            site_values = values / "sites" / "dev"
            site_values.mkdir(parents=True)
            for source in (".env", "terraform.tfvars", "settings.local.json", "dns-records.local.json"):
                (site_values / source).write_bytes((values / source).read_bytes())
            inventory = site_values / "ansible" / "inventory"
            inventory.mkdir(parents=True)
            (inventory / "local.yml").write_bytes((values / "ansible" / "inventory" / "local.yml").read_bytes())
            before = {path: path.read_bytes() for path in values.rglob("*") if path.is_file()}
            root_report = legacy_values_discovery.discover_legacy(values)
            site_report = legacy_values_discovery.discover_legacy(site_values)
            after = {path: path.read_bytes() for path in values.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        normalize = lambda report: sorted(
            (item.key, item.classification, item.proposed_path, repr(item.value)) for item in report.observations
        )
        self.assertEqual(normalize(root_report), normalize(site_report))
        self.assertEqual(root_report.conflicts, site_report.conflicts)
        self.assertEqual(root_report.candidate_ready, site_report.candidate_ready)
        rendered = json.dumps(legacy_values_discovery.render_migration_report(site_report))
        self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", rendered)
        self.assertFalse((values / "site.yaml").exists())
        self.assertFalse((site_values / "site.yaml").exists())

    def test_ancillary_artifacts_are_reported_without_reading_contents(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / "ansible" / "known_hosts").write_text(
                "SECRET_KNOWN_HOST_SENTINEL\n", encoding="utf-8"
            )
            (values / "terraform.tfstate").write_text(
                '{"secret":"SECRET_STATE_SENTINEL"}\n', encoding="utf-8"
            )
            (values / "service-backups").mkdir()
            (values / "service-backups" / "forgejo.json").write_text(
                "SECRET_BACKUP_SENTINEL\n", encoding="utf-8"
            )
            (values / "tfplan.bin").write_bytes(b"SECRET_PLAN_SENTINEL")
            (values / "artifacts" / "nested").mkdir(parents=True)
            (values / "artifacts" / "nested" / "report.txt").write_text(
                "SECRET_ARTIFACT_SENTINEL\n", encoding="utf-8"
            )
            (values / "backups").mkdir()
            (values / "backups" / "restore.tar").write_bytes(b"SECRET_RECOVERY_SENTINEL")
            report = legacy_values_discovery.discover_legacy(values)
            rendered = json.dumps(legacy_values_discovery.render_migration_report(report))
        artifacts = {item["path"]: item for item in report.ancillary_artifacts}
        self.assertEqual(artifacts["ansible/known_hosts"]["class"], "known-hosts")
        self.assertEqual(artifacts["terraform.tfstate"]["class"], "terraform-state")
        self.assertEqual(artifacts["service-backups"]["class"], "service-backups")
        self.assertEqual(artifacts["service-backups"]["file_count"], 1)
        self.assertEqual(artifacts["tfplan.bin"]["class"], "terraform-plan")
        self.assertEqual(artifacts["artifacts"]["class"], "general-artifacts")
        self.assertEqual(artifacts["backups"]["class"], "recovery-backups")
        self.assertEqual(artifacts["artifacts"]["file_count"], 1)
        self.assertEqual(artifacts["backups"]["file_count"], 1)
        self.assertNotIn("SECRET_KNOWN_HOST_SENTINEL", rendered)
        self.assertNotIn("SECRET_PLAN_SENTINEL", rendered)
        self.assertNotIn("SECRET_ARTIFACT_SENTINEL", rendered)
        self.assertNotIn("SECRET_RECOVERY_SENTINEL", rendered)

        self.assertNotIn("SECRET_STATE_SENTINEL", rendered)
        self.assertNotIn("SECRET_BACKUP_SENTINEL", rendered)

    def test_ancillary_artifacts_have_root_site_layout_parity(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / "ansible" / "known_hosts").write_text("host key\n", encoding="utf-8")
            (values / "terraform.tfstate.backup").write_text("state\n", encoding="utf-8")
            (values / "service-backups").mkdir()
            (values / "service-backups" / "restore.tar").write_bytes(b"backup")
            site_values = values / "sites" / "dev"
            for source in ("ansible/known_hosts", "terraform.tfstate.backup", "service-backups/restore.tar"):
                destination = site_values / source
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((values / source).read_bytes())
            root_report = legacy_values_discovery.discover_legacy(values)
            site_report = legacy_values_discovery.discover_legacy(site_values)
        normalize = lambda report: sorted(
            (item["path"], item["class"], item.get("file_count"), item["size_bytes"])
            for item in report.ancillary_artifacts
        )
        self.assertEqual(normalize(root_report), normalize(site_report))
        self.assertFalse((values / "site.yaml").exists())
        self.assertFalse((site_values / "site.yaml").exists())

    def test_ancillary_artifact_symlink_is_rejected(self) -> None:
        temp, values = self.make_values()
        with temp:
            target = values.parent / "outside-known-hosts"
            target.write_text("host key\n", encoding="utf-8")
            (values / "ansible" / "known_hosts").symlink_to(target)
            with self.assertRaises(legacy_values_discovery.DiscoveryError):
                legacy_values_discovery.discover_legacy(values)

    def test_ancillary_artifact_special_file_is_rejected(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / "artifacts").mkdir()
            os.mkfifo(values / "artifacts" / "artifacts.fifo")
            with self.assertRaises(legacy_values_discovery.DiscoveryError):
                legacy_values_discovery.discover_legacy(values)


    def test_discovery_is_byte_for_byte_non_mutating(self) -> None:
        temp, values = self.make_values()
        with temp:
            before = {path: path.read_bytes() for path in values.rglob("*") if path.is_file()}
            report = legacy_values_discovery.discover_legacy(values)
            after = {path: path.read_bytes() for path in values.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((values / "site.yaml").exists())
        self.assertIn(".env", report.files)

    def test_hermes_control_source_aliases_are_mapped_and_redacted_secrets_stay_secret(self) -> None:
        migration = legacy_values_discovery._load_migration_module()
        self.assertEqual(
            legacy_values_discovery._classification("HERMES_CONTROL_SOURCE_URL", migration),
            ("mapped", "services.hermes.configuration.control.source_url"),
        )
        self.assertEqual(
            legacy_values_discovery._classification("HERMES_CONTROL_SOURCE_REF", migration),
            ("mapped", "services.hermes.configuration.control.source_ref"),
        )
        self.assertEqual(legacy_values_discovery._classification("HERMES_CONTROL_API_TOKEN", migration)[0], "secret")

        temp, values = self.make_values()
        with temp:
            rendered = json.dumps(
                legacy_values_discovery.render_migration_report(
                    legacy_values_discovery.discover_legacy(values)
                ),
                sort_keys=True,
            )
        self.assertIn("TECHNITIUM_API_TOKEN", rendered)
        self.assertIn("<redacted>", rendered)
        self.assertIn("unmapped_public_key", rendered)
        self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", rendered)
        self.assertNotIn("review-me", rendered)

    def test_bounded_ansible_importer_admits_hermes_release_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_discovery_version: 0.18.0\n"
                "    hermes_discovery_tag: v2026.7.1\n"
                "    hermes_discovery_commit: 7c1a029553d87c43ecff8a3821336bc95872213b\n"
                "    hermes_discovery_wheel_sha256: " + "b" * 64 + "\n"
                "    hermes_node_version: 22.23.1\n"
                "    hermes_node_sha256_amd64: " + "c" * 64 + "\n"
                "    hermes_node_sha256_arm64: " + "d" * 64 + "\n"
                "    hermes_dashboard_enabled: true\n"
                "    hermes_dashboard_port: 9119\n"
                "    hermes_dashboard_host: 127.0.0.1\n"
                "    hermes_dashboard_basic_auth_username: admin\n"
                "    hermes_control_enabled: false\n"
                "    hermes_control_domain: control.hermes.example.internal\n"
                "    hermes_control_api_host: 127.0.0.1\n"
                "    hermes_control_api_port: 9120\n"
                "    hermes_control_require_task_approval: true\n"
                "    hermes_control_plugin_socket: /run/hermes/control.sock\n"
                "    HERMES_CONTROL_API_TOKEN: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "hermes_discovery_version": "services.hermes.release.version",
            "hermes_discovery_tag": "services.hermes.release.tag",
            "hermes_discovery_commit": "services.hermes.release.commit",
            "hermes_discovery_wheel_sha256": "services.hermes.release.checksum",
            "hermes_node_version": "services.hermes.configuration.node.version",
            "hermes_node_sha256_amd64": "services.hermes.configuration.node.checksums.amd64",
            "hermes_node_sha256_arm64": "services.hermes.configuration.node.checksums.arm64",
            "hermes_dashboard_enabled": "services.hermes.configuration.dashboard.enabled",
            "hermes_dashboard_port": "services.hermes.endpoints.ports.dashboard",
            "hermes_dashboard_host": "services.hermes.configuration.dashboard.host",
            "hermes_dashboard_basic_auth_username": "services.hermes.configuration.dashboard.auth_username",
            "hermes_control_enabled": "services.hermes.configuration.control.enabled",
            "hermes_control_domain": "services.hermes.configuration.control.domain",
            "hermes_control_api_host": "services.hermes.configuration.control.api_host",
            "hermes_control_api_port": "services.hermes.configuration.control.api_port",
            "hermes_control_require_task_approval": "services.hermes.configuration.control.require_task_approval",
            "hermes_control_plugin_socket": "services.hermes.configuration.control.plugin_socket",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(observations[("HERMES_CONTROL_API_TOKEN", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_hermes_runtime_scalars(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_runtime_passwordless_sudo: false\n"
                "    hermes_allow_legacy_runtime: false\n"
                "    hermes_compression_threshold: 0.75\n"
                "    hermes_max_concurrent_children: 5\n"
                "    hermes_max_spawn_depth: 2\n"
                "    hermes_web_searxng_url: https://searxng.apps.example.net\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "hermes_runtime_passwordless_sudo": "resources.guests.hermes.security.allow_passwordless_sudo",
            "hermes_allow_legacy_runtime": "services.hermes.configuration.allow_legacy_runtime",
            "hermes_compression_threshold": "services.hermes.configuration.tuning.compression_threshold",
            "hermes_max_concurrent_children": "services.hermes.configuration.tuning.max_concurrent_children",
            "hermes_max_spawn_depth": "services.hermes.configuration.tuning.max_spawn_depth",
            "hermes_web_searxng_url": "services.hermes.configuration.web.searxng_url",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_hermes_operator_transport(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_domain: hermes.example.internal.\n"
                "    hermes_runtime_user: anvil\n"
                "    hermes_repo_path: /srv/homelab-infra\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "hermes_domain": "services.hermes.endpoints.public_names",
            "hermes_runtime_user": "services.hermes.configuration.runtime_user",
            "hermes_repo_path": "services.hermes.configuration.repository_path",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(observations[("hermes_domain", "mapped")].value, ["hermes.example.internal"])
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_forgejo_actions_wave(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_actions_enabled: true\n"
                "    forgejo_actions_default_url: https://data.forgejo.org\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertTrue(observations[("forgejo_actions_enabled", "mapped")].value)
        self.assertEqual(
            observations[("forgejo_actions_default_url", "mapped")].value,
            "https://data.forgejo.org",
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_insecure_forgejo_actions_url(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    forgejo_actions_default_url: http://data.forgejo.org\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "HTTPS URL"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_tailscale_configuration_wave(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    tailscale_client_enable_ip_forwarding: true\n"
                "    tailscale_client_restore_backup: false\n"
                "    tailscale_client_backup_archive: /var/lib/tailscale/backup.json\n"
                "    tailscale_client_up_args:\n"
                "      - --accept-dns=false\n"
                "      - --ssh\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "tailscale_client_enable_ip_forwarding": ("services.tailscale_client.configuration.enable_ip_forwarding", True),
            "tailscale_client_restore_backup": ("services.tailscale_client.configuration.restore_backup", False),
            "tailscale_client_backup_archive": ("services.tailscale_client.configuration.backup_archive", "/var/lib/tailscale/backup.json"),
            "tailscale_client_up_args": ("services.tailscale_client.configuration.up_args", ["--accept-dns=false", "--ssh"]),
        }
        for key, (path, value) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, path)
                self.assertEqual(observations[(key, "mapped")].value, value)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_non_boolean_tailscale_flag(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    tailscale_client_restore_backup: \"yes\"\n", encoding="utf-8")
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "must be boolean"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_searxng_configuration_wave(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    searxng_container_port: 8080\n"
                "    searxng_bind_address: 127.0.0.1\n"
                "    searxng_instance_name: public-search\n"
                "    searxng_enable_public_url: true\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "searxng_container_port": ("services.searxng_onramp.configuration.container_port", 8080),
            "searxng_bind_address": ("services.searxng_onramp.configuration.bind_address", "127.0.0.1"),
            "searxng_instance_name": ("services.searxng_onramp.configuration.instance_name", "public-search"),
            "searxng_enable_public_url": ("services.searxng_onramp.configuration.enable_public_url", True),
        }
        for key, (path, value) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, path)
                self.assertEqual(observations[(key, "mapped")].value, value)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_non_loopback_searxng_bind(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    searxng_bind_address: 0.0.0.0\n", encoding="utf-8")
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "loopback IP"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_caddy_extra_vhosts(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_extra_vhosts:\n"
                "      - server_names:\n"
                "          - app.example.internal\n"
                "        upstream: 127.0.0.1:9000\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        observation = observations[("caddy_extra_vhosts", "mapped")]
        self.assertEqual(
            observation.proposed_path,
            "services.technitium.configuration.caddy.extra_vhosts",
        )
        self.assertEqual(
            observation.value,
            [{"server_names": ["app.example.internal"], "upstream": {"host": "127.0.0.1", "port": 9000}}],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_normalizes_singular_caddy_extra_vhost(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_extra_vhosts:\n"
                "      - server_name: App.Example.Internal.\n"
                "        upstream: 127.0.0.1:9000\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("caddy_extra_vhosts", "mapped")].value,
            [{"server_names": ["app.example.internal"], "upstream": {"host": "127.0.0.1", "port": 9000}}],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_reconciles_caddy_name_aliases(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_server_name: DNS.Example.Internal.\n"
                "    caddy_server_names:\n"
                "      - dns.example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(observations[("caddy_server_name", "mapped")].value, ["dns.example.internal"])
        self.assertEqual(observations[("caddy_server_names", "mapped")].value, ["dns.example.internal"])
        self.assertFalse(report.conflicts)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_divergent_caddy_name_aliases(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_server_name: dns.example.internal\n"
                "    caddy_server_names:\n"
                "      - other.example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        self.assertTrue(any(conflict["canonical_path"] == "services.technitium.configuration.caddy.server_names" for conflict in report.conflicts))
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_caddy_upstream(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    caddy_upstream: 127.0.0.1:5380\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        observation = observations[("caddy_upstream", "mapped")]
        self.assertEqual(
            observation.proposed_path,
            "services.technitium.configuration.caddy.upstream",
        )
        self.assertEqual(observation.value, {"host": "127.0.0.1", "port": 5380})
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_malformed_caddy_upstream(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    caddy_upstream: 127.0.0.1:70000\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "between 1 and 65535"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_caddy_server_names(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_server_names:\n"
                "      - dns.example.internal\n"
                "      - technitium.example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        observation = observations[("caddy_server_names", "mapped")]
        self.assertEqual(
            observation.proposed_path,
            "services.technitium.configuration.caddy.server_names",
        )
        self.assertEqual(
            observation.value,
            ["dns.example.internal", "technitium.example.internal"],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_caddy_email(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_email: admin@example.internal\n"
                "    caddy_cloudflare_api_token: SECRET_SENTINEL_DO_NOT_PRINT\n"
                "    CF_DNS_API_TOKEN: SECRET_SENTINEL_DO_NOT_PRINT_2\n"
                "    CF_API_EMAIL: provider@example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("caddy_email", "mapped")].proposed_path,
            "platform.ingress.acme.email",
        )
        self.assertEqual(observations[("caddy_email", "mapped")].value, "admin@example.internal")
        self.assertEqual(
            observations[("CF_DNS_API_TOKEN", "secret")].value,
            "<redacted>",
        )
        self.assertEqual(
            observations[("caddy_cloudflare_api_token", "secret")].value,
            "<redacted>",
        )
        self.assertEqual(
            observations[("CF_API_EMAIL", "protected")].value,
            "<redacted>",
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_forgejo_runner_dns_servers(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_dns_servers:\n"
                "      - 192.0.2.1\n"
                "      - 2001:db8::53\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        observation = observations[("forgejo_runner_dns_servers", "mapped")]
        self.assertEqual(observation.proposed_path, "resources.guests.forgejo_runner.network.dns_servers")
        self.assertEqual(observation.value, ["192.0.2.1", "2001:db8::53"])
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_non_string_forgejo_runner_dns_servers(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    forgejo_runner_dns_servers:\n      - 7\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "list of strings"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_typed_extra_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    tailscale_client_enabled: true\n"
                "    hermes_ssh_public_keys:\n"
                "      - ssh-ed25519 HERMES_PUBLIC_KEY\n"
                "    searxng_server_name: search.example.internal\n"
                "    searxng_public_url: https://search.example.internal/\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "tailscale_client_enabled": "services.tailscale_client.enabled",
            "hermes_ssh_public_keys": "resources.guests.hermes.security.ssh_public_keys",
            "searxng_server_name": "services.searxng_onramp.endpoints.public_names.0",
            "searxng_public_url": "services.searxng_onramp.endpoints.public_url",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_immutable_searxng_image(self) -> None:
        temp, values = self.make_values()
        image = "docker.io/searxng/searxng@sha256:" + "a" * 64
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                f"    searxng_container_image: {image}\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("searxng_container_image", "mapped")].proposed_path,
            "services.searxng_onramp.release",
        )
        self.assertEqual(observations[("searxng_container_image", "mapped")].value, image)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_mutable_searxng_image(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n    searxng_container_image: docker.io/searxng/searxng:latest\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "immutable"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_non_string_hermes_ssh_keys(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    hermes_ssh_public_keys:\n      - 7\n", encoding="utf-8")
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "list of strings"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_onramp_security(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    onramp_host_password_authentication: false\n"
                "    onramp_host_permit_root_login: false\n"
                "    onramp_host_deploy_user: anvil\n"
                "    onramp_host_deploy_dir: /srv/onramp\n"
                "    onramp_host_allow_passwordless_sudo: true\n"
                "    onramp_host_allowed_ssh_cidrs:\n"
                "      - 10.0.0.0/8\n"
                "      - 192.168.0.0/16\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "onramp_host_password_authentication": "resources.shared_hosts.onramp_host.security.password_authentication",
            "onramp_host_permit_root_login": "resources.shared_hosts.onramp_host.security.permit_root_login",
            "onramp_host_deploy_user": "resources.shared_hosts.onramp_host.security.deploy_user",
            "onramp_host_deploy_dir": "resources.shared_hosts.onramp_host.security.deploy_dir",
            "onramp_host_allow_passwordless_sudo": "resources.shared_hosts.onramp_host.security.allow_passwordless_sudo",
            "onramp_host_allowed_ssh_cidrs": "resources.shared_hosts.onramp_host.security.allowed_ssh_cidrs",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(
            observations[("onramp_host_allowed_ssh_cidrs", "mapped")].value,
            ["10.0.0.0/8", "192.168.0.0/16"],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_onramp_runtime_and_ssh_keys(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    onramp_host_cloud_init_user: anvil\n"
                "    onramp_host_ssh_public_keys:\n"
                "      - ssh-ed25519 AAAA_PUBLIC_KEY_ONE\n"
                "      - ssh-rsa AAAA_PUBLIC_KEY_TWO\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("onramp_host_cloud_init_user", "mapped")].proposed_path,
            "resources.shared_hosts.onramp_host.runtime.cloud_init_user",
        )
        self.assertEqual(
            observations[("onramp_host_ssh_public_keys", "mapped")].proposed_path,
            "resources.shared_hosts.onramp_host.security.ssh_public_keys",
        )
        self.assertEqual(
            observations[("onramp_host_ssh_public_keys", "mapped")].value,
            ["ssh-ed25519 AAAA_PUBLIC_KEY_ONE", "ssh-rsa AAAA_PUBLIC_KEY_TWO"],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_non_string_onramp_ssh_keys(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    onramp_host_ssh_public_keys:\n"
                "      - 7\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "list of strings"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_duplicate_caddy_extra_vhosts(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_extra_vhosts:\n"
                "      - server_name: App.Example.Internal.\n"
                "        upstream: 127.0.0.1:8080\n"
                "      - server_name: app.example.internal\n"
                "        upstream: 127.0.0.1:8081\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "unique"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_duplicate_names_within_caddy_extra_vhost(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_extra_vhosts:\n"
                "      - server_names:\n"
                "          - App.Example.Internal.\n"
                "          - app.example.internal\n"
                "        upstream: 127.0.0.1:8080\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "unique"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_importer_redacts_every_documented_secret_key(self) -> None:
        temp, values = self.make_values()
        with temp:
            migration = legacy_values_discovery._load_migration_module()
            report = legacy_values_discovery.DiscoveryReport(str(values))
            secret_keys = sorted(migration.SECRET_KEYS)
            for key in secret_keys:
                legacy_values_discovery._observe("fixture", key, "[REDACTED]", report, migration)
            observations = {item.key: item for item in report.observations}
            self.assertEqual(set(secret_keys), set(observations))
            for key in secret_keys:
                self.assertEqual("secret", observations[key].classification)
                self.assertIsNone(observations[key].proposed_path)
                self.assertEqual("<redacted>", observations[key].value)
            self.assertFalse(report.candidate_ready)

    def test_bounded_report_never_becomes_candidate_ready(self) -> None:
        migration = legacy_values_discovery._load_migration_module()
        report = legacy_values_discovery.DiscoveryReport("/tmp/values")
        legacy_values_discovery._observe("fixture", "SERVER_NAME", "dns.example.internal", report, migration)
        legacy_values_discovery._observe("fixture", "unmapped_public_key", "value", report, migration)
        legacy_values_discovery._observe("fixture", "TECHNITIUM_API_TOKEN", "[REDACTED]", report, migration)
        self.assertTrue(any(item.classification == "mapped" for item in report.observations))
        self.assertTrue(any(item.classification == "unknown" for item in report.observations))
        self.assertTrue(any(item.classification == "secret" for item in report.observations))
        self.assertFalse(report.candidate_ready)

    def test_artifact_paths_cannot_escape_values_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "values"
            outside = Path(temp_dir) / "outside.txt"
            root.mkdir()
            outside.write_text("outside", encoding="utf-8")
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "escapes"):
                legacy_values_discovery._artifact_relative(root, outside)

    def test_artifact_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "values"
            outside = Path(temp_dir) / "outside.txt"
            root.mkdir()
            outside.write_text("outside", encoding="utf-8")
            link = root / "linked.txt"
            link.symlink_to(outside)
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "symlinks"):
                legacy_values_discovery._artifact_relative(root, link)

    def test_artifact_tree_symlink_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "values"
            outside = Path(temp_dir) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "artifact.txt").write_text("outside", encoding="utf-8")
            link = root / "linked-tree"
            link.symlink_to(outside, target_is_directory=True)
            report = legacy_values_discovery.DiscoveryReport(str(root))
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "symlinks"):
                legacy_values_discovery._record_artifact_tree(report, root, link, "fixture")

    def test_artifact_file_entry_must_be_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "values"
            root.mkdir()
            directory = root / "not-a-file"
            directory.mkdir()
            report = legacy_values_discovery.DiscoveryReport(str(root))
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "regular file"):
                legacy_values_discovery._record_artifact(report, root, directory, "fixture")

    def test_artifact_tree_nested_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "values"
            tree = root / "tree"
            outside = Path(temp_dir) / "outside"
            tree.mkdir(parents=True)
            outside.mkdir()
            (outside / "artifact.txt").write_text("outside", encoding="utf-8")
            (tree / "linked.txt").symlink_to(outside / "artifact.txt")
            report = legacy_values_discovery.DiscoveryReport(str(root))
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "symlinks"):
                legacy_values_discovery._record_artifact_tree(report, root, tree, "fixture")

    def test_artifact_tree_root_must_be_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "values"
            root.mkdir()
            file_path = root / "not-a-tree"
            file_path.write_text("file", encoding="utf-8")
            report = legacy_values_discovery.DiscoveryReport(str(root))
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "tree must be a directory"):
                legacy_values_discovery._record_artifact_tree(report, root, file_path, "fixture")

    def test_bounded_report_requires_manual_review_for_canonical_conflicts(self) -> None:
        migration = legacy_values_discovery._load_migration_module()
        report = legacy_values_discovery.DiscoveryReport("/tmp/values")
        legacy_values_discovery._observe("env", "SERVER_NAME", "dns-a.example.internal", report, migration)
        legacy_values_discovery._observe("inventory", "server_name", "dns-b.example.internal", report, migration)
        self.assertEqual(2, len(report.observations))
        self.assertEqual("services.technitium.endpoints.public_names", report.observations[0].proposed_path)
        self.assertEqual("manual review required", report.conflicts[0]["disposition"])
        self.assertFalse(report.mapping_ready)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_invalid_caddy_email(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    caddy_email: acme.example.internal\n", encoding="utf-8")
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "email address"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_forgejo_bootstrap_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_bootstrap_admin_username: forgejo-admin\n"
                "    forgejo_bootstrap_admin_email: admin@example.internal\n"
                "    forgejo_bootstrap_owner_email: owner@example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "forgejo_bootstrap_admin_username": "services.forgejo.configuration.bootstrap_admin_username",
            "forgejo_bootstrap_admin_email": "services.forgejo.configuration.bootstrap_admin_email",
            "forgejo_bootstrap_owner_email": "services.forgejo.configuration.bootstrap_owner_email",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_forgejo_database_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_database:\n"
                "      type: postgres\n"
                "      managed: false\n"
                "      host: db.example.internal\n"
                "      port: 5432\n"
                "      name: forgejo\n"
                "      user: forgejo\n"
                "      ssl_mode: require\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("forgejo_database", "mapped")].proposed_path,
            "services.forgejo.configuration.database",
        )
        self.assertEqual(
            observations[("forgejo_database", "mapped")].value["port"],
            5432,
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_invalid_forgejo_database_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_database:\n"
                "      type: postgres\n"
                "      port: 70000\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "valid database metadata"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_forgejo_database_shape(self) -> None:
        invalid_documents = [
            "all:\n  vars:\n    forgejo_database: {type: postgres, host: db}\n",
            "all:\n  vars:\n    forgejo_database: {type: sqlite, name: forgejo}\n",
        ]
        for document in invalid_documents:
            temp, values = self.make_values()
            with temp:
                repo = Path(temp.name) / "repo"
                inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
                inventory.parent.mkdir(parents=True)
                inventory.write_text(document, encoding="utf-8")
                with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "valid database metadata"):
                    legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_forgejo_bootstrap_identity(self) -> None:
        invalid_values = {
            "forgejo_bootstrap_admin_username": "Admin.User",
            "forgejo_bootstrap_admin_email": "admin.example.com",
            "forgejo_bootstrap_owner_email": "owner@",
        }
        for key, value in invalid_values.items():
            with self.subTest(key=key):
                temp, values = self.make_values()
                with temp:
                    repo = Path(temp.name) / "repo"
                    inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
                    inventory.parent.mkdir(parents=True)
                    inventory.write_text(f"all:\n  vars:\n    {key}: {value}\n", encoding="utf-8")
                    with self.assertRaises(legacy_values_discovery.DiscoveryError):
                        legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_service_resource_vmids(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_vmid: 109\n"
                "    hermes_vmid: 111\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "forgejo_runner_vmid": "resources.guests.forgejo_runner.identity.vmid",
            "hermes_vmid": "resources.guests.hermes.identity.vmid",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_technitium_api_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_api_url: https://dns.example.internal/api/\n"
                "    technitium_admin_user: admin\n"
                "    TECHNITIUM_API_TOKEN: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("technitium_api_url", "mapped")].proposed_path,
            "services.technitium.configuration.api_url",
        )
        self.assertEqual(
            observations[("technitium_api_url", "mapped")].value,
            "https://dns.example.internal/api/",
        )
        self.assertEqual(
            observations[("technitium_admin_user", "mapped")].proposed_path,
            "services.technitium.configuration.admin_user",
        )
        self.assertEqual(observations[("TECHNITIUM_API_TOKEN", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_tailscale_forwarding_policy(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    tailscale_client_enable_ip_forwarding: true\n"
                "    TAILSCALE_AUTH_KEY: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("tailscale_client_enable_ip_forwarding", "mapped")].proposed_path,
            "services.tailscale_client.configuration.enable_ip_forwarding",
        )
        self.assertEqual(observations[("TAILSCALE_AUTH_KEY", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_tailscale_restore_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    tailscale_client_restore_backup: false\n"
                "    tailscale_client_backup_archive: /srv/tailscale/backup.tar\n"
                "    TAILSCALE_AUTH_KEY: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("tailscale_client_restore_backup", "mapped")].proposed_path,
            "services.tailscale_client.configuration.restore_backup",
        )
        self.assertEqual(
            observations[("tailscale_client_backup_archive", "mapped")].proposed_path,
            "services.tailscale_client.configuration.backup_archive",
        )
        self.assertEqual(observations[("TAILSCALE_AUTH_KEY", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_tailscale_up_args(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    tailscale_client_up_args:\n"
                "      - --accept-dns=false\n"
                "      - --ssh\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("tailscale_client_up_args", "mapped")].proposed_path,
            "services.tailscale_client.configuration.up_args",
        )
        self.assertEqual(
            observations[("tailscale_client_up_args", "mapped")].value,
            ["--accept-dns=false", "--ssh"],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_service_vmids(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_vmid: 106\n"
                "    forgejo_vmid: 107\n"
                "    tailscale_client_vmid: 108\n"
                "    infisical_vmid: 109\n"
                "    forgejo_runner_vmid: 110\n"
                "    hermes_vmid: 111\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "technitium_vmid": "resources.guests.technitium.identity.vmid",
            "forgejo_vmid": "resources.guests.forgejo.identity.vmid",
            "tailscale_client_vmid": "resources.guests.tailscale_client.identity.vmid",
            "infisical_vmid": "resources.guests.infisical.identity.vmid",
            "forgejo_runner_vmid": "resources.guests.forgejo_runner.identity.vmid",
            "hermes_vmid": "resources.guests.hermes.identity.vmid",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(observations[("technitium_vmid", "mapped")].value, 106)
        self.assertEqual(observations[("forgejo_vmid", "mapped")].value, 107)
        self.assertEqual(observations[("tailscale_client_vmid", "mapped")].value, 108)
        self.assertEqual(observations[("infisical_vmid", "mapped")].value, 109)
        self.assertEqual(observations[("forgejo_runner_vmid", "mapped")].value, 110)
        self.assertEqual(observations[("hermes_vmid", "mapped")].value, 111)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_invalid_service_vmid(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_vmid: 0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "positive integer"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_technitium_transport_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_api_url: https://dns.example.internal:5380\n"
                "    technitium_admin_user: administrator\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("technitium_api_url", "mapped")].proposed_path,
            "services.technitium.configuration.api_url",
        )
        self.assertEqual(
            observations[("technitium_admin_user", "mapped")].proposed_path,
            "services.technitium.configuration.admin_user",
        )
        self.assertEqual(observations[("technitium_api_url", "mapped")].value, "https://dns.example.internal:5380/")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_technitium_api_credentials(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_api_url: https://user:password@dns.example.internal:5380\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "HTTP\\(S\\) URL without credentials"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_technitium_release_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            digest = "a" * 64
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_discovery_version: 13.2.1\n"
                f"    technitium_portable_sha256: {digest}\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("technitium_discovery_version", "mapped")].proposed_path,
            "services.technitium.release.version",
        )
        self.assertEqual(
            observations[("technitium_portable_sha256", "mapped")].proposed_path,
            "services.technitium.release.checksum",
        )
        self.assertEqual(observations[("technitium_portable_sha256", "mapped")].value, digest)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_malformed_technitium_digest(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    technitium_portable_sha256: not-a-digest\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "64-character SHA-256 digest"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_malformed_hermes_wheel_digest(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_discovery_wheel_sha256: invalid\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "64-character SHA-256 digest"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_blank_hermes_release_identifier(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_discovery_tag: '   '\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "managed Hermes release-tag form"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_malformed_hermes_node_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_node_sha256_amd64: invalid\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "64-character SHA-256 digest"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_blank_hermes_node_version(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_node_version: '   '\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "strict semantic version"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_hermes_dashboard_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_dashboard_enabled: yes\n"
                "    hermes_dashboard_port: 65536\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "between 1 and 65535"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_blank_hermes_dashboard_host(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_dashboard_host: '   '\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "loopback-only"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_hermes_control_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_control_api_port: 0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "between 1 and 65535"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_blank_hermes_control_socket(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_control_plugin_socket: '   '\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "normalized absolute POSIX path"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_hermes_tuning_and_web_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_compression_threshold: 0.8\n"
                "    hermes_max_concurrent_children: 4\n"
                "    hermes_max_spawn_depth: 2\n"
                "    hermes_web_searxng_url: https://searxng.example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "hermes_compression_threshold": "services.hermes.configuration.tuning.compression_threshold",
            "hermes_max_concurrent_children": "services.hermes.configuration.tuning.max_concurrent_children",
            "hermes_max_spawn_depth": "services.hermes.configuration.tuning.max_spawn_depth",
            "hermes_web_searxng_url": "services.hermes.configuration.web.searxng_url",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(observations[("hermes_web_searxng_url", "mapped")].value, "https://searxng.example.internal")
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_invalid_hermes_tuning(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_max_spawn_depth: 4\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "outside its canonical range"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_hermes_web_credentials(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_web_searxng_url: https://user:password@searxng.example.internal\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "HTTP\\(S\\) URL without credentials"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_hermes_runtime_policy(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_allow_legacy_runtime: maybe\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "must be boolean"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_hermes_remaining_contract_metadata(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            commit = "e" * 40
            inventory.write_text(
                "all:\n  vars:\n"
                "    hermes_domain: hermes.example.internal\n"
                "    hermes_runtime_user: hermes\n"
                "    hermes_repo_path: /opt/hermes\n"
                "    HERMES_CONTROL_SOURCE_URL: https://github.com/example/hermes\n"
                f"    HERMES_CONTROL_SOURCE_REF: {commit}\n"
                "    hermes_control_enabled: true\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "hermes_domain": "services.hermes.endpoints.public_names",
            "hermes_runtime_user": "services.hermes.configuration.runtime_user",
            "hermes_repo_path": "services.hermes.configuration.repository_path",
            "HERMES_CONTROL_SOURCE_URL": "services.hermes.configuration.control.source_url",
            "HERMES_CONTROL_SOURCE_REF": "services.hermes.configuration.control.source_ref",
            "hermes_control_enabled": "services.hermes.configuration.control.enabled",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(observations[("HERMES_CONTROL_SOURCE_REF", "mapped")].value, commit)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_hermes_contract_boundary_values(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    HERMES_CONTROL_SOURCE_REF: main\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "lowercase 40-character commit"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_searxng_service_boundary(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    searxng_server_name: search.example.internal\n"
                "    searxng_public_url: https://search.example.internal/search\n"
                "    searxng_container_image: ghcr.io/example/searxng@sha256:" + "a" * 64 + "\n"
                "    searxng_container_port: 8080\n"
                "    searxng_bind_address: 127.0.0.1\n"
                "    searxng_instance_name: primary\n"
                "    searxng_enable_public_url: true\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "searxng_server_name": "services.searxng_onramp.endpoints.public_names.0",
            "searxng_public_url": "services.searxng_onramp.endpoints.public_url",
            "searxng_container_image": "services.searxng_onramp.release",
            "searxng_container_port": "services.searxng_onramp.configuration.container_port",
            "searxng_bind_address": "services.searxng_onramp.configuration.bind_address",
            "searxng_instance_name": "services.searxng_onramp.configuration.instance_name",
            "searxng_enable_public_url": "services.searxng_onramp.configuration.enable_public_url",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_searxng_public_url_credentials(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    searxng_public_url: https://user:password@example.internal/search\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "HTTPS URL without credentials"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_forgejo_configuration(self) -> None:
        invalid_values = {
            "forgejo_domain": "bad_domain.example.internal",
            "forgejo_version": "",
            "forgejo_enable_caddy": "true",
            "forgejo_bootstrap_admin_username": "",
        }
        for key, invalid_value in invalid_values.items():
            with self.subTest(key=key):
                temp, values = self.make_values()
                with temp:
                    repo = Path(temp.name) / "repo"
                    inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
                    inventory.parent.mkdir(parents=True)
                    rendered = repr(invalid_value) if isinstance(invalid_value, str) else str(invalid_value).lower()
                    inventory.write_text(f"all:\n  vars:\n    {key}: {rendered}\n", encoding="utf-8")
                    with self.assertRaises(legacy_values_discovery.DiscoveryError):
                        legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_technitium_admin_user(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    technitium_admin_user: Admin.User\n", encoding="utf-8")
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "Linux user identifier"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_forgejo_aliases(self) -> None:
        invalid_values = {
            "FORGEJO_DOMAIN": "bad_domain.example.internal",
            "FORGEJO_SSH_PORT": 0,
            "FORGEJO_ACTIONS_ENABLED": "true",
            "FORGEJO_ACTIONS_DEFAULT_URL": "http://actions.example.internal",
        }
        for key, value in invalid_values.items():
            with self.subTest(key=key):
                temp, values = self.make_values()
                with temp:
                    repo = Path(temp.name) / "repo"
                    inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
                    inventory.parent.mkdir(parents=True)
                    rendered = repr(value) if isinstance(value, str) else str(value)
                    inventory.write_text(f"all:\n  vars:\n    {key}: {rendered}\n", encoding="utf-8")
                    with self.assertRaises(legacy_values_discovery.DiscoveryError):
                        legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_tailscale_policy_boundary(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    tailscale_client_enabled: true\n"
                "    tailscale_client_restore_backup: false\n"
                "    tailscale_client_backup_archive: /var/backups/tailscale.tar\n"
                "    tailscale_client_enable_ip_forwarding: true\n"
                "    tailscale_client_up_args: [--advertise-tags=tag:server, --ssh]\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "tailscale_client_enabled": "services.tailscale_client.enabled",
            "tailscale_client_restore_backup": "services.tailscale_client.configuration.restore_backup",
            "tailscale_client_backup_archive": "services.tailscale_client.configuration.backup_archive",
            "tailscale_client_enable_ip_forwarding": "services.tailscale_client.configuration.enable_ip_forwarding",
            "tailscale_client_up_args": "services.tailscale_client.configuration.up_args",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_invalid_tailscale_policy(self) -> None:
        invalid_values = {
            "tailscale_client_enabled": "yes",
            "tailscale_client_restore_backup": 1,
            "tailscale_client_enable_ip_forwarding": "true",
            "tailscale_client_backup_archive": "",
        }
        for key, invalid_value in invalid_values.items():
            with self.subTest(key=key):
                temp, values = self.make_values()
                with temp:
                    repo = Path(temp.name) / "repo"
                    inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
                    inventory.parent.mkdir(parents=True)
                    rendered = repr(invalid_value) if isinstance(invalid_value, str) else str(invalid_value).lower()
                    inventory.write_text(f"all:\n  vars:\n    {key}: {rendered}\n", encoding="utf-8")
                    with self.assertRaises(legacy_values_discovery.DiscoveryError):
                        legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_invalid_infisical_metadata(self) -> None:
        invalid_values = {
            "infisical_data_dir": "../var/lib/infisical",
            "infisical_postgres_user": "infisical-user",
            "infisical_postgres_db": "infisical-db",
            "infisical_domain": "bad_domain.example.internal",
        }
        for key, invalid_value in invalid_values.items():
            with self.subTest(key=key):
                temp, values = self.make_values()
                with temp:
                    repo = Path(temp.name) / "repo"
                    inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
                    inventory.parent.mkdir(parents=True)
                    inventory.write_text(f"all:\n  vars:\n    {key}: {invalid_value}\n", encoding="utf-8")
                    with self.assertRaises(legacy_values_discovery.DiscoveryError):
                        legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_caddy_ingress_boundary(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_email: admin@example.internal\n"
                "    caddy_server_name: dns.example.internal\n"
                "    caddy_server_names: [dns.example.internal, app.example.internal]\n"
                "    caddy_upstream: 127.0.0.1:5380\n"
                "    caddy_extra_vhosts:\n"
                "      - server_names: [app.example.internal]\n"
                "        upstream: 127.0.0.1:8080\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "caddy_email": "platform.ingress.acme.email",
            "caddy_server_name": "services.technitium.configuration.caddy.server_names",
            "caddy_server_names": "services.technitium.configuration.caddy.server_names",
            "caddy_upstream": "services.technitium.configuration.caddy.upstream",
            "caddy_extra_vhosts": "services.technitium.configuration.caddy.extra_vhosts",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_invalid_caddy_server_names(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    caddy_server_names: [Example.Internal, example.internal]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "unique hostnames"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_forgejo_service_boundary(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_root_url: https://forgejo.example.internal/\n"
                "    FORGEJO_ROOT_URL: https://forgejo.example.internal/\n"
                "    forgejo_ssh_port: 2222\n"
                "    FORGEJO_SSH_PORT: 2222\n"
                "    forgejo_actions_enabled: true\n"
                "    FORGEJO_ACTIONS_ENABLED: true\n"
                "    forgejo_actions_default_url: https://forgejo.example.internal/actions\n"
                "    FORGEJO_ACTIONS_DEFAULT_URL: https://forgejo.example.internal/actions\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "forgejo_root_url": "services.forgejo.endpoints.public_url",
            "forgejo_ssh_port": "services.forgejo.endpoints.ports.ssh",
            "forgejo_actions_enabled": "services.forgejo.configuration.actions_enabled",
            "forgejo_actions_default_url": "services.forgejo.configuration.actions_default_url",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_forgejo_service_boundary_values(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_root_url: https://user:password@example.internal/\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "HTTPS URL without credentials"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_forgejo_runner_boundary(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_version: 0.2.0\n"
                "    forgejo_runner_url: https://forgejo.example.internal\n"
                "    forgejo_runner_name: runner-1\n"
                "    forgejo_runner_scope: org\n"
                "    forgejo_runner_label: linux-amd64\n"
                "    forgejo_runner_labels: [linux-amd64, docker]\n"
                "    forgejo_runner_hosts:\n"
                "      - {name: runner-1, address: 10.0.0.10}\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "forgejo_runner_version": "services.forgejo_runner.release.version",
            "forgejo_runner_url": "services.forgejo_runner.configuration.url",
            "forgejo_runner_name": "services.forgejo_runner.configuration.name",
            "forgejo_runner_scope": "services.forgejo_runner.configuration.scope",
            "forgejo_runner_label": "services.forgejo_runner.configuration.label",
            "forgejo_runner_labels": "services.forgejo_runner.configuration.labels",
            "forgejo_runner_hosts": "services.forgejo_runner.configuration.hosts",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_forgejo_runner_url_credentials(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_url: https://runner:password@example.internal\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "HTTPS URL without credentials"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_forgejo_runner_labels(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_labels:\n"
                "      - docker\n"
                "      - linux-amd64\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("forgejo_runner_labels", "mapped")].proposed_path,
            "services.forgejo_runner.configuration.labels",
        )
        self.assertEqual(
            observations[("forgejo_runner_labels", "mapped")].value,
            ["docker", "linux-amd64"],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_admits_forgejo_runner_hosts(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_hosts:\n"
                "      - name: forgejo\n"
                "        address: forgejo.example.internal\n"
                "      - name: runner\n"
                "        address: runner.example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(
            observations[("forgejo_runner_hosts", "mapped")].proposed_path,
            "services.forgejo_runner.configuration.hosts",
        )
        self.assertEqual(
            observations[("forgejo_runner_hosts", "mapped")].value,
            [
                {"name": "forgejo", "address": "forgejo.example.internal"},
                {"name": "runner", "address": "runner.example.internal"},
            ],
        )
        self.assertFalse(report.candidate_ready)

    def test_bounded_ansible_importer_rejects_malformed_forgejo_runner_hosts(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    forgejo_runner_hosts:\n"
                "      - name: forgejo\n"
                "        address: ''\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "name/address objects"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_rejects_non_string_tailscale_up_args(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    tailscale_client_up_args:\n"
                "      - 22\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_values_discovery.DiscoveryError, "list of strings"):
                legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)

    def test_bounded_ansible_importer_admits_searxng_configuration(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "all:\n  vars:\n"
                "    searxng_container_port: 8080\n"
                "    searxng_bind_address: 127.0.0.1\n"
                "    searxng_instance_name: Homelab SearXNG\n"
                "    searxng_enable_public_url: true\n"
                "    SEARXNG_SECRET_KEY: SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        expected = {
            "searxng_container_port": "services.searxng_onramp.configuration.container_port",
            "searxng_bind_address": "services.searxng_onramp.configuration.bind_address",
            "searxng_instance_name": "services.searxng_onramp.configuration.instance_name",
            "searxng_enable_public_url": "services.searxng_onramp.configuration.enable_public_url",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertEqual(observations[(key, "mapped")].proposed_path, canonical_path)
        self.assertEqual(observations[("SEARXNG_SECRET_KEY", "secret")].value, "<redacted>")
        self.assertFalse(report.candidate_ready)

    def test_forgejo_server_name_maps_to_normalized_public_name(self) -> None:
        temp, values = self.make_values()
        with temp:
            report = legacy_values_discovery.discover_legacy(values)
        observations = [item for item in report.observations if item.key == "forgejo_server_name"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].classification, "mapped")
        self.assertEqual(observations[0].proposed_path, "services.forgejo.endpoints.public_names")
        self.assertEqual(observations[0].value, ["git.example.internal"])

    def test_equivalent_forgejo_names_do_not_conflict_after_normalization(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "FORGEJO_DOMAIN=git.example.internal\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values)
        self.assertFalse([item for item in report.conflicts if item["canonical_path"] == "services.forgejo.endpoints.public_names"])

    def test_different_forgejo_names_conflict_and_remain_fail_closed(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("FORGEJO_DOMAIN=other.example.internal\n", encoding="utf-8")
            report = legacy_values_discovery.discover_legacy(values)
        self.assertFalse(report.candidate_ready)
        self.assertEqual(report.conflicts[0]["canonical_path"], "services.forgejo.endpoints.public_names")

    def test_server_name_maps_to_normalized_technitium_public_name(self) -> None:
        temp, values = self.make_values()
        with temp:
            report = legacy_values_discovery.discover_legacy(values)
        observations = [item for item in report.observations if item.key == "SERVER_NAME"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].classification, "mapped")
        self.assertEqual(observations[0].proposed_path, "services.technitium.endpoints.public_names")
        self.assertEqual(observations[0].value, ["dns.example.internal"])

    def test_server_name_conflict_remains_fail_closed(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / "terraform.tfvars").write_text(
                'SERVER_NAME = "other.example.internal"\n',
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values)
        self.assertFalse(report.candidate_ready)
        self.assertEqual(report.conflicts[0]["canonical_path"], "services.technitium.endpoints.public_names")

    def test_infisical_server_name_maps_to_normalized_public_name(self) -> None:
        temp, values = self.make_values()
        with temp:
            with (values / "terraform.tfvars").open("a", encoding="utf-8") as stream:
                stream.write('infisical_server_name = "Vault.Example.Internal."\n')
            report = legacy_values_discovery.discover_legacy(values)
        observations = [item for item in report.observations if item.key == "infisical_server_name"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].classification, "mapped")
        self.assertEqual(observations[0].proposed_path, "services.infisical.endpoints.public_names")
        self.assertEqual(observations[0].value, ["vault.example.internal"])

    def test_infisical_domain_maps_to_normalized_public_name(self) -> None:
        temp, values = self.make_values()
        with temp:
            with (values / "terraform.tfvars").open("a", encoding="utf-8") as stream:
                stream.write('infisical_domain = "Domain.Example.Internal."\n')
            report = legacy_values_discovery.discover_legacy(values)
        observations = [item for item in report.observations if item.key == "infisical_domain"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].proposed_path, "services.infisical.endpoints.public_names")
        self.assertEqual(observations[0].value, ["domain.example.internal"])

    def test_infisical_server_name_conflict_remains_fail_closed(self) -> None:
        temp, values = self.make_values()
        with temp:
            with (values / "terraform.tfvars").open("a", encoding="utf-8") as stream:
                stream.write(
                    'infisical_server_name = "one.example.internal"\n'
                    'INFISICAL_SERVER_NAME = "two.example.internal"\n'
                )
            report = legacy_values_discovery.discover_legacy(values)
        self.assertFalse(report.candidate_ready)
        self.assertEqual(report.conflicts[0]["canonical_path"], "services.infisical.endpoints.public_names")

    def test_conflicting_sources_are_reported_and_block_candidate(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / "terraform.tfvars").write_text(
                'technitium_api_url = "http://192.0.2.54:5380/api"\n',
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values)
        self.assertFalse(report.candidate_ready)
        self.assertEqual(report.conflicts[0]["canonical_path"], "services.technitium.endpoints.public_url")
        self.assertEqual(report.conflicts[0]["disposition"], "manual review required")

    def test_incomplete_mapping_refuses_candidate(self) -> None:
        temp, values = self.make_values()
        with temp:
            report = legacy_values_discovery.discover_legacy(values)
            self.assertFalse(report.candidate_ready)
            with self.assertRaises(legacy_values_discovery.DiscoveryError):
                legacy_values_discovery.build_candidate_site(
                    report,
                    base_document={"schema_version": 1},
                )

    def test_secret_only_report_remains_fail_closed(self) -> None:
        temp = tempfile.TemporaryDirectory()
        values = Path(temp.name) / "values"
        values.mkdir()
        (values / ".env").write_text(
            "TECHNITIUM_API_TOKEN=SECRET_SENTINEL_DO_NOT_PRINT\n",
            encoding="utf-8",
        )
        with temp:
            report = legacy_values_discovery.discover_legacy(values)
            self.assertFalse(report.candidate_ready)
            rendered = json.dumps(legacy_values_discovery.render_migration_report(report))
        self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", rendered)

    def test_rendered_report_exposes_complete_secret_contract_without_values(self) -> None:
        temp = tempfile.TemporaryDirectory()
        values = Path(temp.name) / "values"
        values.mkdir()
        (values / ".env").write_text(
            "TECHNITIUM_API_TOKEN=SECRET_SENTINEL_DO_NOT_PRINT\n",
            encoding="utf-8",
        )
        repo = Path(temp.name) / "repo"
        inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
        inventory.parent.mkdir(parents=True)
        inventory.write_text(
            "all:\n  vars:\n"
            "    CF_DNS_API_TOKEN: PROVIDER_SECRET_SENTINEL_DO_NOT_PRINT\n"
            "    CF_API_EMAIL: operator@example.internal\n",
            encoding="utf-8",
        )
        with temp:
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
            rendered = legacy_values_discovery.render_migration_report(report)
            serialized = json.dumps(rendered)
        contract = rendered["secret_contract"]
        self.assertEqual(contract["secret_count"], 2)
        self.assertEqual(contract["protected_count"], 1)
        self.assertEqual(contract["redacted_count"], 3)
        self.assertEqual(contract["proposed_path_count"], 0)
        self.assertFalse(contract["candidate_generation_allowed"])
        self.assertEqual(contract["status"], "complete")
        self.assertFalse(rendered["candidate_ready"])
        self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", serialized)
        self.assertNotIn("PROVIDER_SECRET_SENTINEL_DO_NOT_PRINT", serialized)

    def test_cli_writes_redacted_report_with_restricted_mode(self) -> None:
        temp, values = self.make_values()
        with temp:
            output = values.parent / "report.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = legacy_values_discovery_cli.main(
                    ["--values-dir", str(values), "--output", str(output)]
                )
            self.assertEqual(result, 0)
            self.assertIn("wrote redacted legacy discovery report", stdout.getvalue())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            rendered = output.read_text(encoding="utf-8")
            self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", rendered)
            self.assertIn("TECHNITIUM_API_TOKEN", rendered)

    def test_site_aware_metadata_is_reported_without_mutation(self) -> None:
        temp, values = self.make_values()
        with temp:
            metadata = {
                "name": "dev",
                "class": "development",
                "lifecycle": "disposable",
                "allow_apply": True,
                "allow_destroy": True,
                "services": ["forgejo"],
            }
            site = values / "site.json"
            site.write_text(json.dumps(metadata), encoding="utf-8")
            report = legacy_values_discovery.discover_legacy(values)
            rendered = legacy_values_discovery.render_migration_report(report)
            self.assertTrue(site.exists())
        self.assertEqual(rendered["site_metadata"], {key: metadata[key] for key in ("name", "class", "lifecycle", "allow_apply", "allow_destroy")})

    def test_cli_admits_bounded_public_ansible_inventory_slice(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    forgejo_domain: git.example.internal\n    forgejo_version: 12.0.4\n    forgejo_root_url: https://git.example.internal\n    forgejo_bootstrap_admin_email: review@example.internal\n", encoding="utf-8")
            output = values.parent / "ansible-report.json"
            result = legacy_values_discovery_cli.main(
                [
                    "--values-dir", str(values),
                    "--repo", str(repo),
                    "--ansible-inventory", str(inventory),
                    "--output", str(output),
                ]
            )
            self.assertEqual(result, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
        mapped = [item for item in payload["observations"] if item["key"] == "forgejo_domain"]
        version = [item for item in payload["observations"] if item["key"] == "forgejo_version"]
        self.assertTrue(mapped)
        self.assertTrue(version)
        self.assertTrue(any(item["key"] == "forgejo_bootstrap_admin_email" and item["classification"] == "mapped" and item["proposed_path"] == "services.forgejo.configuration.bootstrap_admin_email" for item in payload["observations"]))
        self.assertFalse(payload["candidate_ready"])

    def test_cli_reports_invalid_values_directory_without_traceback(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = legacy_values_discovery_cli.main(["--values-dir", "/not/a/real/values-dir"])
        self.assertEqual(result, 1)
        self.assertIn("legacy discovery failed:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_rejects_report_output_inside_values_directory(self) -> None:
        temp, values = self.make_values()
        with temp:
            output = values / "report.json"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = legacy_values_discovery_cli.main(
                    ["--values-dir", str(values), "--output", str(output)]
                )
            self.assertEqual(result, 1)
            self.assertIn("outside the legacy values directory", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_rejects_malformed_json_without_output_artifact(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / "settings.local.json").write_text("{not-json}\n", encoding="utf-8")
            output = values.parent / "report.json"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = legacy_values_discovery_cli.main(
                    ["--values-dir", str(values), "--output", str(output)]
                )
            self.assertEqual(result, 1)
            self.assertIn("invalid JSON legacy input", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_forgejo_version_maps_to_release_version(self) -> None:
        temp, values = self.make_values()
        with temp:
            with (values / "terraform.tfvars").open("a", encoding="utf-8") as stream:
                stream.write('FORGEJO_VERSION = "1.2.3"\n')
            report = legacy_values_discovery.discover_legacy(values)
        observations = [item for item in report.observations if item.key == "FORGEJO_VERSION"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].proposed_path, "services.forgejo.release.version")
        self.assertEqual(observations[0].value, "1.2.3")

    def test_forgejo_ssh_port_maps_to_canonical_port(self) -> None:
        temp, values = self.make_values()
        with temp:
            with (values / "terraform.tfvars").open("a", encoding="utf-8") as stream:
                stream.write("FORGEJO_SSH_PORT = 2222\n")
            report = legacy_values_discovery.discover_legacy(values)
        observations = [item for item in report.observations if item.key == "FORGEJO_SSH_PORT"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].proposed_path, "services.forgejo.endpoints.ports.ssh")
        self.assertEqual(observations[0].value, 2222)


    def test_runtime_importer_admission_is_scoped_and_fail_closed(self) -> None:
        complete = legacy_values_discovery.DiscoveryReport(values_dir="/tmp/values")
        complete.observations.extend(
            [
                legacy_values_discovery.FieldObservation("inventory", "forgejo_domain", "mapped", "services.forgejo.endpoints.public_names", "list", ["git.example.internal"]),
                legacy_values_discovery.FieldObservation("inventory", "forgejo_root_url", "mapped", "services.forgejo.endpoints.public_url", "str", "https://git.example.internal/"),
            ]
        )
        admission = legacy_values_discovery.runtime_importer_admission(complete)
        self.assertTrue(admission["admitted"])
        self.assertEqual(admission["status"], "complete")
        self.assertEqual(admission["missing"], [])

        blocked = legacy_values_discovery.DiscoveryReport(values_dir="/tmp/values")
        blocked.observations.append(
            legacy_values_discovery.FieldObservation("inventory", "forgejo_domain", "unsupported", None, "dynamic-expression", None)
        )
        blocked.conflicts.append({"canonical_path": "services.forgejo.endpoints.public_url"})
        admission = legacy_values_discovery.runtime_importer_admission(blocked)
        self.assertFalse(admission["admitted"])
        self.assertEqual(admission["status"], "blocked")
        self.assertEqual(admission["missing"], ["forgejo_root_url"])
        self.assertEqual(admission["conflicts"], ["services.forgejo.endpoints.public_url"])

        report = legacy_values_discovery.DiscoveryReport(values_dir="/tmp/values")
        report.observations.extend(
            [
                legacy_values_discovery.FieldObservation(
                    ".env", "SERVER_NAME", "mapped", "services.technitium.endpoints.public_names", "list", ["dns.example.internal"]
                ),
                legacy_values_discovery.FieldObservation(
                    ".env", "TECHNITIUM_API_TOKEN", "secret", None, "str", "<redacted>"
                ),
            ]
        )
        base = {"schema_version": 1, "site": {"name": "old"}, "services": {"technitium": {"enabled": True}}}

        candidate = legacy_values_discovery.build_candidate_site(
            report,
            base_document=base,
            site_name="dev",
            runtime_importer_admission={"admitted": True},
        )

        self.assertEqual(candidate["site"]["name"], "dev")
        self.assertEqual(candidate["services"]["technitium"]["endpoints"]["public_names"], ["dns.example.internal"])
        self.assertNotIn("TECHNITIUM_API_TOKEN", json.dumps(candidate))


    def test_cli_writes_public_candidate_with_restricted_mode(self) -> None:
        temp = tempfile.TemporaryDirectory()
        values = Path(temp.name) / "values"
        values.mkdir()
        (values / ".env").write_text("SERVER_NAME=DNS.Example.Internal.\n", encoding="utf-8")
        base = Path(temp.name) / "base.yaml"
        base.write_text("schema_version: 1\nsite:\n  name: old\nservices: {}\n", encoding="utf-8")
        output = Path(temp.name) / "candidate.yaml"
        stdout = io.StringIO()
        with temp:
            with redirect_stdout(stdout):
                result = legacy_values_discovery_cli.main(
                    [
                        "--values-dir", str(values),
                        "--candidate-base", str(base),
                        "--candidate-output", str(output),
                        "--site", "dev",
                    ]
                )
            self.assertEqual(result, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

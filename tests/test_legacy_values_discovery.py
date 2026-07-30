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
        self.assertTrue(
            any(
                item.key == "forgejo_bootstrap_admin_email"
                and item.classification == "unsupported"
                and item.value is None
                for item in report.observations
            )
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
        self.assertTrue(any(item["key"] == "forgejo_bootstrap_admin_email" and item["classification"] == "unsupported" and item["value"] is None for item in payload["observations"]))
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


    def test_candidate_generation_overlays_public_values_and_omits_secrets(self) -> None:
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
            report, base_document=base, site_name="dev", runtime_importer_ready=True
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

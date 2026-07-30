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
                "all:\n  vars:\n    forgejo_domain: git.example.internal\n    forgejo_version: 12.0.4\n    forgejo_bootstrap_admin_email: review@example.internal\n    forgejo_download_base: '{% dynamic %}'\n    forgejo_ssh_port: 22\n    forgejo_enable_caddy: true\n    forgejo_configure_system_ssh: true\n    forgejo_write_initial_config: false\n    forgejo_bootstrap_enabled: true\n    forgejo_actions_enabled: true\n    forgejo_actions_default_url: https://data.forgejo.org\n"
                "  hosts:\n    edge:\n",
                encoding="utf-8",
            )
            report = legacy_values_discovery.discover_legacy(values, repo=repo, ansible_inventory=inventory)
        observations = {(item.key, item.classification): item for item in report.observations}
        self.assertEqual(observations[("forgejo_domain", "mapped")].value, ["git.example.internal"])
        self.assertEqual(observations[("forgejo_version", "mapped")].value, "12.0.4")
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

    def test_cli_admits_bounded_public_ansible_inventory_slice(self) -> None:
        temp, values = self.make_values()
        with temp:
            repo = Path(temp.name) / "repo"
            inventory = repo / "scaffold" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all:\n  vars:\n    forgejo_domain: git.example.internal\n    forgejo_version: 12.0.4\n    forgejo_bootstrap_admin_email: review@example.internal\n", encoding="utf-8")
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

from __future__ import annotations

import importlib.util
import io
import json
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

    def test_discovery_is_byte_for_byte_non_mutating(self) -> None:
        temp, values = self.make_values()
        with temp:
            before = {path: path.read_bytes() for path in values.rglob("*") if path.is_file()}
            report = legacy_values_discovery.discover_legacy(values)
            after = {path: path.read_bytes() for path in values.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((values / "site.yaml").exists())
        self.assertIn(".env", report.files)

    def test_report_redacts_secret_and_unknown_values(self) -> None:
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
                legacy_values_discovery.build_candidate_site(report)

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


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("service_author", ROOT / "scripts" / "service-author.py")
service_author = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(service_author)


class ServiceAuthorTests(unittest.TestCase):
    def test_repository_surface_check_rejects_missing_service_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "infra").mkdir()
            (repo / "scripts").mkdir()
            (repo / "tests").mkdir()
            (repo / "infra" / "services.json").write_text('{"services": {}}', encoding="utf-8")
            errors = service_author.validate_repository_surfaces(repo, "metrics")
            self.assertIn("catalog registration", errors[0])

    def test_repository_surface_check_accepts_complete_service_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for relative in (
                "infra/services.json",
                "scripts/canonical_values.py",
                "scripts/canonical_projections.py",
                "infra/opentofu/metrics.tf",
                "infra/ansible/playbooks/metrics.yml",
                "infra/ansible/roles/metrics/tasks/main.yml",
                "tests/test_metrics.py",
                "docs/metrics.md",
                "scaffold/fixtures/metrics.yaml",
            ):
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                content = "metrics\nMetricsConfiguration\n" if relative.endswith("canonical_values.py") else "metrics\n"
                path.write_text(content, encoding="utf-8")
            (repo / "infra/services.json").write_text(
                json.dumps({
                    "services": {
                        "metrics": {
                            "configuration_schema": "MetricsConfiguration",
                            "release_sources": ["binary"],
                            "allowed_override_namespaces": ["ansible"],
                            "required_fields": ["resource"],
                            "runtime_owner": "guest",
                        }
                    }
                }),
                encoding="utf-8",
            )
            self.assertEqual(service_author.validate_repository_surfaces(repo, "metrics"), [])

    def test_repository_surface_check_rejects_incomplete_catalog_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            catalog = repo / "infra" / "services.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text('{"services": {"metrics": {}}}', encoding="utf-8")
            errors = service_author.validate_repository_surfaces(repo, "metrics")
            self.assertTrue(any("catalog metadata" in error for error in errors))

    def test_repository_surface_check_rejects_missing_configuration_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "infra").mkdir()
            (repo / "scripts").mkdir()
            (repo / "infra" / "services.json").write_text(
                json.dumps({"services": {"metrics": {
                    "configuration_schema": "MetricsConfiguration",
                    "release_sources": ["binary"],
                    "allowed_override_namespaces": ["ansible"],
                    "required_fields": ["resource"],
                    "runtime_owner": "guest",
                }}}),
                encoding="utf-8",
            )
            (repo / "scripts" / "canonical_values.py").write_text("metrics\n", encoding="utf-8")
            errors = service_author.validate_repository_surfaces(repo, "metrics")
            self.assertTrue(any("configuration schema" in error for error in errors))

    def test_repository_surface_check_rejects_missing_declared_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            catalog = repo / "infra" / "services.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                json.dumps({
                    "services": {
                        "metrics": {
                            "configuration_schema": "MetricsConfiguration",
                            "release_sources": ["binary"],
                            "allowed_override_namespaces": ["ansible"],
                            "required_fields": ["resource"],
                            "runtime_owner": "guest",
                            "playbooks": ["infra/ansible/playbooks/metrics.yml"],
                            "terraform_addresses": ["module.metrics["],
                        }
                    }
                }),
                encoding="utf-8",
            )
            errors = service_author.validate_repository_surfaces(repo, "metrics")
            self.assertTrue(any("declared playbook" in error for error in errors))
            self.assertTrue(any("Terraform address" in error for error in errors))

    def test_repository_surface_check_requires_manifest_secret_contract(self) -> None:
        manifest = service_author.build_manifest(
            "forgejo",
            "dedicated-lxc",
            config_model="ForgejoConfiguration",
            projection_contract="forgejo",
            provisioning_contract="forgejo-guest",
        )
        errors = service_author.validate_repository_surfaces(ROOT, "forgejo", manifest)
        self.assertTrue(any("secret contract" in error for error in errors))

    def test_repository_catalog_contracts_are_all_complete(self) -> None:
        self.assertEqual(service_author.validate_catalog_repository(ROOT), {})

    def test_catalog_report_is_deterministic_and_public_safe(self) -> None:
        report = service_author.build_catalog_report(ROOT)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["summary"], {"total": 9, "passed": 9, "failed": 0})
        service_ids = [item["service_id"] for item in report["services"]]
        self.assertEqual(service_ids, sorted(service_ids))
        self.assertNotIn("secret", json.dumps(report).lower())

    def test_catalog_report_cli_writes_only_requested_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "validate-service-contracts.py"), "--repo", str(ROOT), "--report", str(output)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["summary"]["failed"], 0)
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_rejects_guest_without_provisioning_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "provisioning contract"):
            service_author.build_manifest("metrics", "dedicated-lxc", config_model="MetricsConfig", projection_contract="metrics")

    def test_rejects_stateful_without_state_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "state contract"):
            service_author.build_manifest(
                "metrics",
                "dedicated-lxc",
                config_model="MetricsConfig",
                projection_contract="metrics",
                provisioning_contract="metrics-guest",
                stateful=True,
            )

    def test_rejects_incomplete_secret_metadata(self) -> None:
        with self.assertRaisesRegex(ValueError, "secret metadata"):
            service_author.build_manifest(
                "metrics",
                "shared-host",
                config_model="MetricsConfig",
                projection_contract="metrics",
                provisioning_contract="metrics-host",
                secret_metadata=["services.metrics.secrets.api_key"],
            )

    def test_builds_deterministic_public_manifest(self) -> None:
        manifest = service_author.build_manifest(
            "metrics",
            "dedicated-lxc",
            config_model="MetricsConfig",
            projection_contract="metrics",
            provisioning_contract="metrics-guest",
            secret_metadata=["services.metrics.secrets.api_key:credential:METRICS_API_KEY"],
        )
        self.assertEqual(manifest["service_id"], "metrics")
        self.assertEqual(manifest["archetype"], "dedicated-lxc")
        self.assertEqual(manifest["secrets"][0]["logical_path"], "services.metrics.secrets.api_key")
        encoded = json.dumps(manifest, sort_keys=True)
        self.assertNotIn("password", encoded.lower())

    def test_cli_writes_only_requested_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "manifest.json"
            result = service_author.main(
                [
                    "--service-id",
                    "metrics",
                    "--archetype",
                    "no-runtime",
                    "--config-model",
                    "MetricsConfig",
                    "--projection-contract",
                    "metrics",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(result, 0)
            self.assertTrue(output.is_file())
            self.assertEqual(list(Path(directory).iterdir()), [output])


if __name__ == "__main__":
    unittest.main()

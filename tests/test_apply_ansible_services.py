from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply-ansible-services.py"
spec = importlib.util.spec_from_file_location("apply_ansible_services", SCRIPT)
assert spec and spec.loader
apply_ansible_services = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = apply_ansible_services
spec.loader.exec_module(apply_ansible_services)


class ApplyAnsibleServicesTests(unittest.TestCase):
    def test_dependency_waves_parallelize_independent_services(self) -> None:
        waves = apply_ansible_services.dependency_waves(
            ["technitium", "forgejo", "forgejo_runner", "onramp_host", "searxng_onramp", "hermes"]
        )

        self.assertEqual(waves[0], ["technitium", "forgejo", "onramp_host", "hermes"])
        self.assertEqual(waves[1], ["forgejo_runner", "searxng_onramp"])

    def test_clean_cutover_does_not_load_root_password_from_tfvars(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("refresh_root_password_from_tfvars", source)
        self.assertNotIn("TF_VAR_lxc_root_password", source)

    def test_canonical_dns_environment_keeps_legacy_context_unchanged(self) -> None:
        class LegacyContext:
            canonical_site_path = None

        self.assertEqual(apply_ansible_services.canonical_dns_environment(LegacyContext()), {})

    def test_canonical_dns_environment_fails_closed_when_generated_projection_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            class CanonicalContext:
                canonical_site_path = apply_ansible_services.REPO / "scaffold/sites/dev/site.yaml"
                site = "dev"
                projection_manifest_path = root / "manifest.json"

                @staticmethod
                def generated_path(name: str) -> Path:
                    return root / name

            with self.assertRaisesRegex(RuntimeError, "generated projection"):
                apply_ansible_services.canonical_dns_environment(CanonicalContext())

    def test_canonical_mode_rejects_explicit_legacy_inventory(self) -> None:
        self.assertEqual(
            apply_ansible_services.main(
                ["--canonical-ansible", "--inventory", "legacy-inventory.yml", "--service", "forgejo"]
            ),
            1,
        )

    def test_run_service_keeps_service_playbooks_sequential(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            result = apply_ansible_services.run_service(
                "forgejo_runner",
                ("inventory.yml", "tfvars.py"),
                Path(temp),
                Path(temp) / ".env",
                dict(os.environ),
                runner,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            [["ansible-playbook", "-i", "inventory.yml", "-i", "tfvars.py", "infra/ansible/playbooks/forgejo-runner.yml"]],
        )

    def test_run_bootstrap_host_limits_target_and_keeps_secret_transient(self) -> None:
        commands: list[list[str]] = []
        observed_env: list[dict[str, str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            observed_env.append(dict(env))
            return 0

        base_env = {"SAFE_FLAG": "1"}
        with tempfile.TemporaryDirectory() as temp:
            result = apply_ansible_services.run_bootstrap_host(
                "forgejo",
                ("canonical-inventory.json",),
                Path(temp),
                base_env,
                {"INFRA_BOOTSTRAP_ROOT_PASSWORD": "host-secret"},
                runner,
                ("-e", "@canonical-vars.json"),
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            commands,
            [[
                "ansible-playbook",
                "-i",
                "canonical-inventory.json",
                "-e",
                "@canonical-vars.json",
                "--limit",
                "forgejo",
                "infra/ansible/playbooks/bootstrap-root-password.yml",
            ]],
        )
        self.assertEqual(observed_env[0]["INFRA_BOOTSTRAP_ROOT_PASSWORD"], "host-secret")
        self.assertNotIn("INFRA_BOOTSTRAP_ROOT_PASSWORD", base_env)

    def test_canonical_bootstrap_delivers_one_requirement_per_host(self) -> None:
        delivered_hosts: list[tuple[str, dict[str, str]]] = []
        policy = SimpleNamespace(
            default_secret="secrets.bootstrap.root_password",
            host_overrides={"forgejo": "secrets.bootstrap.hosts.forgejo.root_password"},
        )
        model = SimpleNamespace(bootstrap=SimpleNamespace(root_password=policy))

        def fake_deliver(provider: object, *, path: str, consumer: str, requirements: object) -> SimpleNamespace:
            return SimpleNamespace(
                environment_name="INFRA_BOOTSTRAP_ROOT_PASSWORD",
                value=f"secret-for-{path.rsplit('.', 2)[-2]}",
            )

        def fake_run(host: str, inventories: tuple[str, ...], log_dir: Path, base_env: dict[str, str], bootstrap_env: dict[str, str], runner: object, extra_args: tuple[str, ...]) -> int:
            delivered_hosts.append((host, bootstrap_env))
            return 0

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "secrets.sops.yaml"
            bundle.write_text("encrypted-placeholder\n", encoding="utf-8")

            class Context:
                canonical_site_path = apply_ansible_services.REPO / "scaffold/sites/dev/site.yaml"
                site = "dev"

                @staticmethod
                def path(name: str) -> Path:
                    return root / name

            with (
                mock.patch.object(apply_ansible_services, "load_site", return_value=model),
                mock.patch.object(apply_ansible_services, "canonical_bootstrap_targets", return_value=(("forgejo", "forgejo"), ("hermes", "hermes"))),
                mock.patch.object(apply_ansible_services, "SopsAgeProvider", return_value=object()),
                mock.patch.object(apply_ansible_services, "deliver", side_effect=fake_deliver),
                mock.patch.object(apply_ansible_services, "run_bootstrap_host", side_effect=fake_run),
            ):
                result = apply_ansible_services.run_canonical_bootstrap(Context(), ("inventory.json",), root, {})

        self.assertEqual(result, 0)
        self.assertEqual([host for host, _ in delivered_hosts], ["forgejo", "hermes"])
        self.assertEqual(delivered_hosts[0][1]["INFRA_BOOTSTRAP_ROOT_PASSWORD"], "secret-for-forgejo")
        self.assertEqual(delivered_hosts[1][1]["INFRA_BOOTSTRAP_ROOT_PASSWORD"], "secret-for-bootstrap")

    def test_canonical_host_identity_uses_root_only_for_lxc_and_delivers_both_passwords(self) -> None:
        commands: list[list[str]] = []
        environments: list[dict[str, str]] = []
        delivered_paths: list[str] = []
        model = SimpleNamespace(
            resources=SimpleNamespace(
                guests={"technitium": SimpleNamespace(type="lxc")},
                shared_hosts={},
            ),
            bootstrap=SimpleNamespace(
                root_password=SimpleNamespace(
                    default_secret="secrets.bootstrap.root_password",
                    host_overrides={},
                )
            ),
        )
        delivered_paths: list[str] = []

        def fake_deliver(provider: object, *, path: str, consumer: str, requirements: object) -> SimpleNamespace:
            delivered_paths.append(path)
            return SimpleNamespace(
                environment_name=(
                    "INFRA_SYSTEMBOSS_PASSWORD"
                    if path == "secrets.operator.systemboss_password"
                    else "INFRA_BOOTSTRAP_ROOT_PASSWORD"
                ),
                value=f"value-for-{path}",
            )

        def fake_run(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            environments.append(dict(env))
            return 0

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "secrets.sops.yaml").write_text("encrypted-placeholder\n", encoding="utf-8")

            class Context:
                canonical_site_path = apply_ansible_services.REPO / "scaffold/sites/dev/site.yaml"
                site = "dev"

                @staticmethod
                def path(name: str) -> Path:
                    return root / name

            with (
                mock.patch.object(apply_ansible_services, "load_site", return_value=model),
                mock.patch.object(apply_ansible_services, "canonical_bootstrap_targets", return_value=(("technitium", "technitium"),)),
                mock.patch.object(apply_ansible_services, "SopsAgeProvider", return_value=object()),
                mock.patch.object(apply_ansible_services, "deliver", side_effect=fake_deliver),
            ):
                result = apply_ansible_services.run_canonical_host_identity(Context(), ("inventory.json",), root, {}, runner=fake_run)

        self.assertEqual(result, 0)
        self.assertEqual(len(commands), 2)
        self.assertIn("ansible_user=root", commands[0])
        self.assertIn("ansible_user=infra", commands[1])
        self.assertNotIn("host_identity_root_recovery_enabled=true", commands[0])
        self.assertIn("host_identity_root_recovery_enabled=true", commands[1])
        self.assertNotIn("INFRA_BOOTSTRAP_ROOT_PASSWORD", environments[0])
        self.assertEqual(environments[1]["INFRA_SYSTEMBOSS_PASSWORD"], "value-for-secrets.operator.systemboss_password")
        self.assertEqual(environments[1]["INFRA_BOOTSTRAP_ROOT_PASSWORD"], "value-for-secrets.bootstrap.root_password")
        self.assertEqual(
            delivered_paths,
            [
                "secrets.operator.systemboss_password",
                "secrets.bootstrap.root_password",
            ],
        )

    def test_run_service_adds_paired_canonical_extra_args(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            result = apply_ansible_services.run_service(
                "forgejo_runner",
                ("canonical-inventory.json",),
                Path(temp),
                Path(temp) / ".env",
                dict(os.environ),
                runner,
                ("-e", "@canonical-vars.json"),
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(commands[0][0:6], ["ansible-playbook", "-i", "canonical-inventory.json", "-e", "@canonical-vars.json", "infra/ansible/playbooks/forgejo-runner.yml"])

    def test_technitium_dns_bootstraps_token_before_dns_sync(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                'export TECHNITIUM_API_URL="http://192.0.2.53:5380/api"\n'
                'export TECHNITIUM_API_TOKEN="REPLACE_AFTER_TOKEN_CREATION"\n'
                'export DNS_RECORDS_FILE="values/dns-records.local.json"\n',
                encoding="utf-8",
            )
            result = apply_ansible_services.run_service(
                "technitium",
                ("inventory.yml",),
                Path(temp),
                env_path,
                dict(os.environ),
                runner,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            [
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/technitium.yml"],
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/caddy-proxy.yml"],
                ["python", "scripts/bootstrap-technitium-api-token.py", "--env-file", str(env_path)],
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/technitium-dns.yml"],
            ],
        )

    def test_enabled_services_can_filter_to_one_service(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write('{"services":["technitium","forgejo"]}\n')
            path = Path(handle.name)
        try:
            self.assertEqual(apply_ansible_services.enabled_services(path, "forgejo"), ["forgejo"])
            with self.assertRaises(apply_ansible_services.settings.SettingsError):
                apply_ansible_services.enabled_services(path, "hermes")
        finally:
            path.unlink()

    def test_summary_identifies_unattempted_services(self) -> None:
        result = apply_ansible_services.ServiceResult("forgejo", (), 0, Path("/tmp/forgejo.log"))
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            apply_ansible_services.summarize_results(["forgejo", "hermes"], [result])

        self.assertIn("forgejo: configured", buffer.getvalue())
        self.assertIn("hermes: not attempted", buffer.getvalue())

    def test_sequential_stops_after_first_failure(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 2 if command[-1] == "infra/ansible/playbooks/forgejo.yml" else 0

        with tempfile.TemporaryDirectory() as temp:
            results = apply_ansible_services.run_sequential(
                ["forgejo", "hermes"],
                ("inventory.yml",),
                Path(temp),
                Path(temp) / ".env",
                dict(os.environ),
                runner,
            )

        self.assertEqual([result.service for result in results], ["forgejo"])
        self.assertEqual(results[0].returncode, 2)
        self.assertEqual(len(commands), 1)
if __name__ == "__main__":
    unittest.main()

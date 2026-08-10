from __future__ import annotations

import importlib.util
import json
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
    def test_canonical_identity_args_keep_proxmox_lifecycle_root_skip_enabled(self) -> None:
        with mock.patch.dict(os.environ, {"INFRA_HOST_IDENTITY_SKIP_ROOT": "false"}, clear=False):
            result = apply_ansible_services.canonical_identity_extra_args()

        self.assertIn("infra_host_identity_skip_root=true", result)

    def test_dependency_waves_parallelize_independent_services(self) -> None:
        waves = apply_ansible_services.dependency_waves(
            ["technitium", "forgejo", "forgejo_runner", "onramp_host", "searxng_onramp", "hermes"]
        )

        self.assertEqual(waves[0], ["technitium", "forgejo", "onramp_host", "hermes"])
        self.assertEqual(waves[1], ["forgejo_runner", "searxng_onramp"])

    def test_execution_resource_waves_serialize_shared_onramp_and_keep_independent_hosts_parallel(self) -> None:
        services = ["onramp_host", "hermes", "infisical_onramp", "searxng_onramp"]
        resources = {
            "onramp_host": "onramp_host",
            "hermes": "hermes",
            "infisical_onramp": "onramp_host",
            "searxng_onramp": "onramp_host",
        }
        self.assertEqual(
            apply_ansible_services.execution_resource_waves(services, resources),
            [["onramp_host", "hermes"], ["infisical_onramp"], ["searxng_onramp"]],
        )

    def test_canonical_execution_resource_precedes_legacy_inventory_host(self) -> None:
        model = SimpleNamespace(services={"hermes": SimpleNamespace(resource="shared-hermes-resource")})
        self.assertEqual(
            apply_ansible_services.execution_resource_keys(["hermes"], model),
            {"hermes": "shared-hermes-resource"},
        )

    def test_parallel_shared_host_failure_prevents_later_same_host_batch(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 2 if command[-1] == "infra/ansible/playbooks/infisical-onramp.yml" else 0

        with tempfile.TemporaryDirectory() as temp:
            results = apply_ansible_services.run_parallel(
                ["onramp_host", "infisical_onramp", "searxng_onramp"],
                ("inventory.yml",),
                Path(temp),
                {},
                max_workers=3,
                runner=runner,
                execution_resources={
                    "onramp_host": "onramp-host",
                    "infisical_onramp": "onramp-host",
                    "searxng_onramp": "onramp-host",
                },
            )

        self.assertEqual([result.service for result in results], ["onramp_host", "infisical_onramp"])
        self.assertEqual(results[-1].returncode, 2)
        self.assertNotIn("infra/ansible/playbooks/searxng-onramp.yml", [command[-1] for command in commands])

    def test_legacy_site_playbook_is_not_a_supported_or_validated_entrypoint(self) -> None:
        self.assertFalse((SCRIPT.parents[1] / "infra/ansible/playbooks/site.yml").exists())
        validation = (SCRIPT.parents[1] / "scripts/validate-public.sh").read_text(encoding="utf-8")
        self.assertNotIn("playbooks/site.yml", validation)

    def test_clean_cutover_does_not_load_root_password_from_tfvars(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("refresh_root_password_from_tfvars", source)
        self.assertNotIn("TF_VAR_lxc_root_password", source)

    def test_canonical_dns_environment_rejects_a_context_without_a_selected_site(self) -> None:
        class MissingCanonicalContext:
            canonical_site_path = None

        with self.assertRaisesRegex(RuntimeError, "selected canonical site"):
            apply_ansible_services.canonical_dns_environment(MissingCanonicalContext())

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

    def test_normal_entrypoint_rejects_legacy_inventory_arguments(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            apply_ansible_services.main(["--inventory", "legacy-inventory.yml", "--service", "forgejo"])
        self.assertEqual(raised.exception.code, 2)

    def test_canonical_direct_access_ready_enrolls_site_known_hosts(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        class Context:
            def path(self, relative: str) -> Path:
                return Path("/workspace/values/sites/dev") / relative

        result = apply_ansible_services.run_canonical_direct_access_ready(
            Context(),
            ("canonical-inventory.json",),
            Path("/tmp"),
            {},
            extra_args=("-e", "@canonical-vars.json"),
            runner=runner,
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            commands[0],
            [
                "ansible-playbook",
                "-i",
                "canonical-inventory.json",
                "-e",
                "@canonical-vars.json",
                "-e",
                "direct_access_ready_hosts=all:!proxmox",
                "-e",
                "direct_access_ready_known_hosts_file=/workspace/values/sites/dev/ansible/known_hosts",
                "infra/ansible/playbooks/direct-access-ready.yml",
            ],
        )

    def test_canonical_transport_binds_ssh_known_hosts_to_execution_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "generated"
            generated.mkdir()
            (generated / "ansible-vars.json").write_text('{"services": {}}\n', encoding="utf-8")

            class Context:
                canonical_site_path = root / "site.yaml"

                @staticmethod
                def generated_path(name: str) -> Path:
                    return generated / name

                @staticmethod
                def path(name: str) -> Path:
                    return root / name

            with (
                mock.patch.object(apply_ansible_services, "canonical_dns_environment", return_value={}),
                mock.patch.dict(os.environ, {"INFRA_PVE_SSH_IDENTITY_FILE": "pve-management"}, clear=False),
            ):
                transport = apply_ansible_services.canonical_ansible_transport(Context(), root)

        assert transport is not None
        self.assertIn(
            json.dumps(
                {
                    "ansible_ssh_common_args": (
                        f"-o UserKnownHostsFile={root / 'ansible/known_hosts'} -o StrictHostKeyChecking=yes"
                    )
                }
            ),
            transport.extra_args,
        )

    def test_runtime_known_hosts_path_uses_live_values_dir_during_snapshot_execution(self) -> None:
        class Context:
            @staticmethod
            def path(name: str) -> Path:
                return Path("/sealed-snapshot") / name

        with mock.patch.dict(os.environ, {"INFRA_VALUES_DIR": "/live-values/sites/dev"}, clear=False):
            result = apply_ansible_services.runtime_known_hosts_path(Context())

        self.assertEqual(result, Path("/live-values/sites/dev/ansible/known_hosts"))

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
                dict(os.environ),
                runner,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            [["ansible-playbook", "-i", "inventory.yml", "-i", "tfvars.py", "infra/ansible/playbooks/forgejo-runner.yml"]],
        )

    def test_run_service_delivers_transient_service_environment(self) -> None:
        observed_env: list[dict[str, str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            observed_env.append(dict(env))
            return 0

        with tempfile.TemporaryDirectory() as temp:
            base_env = {"SAFE_FLAG": "1"}
            result = apply_ansible_services.run_service(
                "forgejo_runner",
                ("canonical-inventory.json",),
                Path(temp),
                base_env,
                runner,
                service_environment={"FORGEJO_RUNNER_REGISTRATION_SECRET": "runtime-secret"},
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(observed_env[0]["FORGEJO_RUNNER_REGISTRATION_SECRET"], "runtime-secret")
        self.assertNotIn("FORGEJO_RUNNER_REGISTRATION_SECRET", base_env)

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
                    "INFRA_OPERATOR_PASSWORD"
                    if path == "secrets.operator.password"
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
                mock.patch.dict(os.environ, {"INFRA_HOST_IDENTITY_SKIP_ROOT": "false"}),
            ):
                result = apply_ansible_services.run_canonical_host_identity(Context(), ("inventory.json",), root, {}, runner=fake_run)

        self.assertEqual(result, 0)
        self.assertEqual(len(commands), 2)
        self.assertIn("ansible_user=root", commands[0])
        self.assertIn("ansible_user=infra", commands[1])
        self.assertNotIn("host_identity_root_recovery_enabled=true", commands[0])
        self.assertIn("host_identity_root_recovery_enabled=true", commands[1])
        self.assertNotIn("INFRA_BOOTSTRAP_ROOT_PASSWORD", environments[0])
        self.assertEqual(environments[1]["INFRA_OPERATOR_PASSWORD"], "value-for-secrets.operator.password")
        self.assertEqual(environments[1]["INFRA_BOOTSTRAP_ROOT_PASSWORD"], "value-for-secrets.bootstrap.root_password")
        self.assertEqual(
            delivered_paths,
            [
                "secrets.operator.password",
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
                dict(os.environ),
                runner,
                ("-e", "@canonical-vars.json"),
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(commands[0][0:6], ["ansible-playbook", "-i", "canonical-inventory.json", "-e", "@canonical-vars.json", "infra/ansible/playbooks/forgejo-runner.yml"])

    def test_technitium_dns_invokes_standalone_token_bootstrap_before_dns_sync(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            result = apply_ansible_services.run_service(
                "technitium",
                ("inventory.yml",),
                Path(temp),
                dict(os.environ),
                runner,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            [
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/technitium.yml"],
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/caddy-proxy.yml"],
                ["python", "scripts/bootstrap-technitium-api-token.py"],
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/technitium-dns.yml"],
            ],
        )

    def test_canonical_technitium_service_does_not_invoke_legacy_dotenv_bootstrap(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            result = apply_ansible_services.run_service(
                "technitium",
                ("canonical-inventory.json",),
                Path(temp),
                {},
                runner,
                bootstrap_technitium=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn(["python", "scripts/bootstrap-technitium-api-token.py"], commands)

    def test_canonical_enabled_services_selects_only_enabled_model_services(self) -> None:
        model = SimpleNamespace(
            services={
                "technitium": SimpleNamespace(enabled=True),
                "forgejo": SimpleNamespace(enabled=True),
                "hermes": SimpleNamespace(enabled=False),
            }
        )

        class Context:
            canonical_site_path = Path("/canonical/site.yaml")
            site = "canonical"

        with mock.patch.object(apply_ansible_services, "load_site", return_value=model):
            self.assertEqual(
                apply_ansible_services.canonical_enabled_services(Context()),
                ["technitium", "forgejo"],
            )
            self.assertEqual(
                apply_ansible_services.canonical_enabled_services(Context(), "forgejo"),
                ["forgejo"],
            )
            with self.assertRaisesRegex(RuntimeError, "not enabled"):
                apply_ansible_services.canonical_enabled_services(Context(), "hermes")

    def test_canonical_enabled_services_requires_a_selected_canonical_site(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "selected canonical site"):
            apply_ansible_services.canonical_enabled_services(SimpleNamespace(canonical_site_path=None))

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
                dict(os.environ),
                runner,
            )

        self.assertEqual([result.service for result in results], ["forgejo"])
        self.assertEqual(results[0].returncode, 2)
        self.assertEqual(len(commands), 1)
if __name__ == "__main__":
    unittest.main()

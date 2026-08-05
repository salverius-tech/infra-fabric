from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace-preflight.py"
spec = importlib.util.spec_from_file_location("workspace_preflight", SCRIPT)
assert spec and spec.loader
workspace_preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = workspace_preflight
spec.loader.exec_module(workspace_preflight)


class WorkspacePreflightTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        opentofu = root / "infra" / "opentofu"
        opentofu.mkdir(parents=True)
        (opentofu / ".terraform.lock.hcl").write_text("# lock\n", encoding="utf-8")
        values = root / "values"
        values.mkdir()
        (values / "terraform.tfstate").write_text("{}\n", encoding="utf-8")
        (values / "terraform.tfstate.backup").write_text("{}\n", encoding="utf-8")
        return temp, root

    def test_writable_workspace_passes(self) -> None:
        temp, root = self.make_repo()
        with temp:
            self.assertIsNone(workspace_preflight.run(root, require_values=True))

    def test_missing_values_fails_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra" / "opentofu").mkdir(parents=True)
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)

    def test_missing_values_passes_when_not_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra" / "opentofu").mkdir(parents=True)
            self.assertIsNone(workspace_preflight.run(root, require_values=False))

    def test_unexpected_opentofu_artifact_fails(self) -> None:
        temp, root = self.make_repo()
        with temp:
            artifact = root / "infra" / "opentofu" / "errored.tfstate"
            artifact.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)

    def test_state_lock_fails(self) -> None:
        temp, root = self.make_repo()
        with temp:
            (root / "values" / ".terraform.tfstate.lock.info").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)
    def test_canonical_site_preflight_renders_and_cleans_temporary_projections(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        (root / "infra" / "services.json").write_text(
            (source_root / "infra" / "services.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        with temp, patch.dict(
            os.environ,
            {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"},
            clear=True,
        ):
            self.assertIsNone(workspace_preflight.check_canonical_projection(root))
            self.assertFalse((site / "generated").exists())

    def test_invalid_canonical_site_fails_preflight(self) -> None:
        temp, root = self.make_repo()
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        (site / "site.yaml").write_text("schema_version: 1\n", encoding="utf-8")
        with temp, patch.dict(
            os.environ,
            {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"},
            clear=True,
        ), self.assertRaises(workspace_preflight.PreflightError):
            workspace_preflight.run(root, require_values=True)
    def test_canonical_secret_check_uses_fixed_path_without_decryption(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        (site / "secrets.sops.yaml").write_text("encrypted\n", encoding="utf-8")
        with temp, patch.dict(os.environ, {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"}, clear=True), patch.object(
            workspace_preflight,
            "check_sops_age_availability",
            return_value={"provider": "sops-age"},
        ) as check:
            workspace_preflight.check_canonical_secret_availability(root)
        check.assert_called_once_with(
            site / "secrets.sops.yaml",
            environment={"SOPS_AGE_KEY_FILE": "/run/secrets/sops-age-key"},
            expected_recipients=None,
        )

    def test_site_local_sops_policy_is_the_canonical_default(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        policy = site / ".sops.yaml"
        policy.write_text(
            "creation_rules:\n  - path_regex: '^values/sites/dev/secrets\\.sops\\.yaml$'\n    age: age1publictestrecipient\n",
            encoding="utf-8",
        )
        with temp, patch.dict(
            os.environ,
            {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"},
            clear=True,
        ):
            resolved_policy, recipients = workspace_preflight._sops_policy_inputs(root, require_policy=True)
        self.assertEqual(resolved_policy, policy)
        self.assertEqual(recipients, {"age1publictestrecipient"})

    def test_required_secret_preflight_covers_apply_phase_identity_inputs(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        scaffold = (source_root / "scaffold" / "sites" / "dev" / "site.yaml").read_text(encoding="utf-8")
        (site / "site.yaml").write_text(
            scaffold.replace(
                "bootstrap:\n  ssh:\n",
                "bootstrap:\n"
                "  root_password:\n"
                "    host_overrides:\n"
                "      forgejo: secrets.bootstrap.hosts.forgejo.root_password\n"
                "  ssh:\n",
            ),
            encoding="utf-8",
        )
        shutil.copy2(source_root / "infra" / "services.json", root / "infra" / "services.json")
        (site / "secrets.sops.yaml").write_text("encrypted-metadata-only\n", encoding="utf-8")
        policy = site / ".sops.yaml"
        policy.write_text("policy-metadata-only\n", encoding="utf-8")
        provider = MagicMock()
        with temp, patch.dict(
            os.environ,
            {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"},
            clear=True,
        ), patch.object(
            workspace_preflight,
            "_sops_policy_inputs",
            return_value=(policy, {"age1publictestrecipient"}),
        ), patch.object(workspace_preflight, "inspect_sops_policy"), patch.object(
            workspace_preflight,
            "validate_sops_age_recipients",
        ), patch.object(workspace_preflight, "SopsAgeProvider", return_value=provider):
            workspace_preflight.check_canonical_required_secrets(root, require_secrets=True)

        required = provider.validate_required.call_args.args[0]
        self.assertIn("secrets.bootstrap.ssh_private_key", required)
        self.assertIn("secrets.providers.proxmox.api_token", required)
        self.assertIn("secrets.providers.cloudflare.api_token", required)
        self.assertIn("secrets.operator.password", required)
        self.assertIn("secrets.bootstrap.root_password", required)
        self.assertIn("secrets.bootstrap.hosts.forgejo.root_password", required)
        self.assertIn("services.forgejo.secrets.secret_key", required)

    def test_canonical_secret_check_passes_private_policy_inputs_without_exposing_recipients(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        (site / "secrets.sops.yaml").write_text("encrypted\n", encoding="utf-8")
        policy = root / "private.sops.yaml"
        policy.write_text("private-policy-metadata\n", encoding="utf-8")
        with temp, patch.dict(
            os.environ,
            {
                "VALUES_DIR": str(root / "values"),
                "VALUES_SITE": "dev",
                "INFRA_SOPS_POLICY_PATH": str(policy),
                "INFRA_SOPS_AGE_RECIPIENTS": "age1example, age1other",
            },
            clear=True,
        ), patch.object(workspace_preflight, "inspect_sops_policy", return_value={"recipient_policy": "verified"}) as inspect, patch.object(
            workspace_preflight,
            "check_sops_age_availability",
            return_value={"provider": "sops-age", "recipient_policy": "verified"},
        ) as check:
            result = workspace_preflight.check_canonical_secret_availability(root)

        self.assertEqual(result["recipient_policy"], "verified")
        inspect.assert_called_once_with(policy, site="dev", expected_recipients={"age1example", "age1other"})
        check.assert_called_once_with(
            site / "secrets.sops.yaml",
            environment={"SOPS_AGE_KEY_FILE": "/run/secrets/sops-age-key"},
            expected_recipients={"age1example", "age1other"},
        )

    def test_canonical_secret_check_sanitizes_provider_failure(self) -> None:
        temp, root = self.make_repo()
        source_root = Path(__file__).resolve().parents[1]
        site = root / "values" / "sites" / "dev"
        site.mkdir(parents=True)
        shutil.copy2(source_root / "scaffold" / "sites" / "dev" / "site.yaml", site / "site.yaml")
        (site / "secrets.sops.yaml").write_text("SECRET_SENTINEL\n", encoding="utf-8")
        with temp, patch.dict(os.environ, {"VALUES_DIR": str(root / "values"), "VALUES_SITE": "dev"}, clear=True), patch.object(
            workspace_preflight,
            "check_sops_age_availability",
            side_effect=workspace_preflight.SecretProviderError("SECRET_SENTINEL"),
        ):
            with self.assertRaisesRegex(workspace_preflight.PreflightError, "canonical secret availability") as context:
                workspace_preflight.check_canonical_secret_availability(root)
        self.assertNotIn("SECRET_SENTINEL", str(context.exception))


if __name__ == "__main__":
    unittest.main()

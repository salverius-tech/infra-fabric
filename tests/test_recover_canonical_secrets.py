from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "recover_canonical_secrets",
    ROOT / "scripts" / "recover-canonical-secrets.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecoverCanonicalSecretsTests(unittest.TestCase):
    def test_parse_mapping_accepts_only_canonical_secret_namespaces(self) -> None:
        accepted = {
            "ROOT=secrets.bootstrap.root_password",
            "OPERATOR=secrets.operator.password",
            "PVE=secrets.providers.proxmox.api_token",
            "FORGEJO=services.forgejo.secrets.secret_key",
        }
        self.assertEqual(
            {MODULE.parse_mapping(raw)[1] for raw in accepted},
            {
                "secrets.bootstrap.root_password",
                "secrets.operator.password",
                "secrets.providers.proxmox.api_token",
                "services.forgejo.secrets.secret_key",
            },
        )

        for raw in (
            "OPERATOR=operator.password",
            "OPERATOR=operator.systemboss_password",
            "CF=services.providers.cloudflare.secrets.api_token",
            "OTHER=services.forgejo.configuration.password",
            "OTHER=arbitrary.secret.path",
        ):
            with self.subTest(raw=raw), self.assertRaisesRegex(MODULE.RecoveryError, "canonical secret namespace"):
                MODULE.parse_mapping(raw)

    def test_apply_uses_exact_site_filename_and_adjacent_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "values" / "sites" / "dev" / "secrets.sops.yaml"
            bundle.parent.mkdir(parents=True)
            bundle.write_text("ciphertext", encoding="utf-8")
            policy = bundle.parent / ".sops.yaml"
            policy.write_text("policy-metadata", encoding="utf-8")
            commands: list[list[str]] = []

            def fake_sops(args: list[str], **_: object) -> str:
                commands.append(args)
                if "--decrypt" in args:
                    return "{}\n"
                return "new-ciphertext"

            with patch.object(MODULE, "legacy_env_from_head", return_value={"TOKEN": "synthetic-value"}), patch.object(
                MODULE,
                "_run_sops",
                side_effect=fake_sops,
            ):
                report = MODULE.recover(
                    Path(temporary),
                    bundle,
                    [("TOKEN", "services.forgejo.secrets.internal_token")],
                    apply=True,
                    sops="sops",
                )

            self.assertEqual(report, ["imported missing canonical target: services.forgejo.secrets.internal_token"])
            self.assertNotIn("synthetic-value", repr(report))
            encrypt = commands[-1]
            self.assertEqual(encrypt[encrypt.index("--filename-override") + 1], "values/sites/dev/secrets.sops.yaml")
            self.assertEqual(encrypt[encrypt.index("--config") + 1], str(policy))
            self.assertEqual(bundle.read_text(encoding="utf-8"), "new-ciphertext")


if __name__ == "__main__":
    unittest.main()

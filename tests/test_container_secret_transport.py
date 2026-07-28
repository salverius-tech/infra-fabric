from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "container-secret-transport.sh"


class ContainerSecretTransportTests(unittest.TestCase):
    def run_helper(self, key: Path | None, *, option: Path | None = None, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        script = f'''
source {HELPER!s}
transport_parse_args "$@"
set -- "${{transport_remaining_args[@]}}"
transport_prepare
printf 'remaining=%s\\n' "$*"
printf 'mount=%s\\n' "${{transport_compose_mount_args[*]}}"
printf 'env=%s\\n' "${{transport_compose_env_args[*]}}"
'''
        env = os.environ.copy()
        if key is None:
            env.pop("SOPS_AGE_KEY_FILE", None)
        else:
            env["SOPS_AGE_KEY_FILE"] = str(key)
        args: list[str] = []
        if option is not None:
            args.extend(["--sops-age-key-file", str(option), "--"])
        args.extend(extra or ["python", "-c", "pass"])
        return subprocess.run(["bash", "-c", script, "transport-test", *args], cwd=ROOT, env=env, text=True, capture_output=True)

    def test_fixed_container_path_and_option_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_key = Path(directory) / "env-key"
            option_key = Path(directory) / "option-key"
            env_key.write_text("KEY_CONTENT_MUST_NOT_BE_READ", encoding="utf-8")
            option_key.write_text("OTHER_KEY_CONTENT_MUST_NOT_BE_READ", encoding="utf-8")
            env_key.chmod(0o600)
            option_key.chmod(0o600)
            result = self.run_helper(env_key, option=option_key, extra=["--wrapped", "value"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("remaining=--wrapped value", result.stdout)
        self.assertIn("dst=/run/secrets/sops-age-key,readonly", result.stdout)
        self.assertIn("--env SOPS_AGE_KEY_FILE=/run/secrets/sops-age-key", result.stdout)
        self.assertNotIn("OTHER_KEY_CONTENT", result.stdout + result.stderr)
        self.assertNotIn(str(option_key), result.stdout.split("env=", 1)[-1])

    def test_legacy_invocation_has_no_transport(self) -> None:
        result = self.run_helper(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mount=", result.stdout)
        self.assertIn("env=", result.stdout)
        self.assertNotIn("sops-age-key", result.stdout)

    def test_missing_and_broad_permission_files_fail_without_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            result = self.run_helper(missing)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("transport is unavailable", result.stderr)

            broad = Path(directory) / "broad"
            broad.write_text("PRIVATE_SENTINEL", encoding="utf-8")
            broad.chmod(0o644)
            result = self.run_helper(broad)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("transport is unavailable", result.stderr)
            self.assertNotIn("PRIVATE_SENTINEL", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "run-infra.sh fake PATH test requires POSIX shell path semantics")
class RunInfraTests(unittest.TestCase):
    def run_with_fake_docker(self, exit_code: int, site: str | None = None) -> tuple[subprocess.CompletedProcess[str], Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        values = root / "values"
        values.mkdir()
        selected_site = site or "dev"
        selected_values = values / "sites" / selected_site
        selected_values.mkdir(parents=True, exist_ok=True)
        (selected_values / "site.yaml").write_text("schema_version: 1\n", encoding="utf-8")
        fakebin = root / "bin"
        fakebin.mkdir()
        record = root / "record"
        fake_docker = fakebin / "docker"
        fake_docker.write_text(
            textwrap.dedent(
                f"""
                #!/usr/bin/env bash
                set -euo pipefail
                echo "$*" > "{record}"
                exit {exit_code}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fakebin}{os.pathsep}{env['PATH']}",
                "HOME": str(root / "home"),
                "VALUES_DIR": str(values),
                "TMPDIR": str(root),
            }
        )
        (root / "home").mkdir()
        age_key = root / "site.age"
        age_key.write_text("synthetic-test-age-identity\n", encoding="utf-8")
        age_key.chmod(0o600)
        env["SOPS_AGE_KEY_FILE"] = str(age_key)
        env["VALUES_SITE"] = selected_site
        result = subprocess.run(
            ["bash", "scripts/run-infra.sh", "true"],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, root

    def test_runtime_workspace_is_removed_on_success(self) -> None:
        result, root = self.run_with_fake_docker(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(list(root.glob("run-infra.*")))

    def test_site_values_directory_is_selected(self) -> None:
        result, root = self.run_with_fake_docker(0, site="dev")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(list(root.glob("run-infra.*")))

    def test_runtime_workspace_is_removed_on_failure(self) -> None:
        result, root = self.run_with_fake_docker(7)
        self.assertEqual(result.returncode, 7)
        self.assertFalse(list(root.glob("run-infra.*")))

    def test_generated_root_override_uses_a_private_fixed_site_mount(self) -> None:
        source = (REPO / "scripts/run-infra.sh").read_text(encoding="utf-8")
        self.assertIn("INFRA_GENERATED_ROOT must be an absolute private host path", source)
        self.assertIn("prepare_private_directory", source)
        self.assertIn("open_private_directory", source)
        self.assertIn("ensure_private_directory", source)
        self.assertIn("st_uid != os.getuid()", source)
        self.assertIn('${generated_host_root}:/run/infra-fabric/generated', source)
        self.assertIn('INFRA_GENERATED_DIR=/run/infra-fabric/generated/generated', source)
        self.assertNotIn("INFRA_ACCEPT_CHANGED_HOST_KEYS", source)

    def test_default_private_artifact_roots_make_plain_lifecycle_commands_nfs_safe(self) -> None:
        result, root = self.run_with_fake_docker(0, site="dev")
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = (root / "record").read_text(encoding="utf-8")
        state_root = root / "home/.local/state/infra-fabric/sites/dev"
        self.assertIn(f"{state_root}/generated:/run/infra-fabric/generated", invocation)
        self.assertIn(f"{state_root}/execution-snapshots:/run/infra-fabric/execution-snapshots", invocation)
        self.assertIn(f"{state_root}/state-backups:/run/infra-fabric/state-backups", invocation)
        for name in ("generated", "execution-snapshots", "state-backups"):
            self.assertEqual(stat.S_IMODE((state_root / name).stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()

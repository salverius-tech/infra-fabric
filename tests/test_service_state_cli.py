from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCRIPT = ROOT / "scripts" / "service-state.sh"
SITE_CONTEXT_SCRIPT = ROOT / "scripts" / "site-context.sh"


class ServiceStateCliTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> Path:
        scripts = root / "scripts"
        scripts.mkdir()
        script = scripts / "service-state.sh"
        shutil.copy2(SOURCE_SCRIPT, script)
        shutil.copy2(SITE_CONTEXT_SCRIPT, scripts / "site-context.sh")
        (scripts / "python.sh").write_text("#!/usr/bin/env bash\nif [[ \"$1\" == \"-\" ]]; then echo hermes; else echo hermes; fi\n", encoding="utf-8")
        (scripts / "settings.py").write_text("#!/usr/bin/env bash\necho hermes\n", encoding="utf-8")
        (scripts / "run-infra.sh").write_text(
            "#!/usr/bin/env bash\n"
            "printf 'MSYS2_ENV_CONV_EXCL=%s\\n' \"${MSYS2_ENV_CONV_EXCL:-}\" >> \"${CAPTURE_FILE}\"\n"
            "printf '%s\\n' \"$*\" >> \"${CAPTURE_FILE}\"\n",
            encoding="utf-8",
        )
        for path in scripts.iterdir():
            path.chmod(0o755)
        return script

    def test_restore_excludes_container_paths_from_msys_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.make_fixture(root)
            site_values = root / "values" / "sites" / "dev"
            site_values.mkdir(parents=True)
            (site_values / "site.json").write_text(
                '{"name":"dev","class":"development","lifecycle":"disposable",'
                '"allow_apply":true,"allow_destroy":true,"services":["hermes"]}\n',
                encoding="utf-8",
            )
            (site_values / "site.yaml").write_text("schema_version: 1\nsite:\n  name: dev\n", encoding="utf-8")
            archive = site_values / "service-backups" / "hermes" / "state.tar.gz"
            archive.parent.mkdir(parents=True)
            archive.touch()
            capture = root / "run-infra.txt"
            environment = os.environ | {
                "CAPTURE_FILE": str(capture),
                "MSYS2_ENV_CONV_EXCL": "KEEP",
                "VALUES_SITE": "dev",
            }

            result = subprocess.run(
                [str(script), "restore", "hermes", str(archive)],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            captured = capture.read_text(encoding="utf-8")
            self.assertIn(
                "MSYS2_ENV_CONV_EXCL=KEEP;SERVICE_STATE_BACKUP_ROOT;SERVICE_STATE_RESTORE_FILE",
                captured,
            )
            self.assertIn('generated_dir="${INFRA_GENERATED_DIR:-/workspace/values/sites/dev/generated}"', captured)
            self.assertIn('inventory="${generated_dir}/ansible-inventory.json"', captured)
            self.assertIn('vars_file="${generated_dir}/ansible-vars.json"', captured)
            self.assertIn('--generated-dir "${generated_dir}"', captured)

    def test_latest_local_archive_skips_pre_restore_safety_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.make_fixture(root)
            site_values = root / "values" / "sites" / "dev"
            backup_dir = site_values / "service-backups" / "hermes"
            backup_dir.mkdir(parents=True)
            (backup_dir / "hermes-state-20260101T000000Z.tar.gz").write_text("old")
            (backup_dir / "hermes-state-pre-restore-20260201T000000Z.tar.gz").write_text("safety")
            probe = root / "probe.sh"
            probe.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"repo_root={root}\n"
                'site_values_dir="values/sites/dev"\n'
                f"source <(sed -n '/^latest_local_archive()/,/^}}/p' {script})\n"
                "latest_local_archive hermes\n",
                encoding="utf-8",
            )
            probe.chmod(0o755)
            result = subprocess.run(
                [str(probe)],
                cwd=root,
                env=os.environ | {"VALUES_SITE": "dev"},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(backup_dir / "hermes-state-20260101T000000Z.tar.gz"))

if __name__ == "__main__":
    unittest.main()

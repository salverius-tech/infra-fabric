from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OperationalCutoverTests(unittest.TestCase):
    def test_operational_scripts_are_valid_bash(self) -> None:
        for name in ("validate-values.sh", "plan-infra.sh", "apply-infra.sh"):
            result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=f"{name}: {result.stderr}")

    def test_forensic_importer_does_not_depend_on_canonical_preflight(self) -> None:
        # Recovery-boundary sentinel: a legacy-only source cannot satisfy canonical
        # site preflight, and no normal lifecycle recipe may depend on this importer.
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        importer = justfile[justfile.index("recover-legacy-values-forensics:"):]
        importer = importer[: importer.index("\n# ")]
        self.assertNotIn("check-values", importer)
        self.assertIn("scripts/legacy-values-discovery.py", importer)
        self.assertNotIn("scripts/migrate-values.py", importer)
        self.assertIn("normalized workspace-relative path", importer)
        self.assertIn("/workspace/${values_dir}", importer)
        self.assertIn('!= *"/./"*', importer)
        self.assertIn('!= *"/../"*', importer)
        for write_capable_flag in ("--output", "--candidate-base", "--candidate-output"):
            self.assertNotIn(write_capable_flag, importer)
        for recipe in ("setup remote=", "validate:", "plan:", "apply:", "teardown-plan:", "teardown-apply"):
            start = justfile.index(recipe)
            end = justfile.find("\n# ", start)
            block = justfile[start:] if end < 0 else justfile[start:end]
            self.assertNotIn("recover-legacy-values-forensics", block)

    def test_forensic_discovery_is_byte_for_byte_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            values = Path(temporary) / "values"
            inventory = values / "ansible" / "inventory"
            inventory.mkdir(parents=True)
            (values / ".env").write_text(
                "TECHNITIUM_API_TOKEN=SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text(
                'forgejo_server_name = "git.example.internal"\n',
                encoding="utf-8",
            )
            (inventory / "local.yml").write_text(
                "all:\n  hosts:\n    edge:\n", encoding="utf-8"
            )

            def snapshot_tree() -> dict[str, tuple[int, int, int, bytes | str | None]]:
                snapshot: dict[str, tuple[int, int, int, bytes | str | None]] = {}
                for path in (values, *sorted(values.rglob("*"))):
                    metadata = path.lstat()
                    relative = "." if path == values else path.relative_to(values).as_posix()
                    payload: bytes | str | None = None
                    if path.is_symlink():
                        payload = os.readlink(path)
                    elif path.is_file():
                        payload = path.read_bytes()
                    snapshot[relative] = (
                        metadata.st_mode,
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        payload,
                    )
                return snapshot

            before = snapshot_tree()
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "legacy-values-discovery.py"),
                    "--values-dir",
                    str(values),
                    "--repo",
                    str(ROOT),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["files"], sorted(payload["files"]))
            self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", result.stdout)
            self.assertEqual(snapshot_tree(), before)


if __name__ == "__main__":
    unittest.main()

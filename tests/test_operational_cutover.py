from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def snapshot_tree(root: Path) -> dict[str, tuple[int, int, int, bytes | str | None]]:
    """Capture every directory, regular file, and symlink without following links."""
    snapshot: dict[str, tuple[int, int, int, bytes | str | None]] = {}

    def visit(path: Path, relative: str) -> None:
        metadata = path.lstat()
        payload: bytes | str | None = None
        if stat.S_ISLNK(metadata.st_mode):
            payload = os.readlink(path)
        elif stat.S_ISREG(metadata.st_mode):
            payload = path.read_bytes()
        snapshot[relative] = (
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            payload,
        )
        if stat.S_ISDIR(metadata.st_mode):
            for entry in sorted(os.scandir(path), key=lambda item: item.name):
                child = Path(entry.path)
                child_relative = entry.name if relative == "." else f"{relative}/{entry.name}"
                visit(child, child_relative)

    visit(root, ".")
    return snapshot


class OperationalCutoverTests(unittest.TestCase):
    def test_operational_scripts_are_valid_bash(self) -> None:
        for name in (
            "validate-values.sh",
            "plan-infra.sh",
            "apply-infra.sh",
            "rehearse-development-rollback.sh",
        ):
            result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=f"{name}: {result.stderr}")

    def test_canonical_lifecycle_wrappers_are_executable(self) -> None:
        for name in ("plan-infra.sh", "apply-infra.sh", "teardown-infra.sh"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / "scripts" / name).stat().st_mode & 0o111)

    def test_development_rollback_rehearsal_is_explicit_and_dev_only(self) -> None:
        script = (ROOT / "scripts" / "rehearse-development-rollback.sh").read_text(
            encoding="utf-8"
        )
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        self.assertIn("--approve-development-rollback", script)
        self.assertIn('"${VALUES_SITE}" != "dev"', script)
        self.assertIn("StrictHostKeyChecking=yes", script)
        self.assertIn("hermes_rollback_rehearsal_approved", script)
        self.assertIn("rehearse-development-rollback approval=\"\":", justfile)

    def test_no_legacy_recovery_entrypoint_remains(self) -> None:
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        self.assertNotIn("recover-legacy-values-forensics", justfile)
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertNotIn("legacy-values-forensics", compose)
        for path in (
            "ansible_semantic_discovery.py", "discover-values-remote.sh",
            "legacy-values-discovery.py", "legacy-values-forensics.sh",
            "legacy_values_discovery.py", "migrate-secret-bundle.py",
            "migrate-site-values.py", "migrate-values.py", "migration_backup.py",
            "bootstrap-domain.py", "parse-env.py", "bootstrap-pve-token.sh",
        ):
            self.assertFalse((ROOT / "scripts" / path).exists(), path)
        self.assertFalse((ROOT / "infra/ansible/inventory/tfvars.py").exists())
        self.assertFalse((ROOT / "tests/test_tfvars_inventory.py").exists())
        self.assertFalse((ROOT / "tests/test_bootstrap_domain.py").exists())
        self.assertFalse((ROOT / "tests/test_parse_env.py").exists())
        self.assertFalse((ROOT / "scaffold/.env.example").exists())

    def test_lifecycle_projection_helpers_have_no_legacy_input_mode(self) -> None:
        for relative in (
            "scripts/storage-vars.py",
            "scripts/service-runtime.py",
            "scripts/guest-mount-feature-vars.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("--tfvars", source, relative)
            self.assertNotIn("--settings", source, relative)
            self.assertNotIn("load_tfvars", source, relative)
            self.assertNotIn("import hcl2", source, relative)

if __name__ == "__main__":
    unittest.main()

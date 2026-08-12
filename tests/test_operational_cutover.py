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
        ):
            result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=f"{name}: {result.stderr}")

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
        ):
            self.assertFalse((ROOT / "scripts" / path).exists(), path)

if __name__ == "__main__":
    unittest.main()

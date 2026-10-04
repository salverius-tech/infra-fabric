from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HostSshDirectoryTests(unittest.TestCase):
    def run_helper(self, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-euo",
                "pipefail",
                "-c",
                "source scripts/host-ssh-directory.sh; require_host_ssh_directory; printf '%s' \"$HOST_SSH_DIR\"",
            ],
            cwd=ROOT,
            env={**os.environ, **environment},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_requires_home_or_explicit_ssh_directory(self) -> None:
        result = self.run_helper({"HOME": "", "HOST_SSH_DIR": ""})

        self.assertEqual(result.returncode, 2)
        self.assertIn("HOME or HOST_SSH_DIR is required", result.stderr)

    def test_exports_readable_explicit_ssh_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_helper({"HOME": "", "HOST_SSH_DIR": temporary})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, temporary)

    def test_rejects_missing_ssh_directory(self) -> None:
        result = self.run_helper(
            {"HOME": "/nonexistent/infra-fabric-test", "HOST_SSH_DIR": ""}
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("SSH mount directory is missing or unreadable", result.stderr)


if __name__ == "__main__":
    unittest.main()

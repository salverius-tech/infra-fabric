from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IgnoreContractTests(unittest.TestCase):
    def test_git_and_docker_ignore_local_scratch_and_tool_caches(self) -> None:
        expected = {
            ".tmp/",
            ".cache/",
            ".coverage",
            ".mypy_cache/",
            ".pytest_cache/",
            ".ruff_cache/",
        }
        for filename in (".gitignore", ".dockerignore"):
            with self.subTest(filename=filename):
                entries = {
                    line.strip()
                    for line in (ROOT / filename).read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")
                }
                self.assertTrue(expected <= entries)

    def test_moved_dns_fixture_remains_publicly_tracked(self) -> None:
        self.assertTrue((ROOT / "tests/fixtures/dns-records.local.json").is_file())
        for filename in (".gitignore", ".dockerignore"):
            with self.subTest(filename=filename):
                self.assertIn(
                    "!tests/fixtures/dns-records.local.json",
                    (ROOT / filename).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()

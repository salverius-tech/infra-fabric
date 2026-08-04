from __future__ import annotations

import os

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValuesScriptTests(unittest.TestCase):
    def test_site_init_renders_generic_template_for_new_site(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            template = workspace / "scaffold"
            fake_bin = workspace / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text("#!/bin/sh\nif [ \"$1\" = \"-C\" ] && [ \"$3\" = \"init\" ]; then mkdir -p \"$2/.git\"; fi\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            (template / "sites" / "_template").mkdir(parents=True)
            (template / "sites" / "_template" / "site.yaml").write_text("site:\n  name: example\n", encoding="utf-8")
            for source in ("README.md", ".env.example"):
                (template / source).write_text("placeholder\n", encoding="utf-8")
            environment = os.environ.copy()
            environment.update({"VALUES_DIR": str(workspace / "values"), "VALUES_SITE": "qa", "VALUES_TEMPLATE_DIR": str(template), "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}"})
            result = subprocess.run([str(ROOT / "scripts" / "values.sh"), "init"], cwd=ROOT, env=environment, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("name: qa", (workspace / "values" / "sites" / "qa" / "site.yaml").read_text(encoding="utf-8"))

    def test_site_init_seeds_canonical_yaml_without_overwriting_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            values = workspace / "values"
            fake_bin = workspace / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text("#!/bin/sh\nif [ \"$1\" = \"-C\" ] && [ \"$3\" = \"init\" ]; then mkdir -p \"$2/.git\"; fi\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "VALUES_DIR": str(values),
                    "VALUES_SITE": "dev",
                    "VALUES_TEMPLATE_DIR": str(ROOT / "scaffold"),
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                }
            )
            result = subprocess.run(
                [str(ROOT / "scripts" / "values.sh"), "init"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            site = values / "sites" / "dev"
            self.assertTrue((site / "site.yaml").is_file())
            self.assertFalse((site / "site.json").exists())
            self.assertFalse((site / "terraform.tfvars").exists())
            self.assertFalse((site / "dns-records.local.json").exists())
            self.assertFalse((site / "ansible" / "inventory" / "local.yml").exists())
            original = (site / "site.yaml").read_bytes()
            (site / "site.yaml").write_bytes(b"operator-edited\n")

            result = subprocess.run(
                [str(ROOT / "scripts" / "values.sh"), "init"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((site / "site.yaml").read_bytes(), b"operator-edited\n")
            self.assertNotEqual(original, b"operator-edited\n")

    def test_site_init_fails_when_canonical_scaffold_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            template = workspace / "scaffold"
            fake_bin = workspace / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text("#!/bin/sh\nif [ \"$1\" = \"-C\" ] && [ \"$3\" = \"init\" ]; then mkdir -p \"$2/.git\"; fi\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            (template / "sites" / "dev").mkdir(parents=True)
            for source in ("README.md", ".env.example", "terraform.tfvars", "dns-records.local.json"):
                destination = template / source
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("placeholder\n", encoding="utf-8")
            inventory = template / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("all: {}\n", encoding="utf-8")
            (template / "sites" / "dev" / "site.json").write_text("{}\n", encoding="utf-8")
            environment = os.environ.copy()
            environment.update(
                {
                    "VALUES_DIR": str(workspace / "values"),
                    "VALUES_SITE": "dev",
                    "VALUES_TEMPLATE_DIR": str(template),
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                }
            )
            result = subprocess.run(
                [str(ROOT / "scripts" / "values.sh"), "init"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing canonical site scaffold", result.stderr)


if __name__ == "__main__":
    unittest.main()
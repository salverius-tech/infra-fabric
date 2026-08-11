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
            "legacy-values-forensics.sh",
        ):
            result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=f"{name}: {result.stderr}")

    def test_forensic_recipe_is_an_exact_non_forwarding_command(self) -> None:
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        importer = justfile[justfile.index("recover-legacy-values-forensics:"):]
        importer = importer[: importer.index("\n# ")]
        self.assertEqual(
            importer,
            "recover-legacy-values-forensics:\n    @scripts/legacy-values-forensics.sh\n",
        )
        for forbidden in (
            "check-values",
            "scripts/python.sh",
            "scripts/migrate-values.py",
            "{{args}}",
            "*args",
            "--output",
            "--candidate-base",
            "--candidate-output",
            "--resolve-tagged-images",
        ):
            self.assertNotIn(forbidden, importer)

        wrapper = (ROOT / "scripts" / "legacy-values-forensics.sh").read_text(encoding="utf-8")
        self.assertIn("does not accept or forward arguments", wrapper)
        self.assertIn("--no-deps", wrapper)
        self.assertIn("legacy-values-forensics", wrapper)
        self.assertIn("python -B scripts/legacy-values-discovery.py", wrapper)
        self.assertIn('--values-dir "/workspace/${values_dir}"', wrapper)
        self.assertIn("--repo /workspace", wrapper)
        for forbidden in (
            "scripts/python.sh",
            "transport_prepare",
            '"$@"',
            "--output",
            "--candidate-base",
            "--candidate-output",
            "--resolve-tagged-images",
        ):
            self.assertNotIn(forbidden, wrapper)

        rejected = subprocess.run(
            [str(ROOT / "scripts" / "legacy-values-forensics.sh"), "--output", "/tmp/report"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("does not accept or forward arguments", rejected.stderr)

        for recipe in ("setup remote=", "validate:", "plan:", "apply:", "teardown-plan:", "teardown-apply"):
            start = justfile.index(recipe)
            end = justfile.find("\n# ", start)
            block = justfile[start:] if end < 0 else justfile[start:end]
            self.assertNotIn("recover-legacy-values-forensics", block)

    def test_forensic_compose_service_seals_source_and_network(self) -> None:
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        service = compose[compose.index("  legacy-values-forensics:"):]
        service = service[: service.index("\nvolumes:")]
        for contract in (
            "    pull_policy: never",
            "    entrypoint: []",
            "    read_only: true",
            "    network_mode: none",
            "      - .:/workspace:ro",
            "      - /tmp:mode=1777",
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      PYTHONPYCACHEPREFIX: /tmp/legacy-values-forensics-pycache",
        ):
            self.assertIn(contract, service)
        self.assertNotIn("/ssh-ro", service)
        self.assertNotIn("plugin-cache", service)
        self.assertNotIn("ansible-cache", service)

    def test_default_discovery_does_not_resolve_tagged_images(self) -> None:
        import importlib.util

        module_path = ROOT / "scripts" / "legacy_values_discovery.py"
        spec = importlib.util.spec_from_file_location("operational_legacy_values_discovery", module_path)
        assert spec and spec.loader
        legacy_values_discovery = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = legacy_values_discovery
        spec.loader.exec_module(legacy_values_discovery)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                values = Path(temporary) / "values"
                values.mkdir()
                (values / "terraform.tfvars").write_text(
                    'searxng_container_image = "searxng/searxng:latest"\n',
                    encoding="utf-8",
                )
                with mock.patch.object(
                    legacy_values_discovery,
                    "_resolve_container_image_digest",
                    side_effect=AssertionError("registry lookup must not occur"),
                ) as resolver:
                    report = legacy_values_discovery.discover_legacy(values)
                resolver.assert_not_called()
                observation = next(item for item in report.observations if item.key == "searxng_container_image")
                self.assertEqual(observation.value["resolution"], "not-requested")
                self.assertEqual(observation.value["tag"], "latest")
                self.assertIsNone(observation.value["digest"])

                digest = "sha256:" + "a" * 64
                with mock.patch.object(
                    legacy_values_discovery,
                    "_resolve_container_image_digest",
                    return_value=digest,
                ) as resolver:
                    opted_in = legacy_values_discovery.discover_legacy(values, resolve_tagged_images=True)
                resolver.assert_called_once_with("searxng/searxng:latest")
                opted_in_observation = next(
                    item for item in opted_in.observations if item.key == "searxng_container_image"
                )
                self.assertEqual(opted_in_observation.value["digest"], digest)
        finally:
            sys.modules.pop(spec.name, None)

    def test_whole_forensic_recipe_preserves_fresh_source_and_legacy_tree(self) -> None:
        just_binary = shutil.which("just")
        if just_binary is None:
            self.skipTest("whole-recipe behavioral test requires the host just binary")
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            copied_root = temp / "fresh-source"
            shutil.copytree(
                ROOT,
                copied_root,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache"),
            )
            values = copied_root / "values"
            values.mkdir()
            (values / ".env").write_text(
                "TECHNITIUM_API_TOKEN=SECRET_SENTINEL_DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text(
                'forgejo_server_name = "git.example.internal"\n'
                'searxng_container_image = "searxng/searxng:latest"\n',
                encoding="utf-8",
            )
            empty = values / "empty-directory"
            empty.mkdir()
            binary = values / "binary-fixture"
            binary.write_bytes(b"\x00legacy\xff")
            binary.chmod(0o640)
            link = values / "fixture-link"
            link.symlink_to("binary-fixture")
            fixed_ns = 1_700_000_000_123_456_789
            os.utime(binary, ns=(fixed_ns, fixed_ns))
            os.utime(empty, ns=(fixed_ns, fixed_ns))
            os.utime(link, ns=(fixed_ns, fixed_ns), follow_symlinks=False)

            fake_bin = temp / "bin"
            fake_bin.mkdir()
            docker_record = temp / "docker-command.json"
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, sys\n"
                "args = sys.argv[1:]\n"
                "pathlib.Path(os.environ['FAKE_DOCKER_RECORD']).write_text(json.dumps(args))\n"
                "service = args.index('legacy-values-forensics')\n"
                "command = args[service + 1:]\n"
                "workspace = os.environ['FAKE_WORKSPACE']\n"
                "command = [workspace + item.removeprefix('/workspace') if item.startswith('/workspace/') else item for item in command]\n"
                "if command[0] == 'python': command[0] = sys.executable\n"
                "os.chdir(workspace)\n"
                "os.execvpe(command[0], command, os.environ)\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            blocker = temp / "network-blocker"
            blocker.mkdir()
            (blocker / "sitecustomize.py").write_text(
                "import socket\n"
                "def denied(*args, **kwargs): raise AssertionError('network access attempted')\n"
                "socket.create_connection = denied\n"
                "socket.socket.connect = denied\n",
                encoding="utf-8",
            )

            source_before = snapshot_tree(copied_root)
            values_before = snapshot_tree(values)
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "FAKE_DOCKER_RECORD": str(docker_record),
                    "FAKE_WORKSPACE": str(copied_root),
                    "PYTHONPATH": str(blocker),
                    "VALUES_DIR": "values",
                }
            )
            result = subprocess.run(
                [just_binary, "recover-legacy-values-forensics"],
                cwd=copied_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["files"], sorted(payload["files"]))
            self.assertNotIn("SECRET_SENTINEL_DO_NOT_PRINT", result.stdout)
            image = next(item for item in payload["observations"] if item["key"] == "searxng_container_image")
            self.assertEqual(image["value"]["resolution"], "not-requested")
            self.assertEqual(
                json.loads(docker_record.read_text(encoding="utf-8")),
                [
                    "compose",
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "legacy-values-forensics",
                    "python",
                    "-B",
                    "scripts/legacy-values-discovery.py",
                    "--values-dir",
                    "/workspace/values",
                    "--repo",
                    "/workspace",
                ],
            )
            self.assertEqual(snapshot_tree(values), values_before)
            self.assertEqual(snapshot_tree(copied_root), source_before)
            self.assertFalse(any(path.name == "__pycache__" for path in copied_root.rglob("__pycache__")))
            self.assertFalse(any(path.suffix == ".pyc" for path in copied_root.rglob("*.pyc")))


if __name__ == "__main__":
    unittest.main()

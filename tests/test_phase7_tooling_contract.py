"""Source contracts for reproducible public validation tooling."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "tools" / "Dockerfile"
ENTRYPOINT = ROOT / "tools" / "docker-entrypoint.sh"
LOCK = ROOT / "tools" / "requirements.lock"
PIP_BOOTSTRAP_LOCK = ROOT / "tools" / "pip-bootstrap.lock"
VALIDATE = ROOT / "scripts" / "validate-public.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"
POLICY = ROOT / "docs" / "tooling-reproducibility.md"


class Phase7ToolingContractTests(unittest.TestCase):
    def test_tooling_image_uses_hash_locked_dependencies_and_amd64_policy(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        lock = LOCK.read_text(encoding="utf-8")
        bootstrap_lock = PIP_BOOTSTRAP_LOCK.read_text(encoding="utf-8")

        self.assertIn(
            "COPY tools/pip-bootstrap.lock tools/requirements.lock /tmp/", text
        )
        self.assertIn(
            "pip install --no-cache-dir --require-hashes --upgrade -r /tmp/pip-bootstrap.lock",
            text,
        )
        self.assertIn(
            "pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock",
            text,
        )
        self.assertIn("ARG TARGETARCH", text)
        self.assertIn('"${TARGETARCH}" = "amd64"', text)
        self.assertRegex(
            lock, r"(?m)^[A-Za-z0-9_.-]+==[^\s]+ \\\n    --hash=sha256:[0-9a-f]{64}$"
        )
        self.assertRegex(
            bootstrap_lock, r"(?m)^pip==[^\s]+ \\\n    --hash=sha256:[0-9a-f]{64}$"
        )
        self.assertNotIn("-r tools/requirements.txt", text)

    def test_apt_and_advisory_policy_are_documented(self) -> None:
        policy = POLICY.read_text(encoding="utf-8")
        inventory = yaml.safe_load(
            (ROOT / "docs" / "documentation-inventory.json").read_text(encoding="utf-8")
        )
        self.assertIn("APT reproducibility policy", policy)
        self.assertEqual(
            inventory["documents"]["docs/tooling-reproducibility.md"],
            "current authority",
        )
        self.assertIn("HIGH and CRITICAL", policy)
        self.assertIn("exception", policy.lower())
        self.assertIn("read-only", policy.lower())

    def test_entrypoint_repairs_only_public_paths_and_keeps_caches_off_source(
        self,
    ) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertNotIn("/workspace/values", text)
        self.assertNotIn("find /workspace -type", text)
        self.assertIn("/workspace/infra/opentofu", text)
        self.assertIn("COVERAGE_FILE", text)
        self.assertIn("PYTHONPYCACHEPREFIX", text)
        self.assertIn("XDG_CACHE_HOME", text)

    def test_validation_has_named_stages_quality_and_summary(self) -> None:
        text = VALIDATE.read_text(encoding="utf-8")
        for stage in (
            "preflight",
            "opentofu",
            "shell",
            "python-quality",
            "contracts",
            "ansible",
            "summary",
        ):
            self.assertIn(f'run_stage "{stage}"', text)
        self.assertIn("black --check", text)
        self.assertIn("tools/python-format-files.txt", text)
        self.assertIn("ruff check --select=E9,F63,F7,F82", text)
        self.assertIn("${python_files[@]}", text)
        self.assertIn("mypy", text)
        self.assertIn("coverage run", text)
        self.assertIn("coverage report --fail-under=", text)
        self.assertIn('stages+=("FAIL ${current_stage}")', text)

    def test_workflow_scans_dependencies_and_image_on_manual_schedule_only(
        self,
    ) -> None:
        workflow = yaml.load(
            WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )
        job = workflow["jobs"]["supply-chain-evidence"]
        rendered = "\n".join(str(step) for step in job["steps"])

        self.assertIn("dependencies", rendered.lower())
        self.assertIn("fs", rendered)
        self.assertIn("HIGH,CRITICAL", rendered)
        self.assertIn("workflow_dispatch", job["if"])
        self.assertIn("schedule", job["if"])


if __name__ == "__main__":
    unittest.main()

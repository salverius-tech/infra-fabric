from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PlanProjectionLifecycleTests(unittest.TestCase):
    def test_setup_requires_an_explicit_remote_and_does_not_discover_legacy_settings(self) -> None:
        # Safety category: pre-mutation ordering. Setup can initialize or clone a
        # private values repository, so retain this narrow public entrypoint guard.
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        setup_recipe = justfile.split("# Initialize the selected canonical site's bootstrap SSH identity", 1)[0]
        self.assertNotIn("discover-values-remote.sh", setup_recipe)
        self.assertIn('selected_remote="{{remote}}"', setup_recipe)

    def test_shared_projection_set_helper_fails_closed_and_accepts_complete_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary) / "generated"
            generated.mkdir()
            command = f"source scripts/site-context.sh; require_canonical_projection_set {generated}"
            missing = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", command],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(missing.returncode, 2)
            self.assertIn("Canonical projections are missing", missing.stderr)

            for name in (
                "manifest.json",
                "terraform.auto.tfvars.json",
                "ansible-inventory.json",
                "ansible-vars.json",
                "dns-records.json",
                "onramp-handoff.json",
            ):
                (generated / name).write_text("{}\n", encoding="utf-8")
            complete = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", command],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(complete.returncode, 0, complete.stderr)

    def test_normal_operator_workflows_fail_closed_before_container_execution(self) -> None:
        workflows = (
            ("validate-values.sh", ()),
            ("plan-infra.sh", ()),
            ("apply-infra.sh", ()),
            ("teardown-infra.sh", ("plan",)),
        )
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            fake_bin = temporary_root / "bin"
            fake_bin.mkdir()
            docker_called = temporary_root / "docker-called"
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                "#!/usr/bin/env bash\ntouch \"${DOCKER_CALLED}\"\nexit 99\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)

            for values_site, expected_message in (
                (None, "VALUES_SITE is required for normal operator workflows"),
                ("missing", "Selected canonical site is missing"),
            ):
                for name, arguments in workflows:
                    docker_called.unlink(missing_ok=True)
                    environment = {
                        **os.environ,
                        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                        "VALUES_DIR": str(temporary_root / "values"),
                        "DOCKER_CALLED": str(docker_called),
                    }
                    if values_site is not None:
                        environment["VALUES_SITE"] = values_site
                    else:
                        environment.pop("VALUES_SITE", None)
                    result = subprocess.run(
                        ["bash", str(ROOT / "scripts" / name), *arguments],
                        cwd=ROOT,
                        env=environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2, f"{name}: {result.stderr}")
                    self.assertIn(expected_message, result.stderr, name)
                    self.assertFalse(docker_called.exists(), name)

    def test_plan_script_is_shell_valid(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "plan-infra.sh")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_preserves_existing_artifacts_until_verified_replacement(self) -> None:
        # Safety category: pre-mutation ordering. Exercising this path requires a
        # provider/private-values plan boundary, so keep this narrow source sentinel.
        content = (ROOT / "scripts" / "plan-infra.sh").read_text(encoding="utf-8")
        ordered_steps = (
            "python scripts/workspace-preflight.py --require-values --require-secrets",
            'generated_verified=false',
            'generated_tmp="$(mktemp -d',
            'python scripts/verify-projections.py',
            'generated_verified=true',
            'tofu -chdir=infra/opentofu init',
            'plan_tmp="$(mktemp',
            'mv -f "${plan_tmp}" "${INFRA_VALUES_DIR}/tfplan"',
        )
        positions = [content.index(step) for step in ordered_steps]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('rm -f "${INFRA_VALUES_DIR}/tfplan" "${INFRA_VALUES_DIR}/tfplan.meta.json"', content)

    def test_teardown_uses_a_distinct_metadata_bound_destroy_contract(self) -> None:
        # Safety category: approval sentinel. Running teardown would require a live
        # provider mutation, so retain the explicit source-level guard.
        source = (ROOT / "scripts" / "teardown-infra.sh").read_text(encoding="utf-8")
        self.assertIn('Teardown apply requires an explicit --approve argument', source)
        self.assertIn('tofu -chdir=infra/opentofu plan -destroy', source)
        self.assertIn('--operation destroy --allow-destroy --allow-stateful-batch', source)
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "teardown-infra.sh")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

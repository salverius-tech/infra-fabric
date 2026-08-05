from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("execution_snapshot", ROOT / "scripts" / "execution-snapshot.py")
assert SPEC and SPEC.loader
EXECUTION_SNAPSHOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXECUTION_SNAPSHOT)


class ExecutionSnapshotTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        values_dir = root / "values" / "sites" / "dev"
        generated = values_dir / "generated"
        generated.mkdir(parents=True)
        (values_dir / "site.yaml").write_text("schema_version: 1\n", encoding="utf-8")
        (values_dir / "secrets.sops.yaml").write_text("sops: encrypted-metadata\n", encoding="utf-8")
        (values_dir / ".sops.yaml").write_text("creation_rules: []\n", encoding="utf-8")
        for name in EXECUTION_SNAPSHOT.GENERATED_FILES:
            (generated / name).write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
        plan = values_dir / "tfplan"
        plan.write_bytes(b"synthetic-binary-plan")
        metadata = values_dir / "tfplan.meta.json"
        metadata.write_text('{"schema_version":5}\n', encoding="utf-8")
        return values_dir, plan, metadata

    def test_snapshot_is_complete_read_only_and_hash_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values_dir, plan, metadata = self.fixture(root)
            snapshot = EXECUTION_SNAPSHOT.create_snapshot(
                values_dir,
                plan,
                metadata,
                values_dir / ".execution-snapshots",
                site="dev",
            )
            manifest = EXECUTION_SNAPSHOT.verify_snapshot(snapshot)
            relative_snapshot = Path(os.path.relpath(snapshot, Path.cwd()))
            EXECUTION_SNAPSHOT.verify_snapshot(relative_snapshot)
            self.assertEqual(manifest["site"], "dev")
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o500)
            self.assertEqual((snapshot / "tfplan").stat().st_mode & 0o777, 0o400)
            self.assertTrue((snapshot / "values/sites/dev/generated/manifest.json").is_file())
            self.assertTrue((snapshot / "values/sites/dev/secrets.sops.yaml").is_file())
            self.assertNotIn("encrypted-metadata", json.dumps(manifest))

    def test_snapshot_remains_stable_when_live_inputs_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values_dir, plan, metadata = self.fixture(root)
            snapshot = EXECUTION_SNAPSHOT.create_snapshot(
                values_dir,
                plan,
                metadata,
                values_dir / ".execution-snapshots",
                site="dev",
            )
            plan.write_bytes(b"changed-live-plan")
            (values_dir / "generated/ansible-vars.json").write_text('{"changed":true}\n', encoding="utf-8")
            EXECUTION_SNAPSHOT.verify_snapshot(snapshot)
            self.assertEqual((snapshot / "tfplan").read_bytes(), b"synthetic-binary-plan")
            self.assertNotIn("changed", (snapshot / "values/sites/dev/generated/ansible-vars.json").read_text())

    def test_snapshot_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values_dir, plan, metadata = self.fixture(root)
            snapshot = EXECUTION_SNAPSHOT.create_snapshot(
                values_dir,
                plan,
                metadata,
                values_dir / ".execution-snapshots",
                site="dev",
            )
            copied_plan = snapshot / "tfplan"
            copied_plan.chmod(0o600)
            copied_plan.write_bytes(b"tampered")
            copied_plan.chmod(0o400)
            with self.assertRaisesRegex(EXECUTION_SNAPSHOT.ExecutionSnapshotError, "integrity"):
                EXECUTION_SNAPSHOT.verify_snapshot(snapshot)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values_dir, plan, metadata = self.fixture(root)
            policy = values_dir / ".sops.yaml"
            target = values_dir / "policy-target"
            target.write_text("creation_rules: []\n", encoding="utf-8")
            policy.unlink()
            policy.symlink_to(target)
            with self.assertRaisesRegex(EXECUTION_SNAPSHOT.ExecutionSnapshotError, "non-symlink"):
                EXECUTION_SNAPSHOT.create_snapshot(
                    values_dir,
                    plan,
                    metadata,
                    values_dir / ".execution-snapshots",
                    site="dev",
                )

    def test_apply_consumes_snapshot_plan_values_and_projections(self) -> None:
        source = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        create = 'execution_snapshot="$(python scripts/execution-snapshot.py create'
        storage = "python scripts/storage-vars.py --summary"
        apply = "apply_command=(tofu -chdir=infra/opentofu apply"
        self.assertIn(create, source)
        self.assertIn('export VALUES_DIR="${execution_snapshot}/values"', source)
        self.assertIn('${execution_values_dir}/generated/terraform.auto.tfvars.json', source)
        self.assertIn('../../${execution_plan}', source)
        self.assertLess(source.index(create), source.index(storage))
        self.assertLess(source.index(create), source.index(apply))


if __name__ == "__main__":
    unittest.main()

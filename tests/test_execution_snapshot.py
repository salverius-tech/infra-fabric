from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "execution_snapshot", ROOT / "scripts" / "execution-snapshot.py"
)
assert SPEC and SPEC.loader
EXECUTION_SNAPSHOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXECUTION_SNAPSHOT)


class ExecutionSnapshotTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        values_dir = root / "values" / "sites" / "dev"
        generated = values_dir / "generated"
        generated.mkdir(parents=True)
        (values_dir / "site.yaml").write_text("schema_version: 1\n", encoding="utf-8")
        (values_dir / "secrets.sops.yaml").write_text(
            "sops: encrypted-metadata\n", encoding="utf-8"
        )
        (values_dir / ".sops.yaml").write_text("creation_rules: []\n", encoding="utf-8")
        for name in EXECUTION_SNAPSHOT.GENERATED_FILES:
            (generated / name).write_text(
                json.dumps({"name": name}) + "\n", encoding="utf-8"
            )
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
            self.assertTrue(
                (snapshot / "values/sites/dev/generated/manifest.json").is_file()
            )
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
            (values_dir / "generated/ansible-vars.json").write_text(
                '{"changed":true}\n', encoding="utf-8"
            )
            EXECUTION_SNAPSHOT.verify_snapshot(snapshot)
            self.assertEqual(
                (snapshot / "tfplan").read_bytes(), b"synthetic-binary-plan"
            )
            self.assertNotIn(
                "changed",
                (snapshot / "values/sites/dev/generated/ansible-vars.json").read_text(),
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_verify_rejects_valid_attacker_snapshot_after_ancestor_is_replaced(
        self,
    ) -> None:
        """Verification must not authorize a snapshot through a swapped ancestor."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ancestor = root / "victim-parent" / "ancestor"
            values_dir, plan, metadata = self.fixture(ancestor)
            victim = EXECUTION_SNAPSHOT.create_snapshot(
                values_dir, plan, metadata, ancestor / "snapshots", site="dev"
            )

            attacker_parent = root / "attacker-parent"
            attacker_values, attacker_plan, attacker_metadata = self.fixture(
                attacker_parent
            )
            attacker_plan.write_bytes(b"attacker-plan")
            attacker = EXECUTION_SNAPSHOT.create_snapshot(
                attacker_values,
                attacker_plan,
                attacker_metadata,
                attacker_parent / "snapshots",
                site="dev",
            )
            attacker_target = attacker_parent / "replacement-ancestor"
            attacker_snapshots = attacker_target / "snapshots"
            attacker_snapshots.mkdir(parents=True)
            # The separately valid sealed directory is only made writable long enough
            # to arrange the attacker-controlled namespace, then resealed.
            attacker.chmod(0o700)
            attacker.rename(attacker_snapshots / victim.name)
            (attacker_snapshots / victim.name).chmod(0o500)

            moved_ancestor = root / "victim-parent" / "ancestor-held"
            ancestor.rename(moved_ancestor)
            ancestor.symlink_to(attacker_target, target_is_directory=True)

            with self.assertRaisesRegex(
                EXECUTION_SNAPSHOT.ExecutionSnapshotError, "unsafe"
            ):
                EXECUTION_SNAPSHOT.verify_snapshot(
                    root / "victim-parent" / "ancestor" / "snapshots" / victim.name
                )

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
            with self.assertRaisesRegex(
                EXECUTION_SNAPSHOT.ExecutionSnapshotError, "integrity"
            ):
                EXECUTION_SNAPSHOT.verify_snapshot(snapshot)

    def test_create_keeps_held_source_when_pathname_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values_dir, plan, metadata = self.fixture(root)
            original = plan.read_bytes()
            original_copy = EXECUTION_SNAPSHOT._copy
            swapped = False

            def copy_then_replace(source, destination):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    replacement = plan.with_name("replacement-plan")
                    replacement.write_bytes(b"replacement-plan-bytes")
                    replacement.replace(plan)
                return original_copy(source, destination)

            with patch.object(
                EXECUTION_SNAPSHOT, "_copy", side_effect=copy_then_replace
            ):
                snapshot = EXECUTION_SNAPSHOT.create_snapshot(
                    values_dir, plan, metadata, root / "snapshots", site="dev"
                )
            self.assertEqual((snapshot / "tfplan").read_bytes(), original)

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
            with self.assertRaisesRegex(
                EXECUTION_SNAPSHOT.ExecutionSnapshotError, "non-symlink"
            ):
                EXECUTION_SNAPSHOT.create_snapshot(
                    values_dir,
                    plan,
                    metadata,
                    values_dir / ".execution-snapshots",
                    site="dev",
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_create_uses_held_bytes_for_every_execution_source_class(self) -> None:
        """Same-size replacement or symlink after open cannot mix snapshot inputs."""
        for relative in (
            "tfplan",
            "tfplan.meta.json",
            "site.yaml",
            "secrets.sops.yaml",
            ".sops.yaml",
            *EXECUTION_SNAPSHOT.GENERATED_FILES,
        ):
            with self.subTest(
                relative=relative
            ), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                values_dir, plan, metadata = self.fixture(root)
                source = (
                    plan
                    if relative == "tfplan"
                    else (
                        metadata
                        if relative == "tfplan.meta.json"
                        else (
                            values_dir / "generated" / relative
                            if relative in EXECUTION_SNAPSHOT.GENERATED_FILES
                            else values_dir / relative
                        )
                    )
                )
                expected = source.read_bytes()
                attacker = root / "attacker-source"
                attacker.write_bytes(b"X" * len(expected))
                original_copy = EXECUTION_SNAPSHOT._copy
                swapped = False

                def copy_after_swap(
                    held,
                    destination,
                    bound_source=source,
                    bound_attacker=attacker,
                    bound_copy=original_copy,
                ):
                    nonlocal swapped
                    if destination.name == bound_source.name and not swapped:
                        swapped = True
                        bound_source.unlink()
                        bound_source.symlink_to(bound_attacker)
                    return bound_copy(held, destination)

                with patch.object(
                    EXECUTION_SNAPSHOT, "_copy", side_effect=copy_after_swap
                ):
                    snapshot = EXECUTION_SNAPSHOT.create_snapshot(
                        values_dir, plan, metadata, root / "snapshots", site="dev"
                    )
                copied = (
                    snapshot / "tfplan"
                    if relative == "tfplan"
                    else (
                        snapshot / "tfplan.meta.json"
                        if relative == "tfplan.meta.json"
                        else (
                            snapshot
                            / "values"
                            / "sites"
                            / "dev"
                            / "generated"
                            / relative
                            if relative in EXECUTION_SNAPSHOT.GENERATED_FILES
                            else snapshot / "values" / "sites" / "dev" / relative
                        )
                    )
                )
                self.assertTrue(swapped)
                self.assertEqual(copied.read_bytes(), expected)
                self.assertEqual(attacker.read_bytes(), b"X" * len(expected))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_create_keeps_staging_and_publication_on_held_root_after_root_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values_dir, plan, metadata = self.fixture(root)
            destination_root = values_dir / ".execution-snapshots"
            redirected = root / "redirected"
            redirected.mkdir()
            original_copy = EXECUTION_SNAPSHOT._copy
            swapped = False

            def copy_then_swap(source: Path, destination: Path) -> None:
                nonlocal swapped
                original_copy(source, destination)
                if not swapped:
                    swapped = True
                    destination_root.rename(
                        values_dir / ".execution-snapshots-original"
                    )
                    destination_root.symlink_to(redirected, target_is_directory=True)

            with patch.object(EXECUTION_SNAPSHOT, "_copy", side_effect=copy_then_swap):
                snapshot = EXECUTION_SNAPSHOT.create_snapshot(
                    values_dir, plan, metadata, destination_root, site="dev"
                )
            self.assertTrue(snapshot.is_dir())
            self.assertFalse(any(redirected.iterdir()))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_create_keeps_manifest_seal_and_publication_on_held_root_after_swap(
        self,
    ) -> None:
        """Every post-copy stage must remain rooted at the original held directory."""
        for phase in ("manifest", "seal", "publish"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                values_dir, plan, metadata = self.fixture(root)
                destination_root = values_dir / ".execution-snapshots"
                redirected = root / "redirected"
                redirected.mkdir()
                original_root = values_dir / ".execution-snapshots-original"
                swapped = False

                def swap_root(
                    bound_destination=destination_root,
                    bound_original=original_root,
                    bound_redirected=redirected,
                ) -> None:
                    nonlocal swapped
                    if not swapped:
                        swapped = True
                        bound_destination.rename(bound_original)
                        bound_destination.symlink_to(
                            bound_redirected, target_is_directory=True
                        )

                if phase == "manifest":
                    original = EXECUTION_SNAPSHOT.write_private_manifest

                    def hook(*args, bound_original=original, **kwargs):
                        result = bound_original(*args, **kwargs)
                        swap_root()
                        return result

                    patch_target = patch.object(
                        EXECUTION_SNAPSHOT, "write_private_manifest", side_effect=hook
                    )
                elif phase == "seal":
                    original = EXECUTION_SNAPSHOT._seal

                    def hook(*args, bound_original=original, **kwargs):
                        result = bound_original(*args, **kwargs)
                        swap_root()
                        return result

                    patch_target = patch.object(
                        EXECUTION_SNAPSHOT, "_seal", side_effect=hook
                    )
                else:
                    original = EXECUTION_SNAPSHOT.staging_directory

                    @contextlib.contextmanager
                    def hook(*args, bound_original=original, **kwargs):
                        with bound_original(*args, **kwargs) as staging:
                            publish = staging.publish

                            def publish_hook(*publish_args, **publish_kwargs):
                                swap_root()
                                return publish(*publish_args, **publish_kwargs)

                            staging.publish = publish_hook
                            yield staging

                    patch_target = patch.object(
                        EXECUTION_SNAPSHOT, "staging_directory", hook
                    )
                with patch_target:
                    snapshot = EXECUTION_SNAPSHOT.create_snapshot(
                        values_dir, plan, metadata, destination_root, site="dev"
                    )
                self.assertTrue(snapshot.is_dir())
                self.assertTrue(any(original_root.iterdir()))
                self.assertFalse(any(redirected.iterdir()))

    def test_apply_consumes_snapshot_plan_values_and_projections(self) -> None:
        source = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        create = 'execution_snapshot="$(python scripts/execution-snapshot.py create'
        storage = "python scripts/storage-vars.py --summary"
        apply = "apply_command=(tofu -chdir=infra/opentofu apply"
        self.assertIn(create, source)
        self.assertIn('export VALUES_DIR="${execution_snapshot}/values"', source)
        self.assertIn(
            "${execution_values_dir}/generated/terraform.auto.tfvars.json", source
        )
        self.assertIn('execution_plan_argument="${execution_plan}"', source)
        self.assertIn('if [[ "${execution_plan_argument}" != /* ]]', source)
        self.assertIn('execution_plan_argument="../../${execution_plan_argument}"', source)
        self.assertIn('"${execution_plan_argument}"', source)
        self.assertLess(source.index(create), source.index(storage))
        self.assertLess(source.index(create), source.index(apply))

    def test_lifecycle_snapshot_root_override_preserves_the_default_and_container_boundary(self) -> None:
        apply_source = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        teardown_source = (ROOT / "scripts" / "teardown-infra.sh").read_text(encoding="utf-8")
        wrapper_source = (ROOT / "scripts" / "run-infra.sh").read_text(encoding="utf-8")
        default = '"${INFRA_EXECUTION_SNAPSHOT_ROOT:-${INFRA_VALUES_DIR}/execution-snapshots}"'
        self.assertIn(default, apply_source)
        self.assertIn(default, teardown_source)
        self.assertIn('--destination-root "${execution_snapshot_root}"', apply_source)
        self.assertIn('--destination-root "${execution_snapshot_root}"', teardown_source)
        self.assertIn('must be an absolute private host path', wrapper_source)
        self.assertIn('must not be a symlink', wrapper_source)
        self.assertIn('INFRA_EXECUTION_SNAPSHOT_ROOT=/run/infra-fabric/execution-snapshots', wrapper_source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from migration_backup import BackupManifestError, build_manifest, emit_manifest, expand_backup_paths, verify_manifest


class MigrationBackupTests(unittest.TestCase):
    def make_tree(self, root: Path) -> list[str]:
        (root / "site").mkdir()
        (root / "site" / "terraform.tfvars").write_text("address = 192.0.2.10\n", encoding="utf-8")
        (root / "site" / "dns-records.json").write_text('{"zone":"example.internal"}\n', encoding="utf-8")
        return ["site/dns-records.json", "site/terraform.tfvars"]

    def test_manifest_is_deterministic_and_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.make_tree(root)
            first = build_manifest(root, list(reversed(paths)))
            second = build_manifest(root, paths)
            self.assertEqual(first, second)
            self.assertEqual([entry["path"] for entry in first["entries"]], sorted(paths))

    def test_hash_verification_accepts_unchanged_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = build_manifest(root, self.make_tree(root))
            verify_manifest(root, manifest)

    def test_changed_missing_and_unexpected_files_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = build_manifest(root, self.make_tree(root))
            (root / "site" / "terraform.tfvars").write_text("changed\n", encoding="utf-8")
            with self.assertRaises(BackupManifestError):
                verify_manifest(root, manifest)
            (root / "site" / "terraform.tfvars").unlink()
            with self.assertRaises(BackupManifestError):
                verify_manifest(root, manifest)
            (root / "site" / "terraform.tfvars").write_text("address = 192.0.2.10\n", encoding="utf-8")
            (root / "extra.txt").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaises(BackupManifestError):
                verify_manifest(root, manifest)
            (root / "extra.txt").unlink()
            (root / "unexpected-link").symlink_to(root / "site" / "terraform.tfvars")
            with self.assertRaises(BackupManifestError):
                verify_manifest(root, manifest)

    def test_traversal_absolute_duplicate_and_symlink_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            for paths in (["../outside"], [str(root / "site" / "dns-records.json")], ["site/dns-records.json"] * 2):
                with self.subTest(paths=paths), self.assertRaises(BackupManifestError):
                    build_manifest(root, paths)
            link = root / "link"
            link.symlink_to(root / "site" / "dns-records.json")
            with self.assertRaises(BackupManifestError):
                build_manifest(root, ["link"])

    def test_manifest_errors_do_not_contain_fixture_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.make_tree(root)
            manifest = build_manifest(root, paths)
            (root / paths[0]).write_text("REPLACE_SECRET\n", encoding="utf-8")
            with self.assertRaises(BackupManifestError) as context:
                verify_manifest(root, manifest)
            self.assertNotIn("REPLACE_SECRET", str(context.exception))

    def test_disposable_restore_rehearsal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.make_tree(root)
            backup = root / "backup"
            working = root / "working"
            shutil.copytree(root / "site", backup)
            shutil.copytree(root / "site", working)
            manifest = build_manifest(backup, relative_paths=[path.removeprefix("site/") for path in paths])
            shutil.rmtree(working)
            shutil.copytree(backup, working)
            verify_manifest(backup, manifest)
            self.assertEqual(
                sorted(path.relative_to(working).as_posix() for path in working.rglob("*")),
                sorted(path.removeprefix("site/") for path in paths),
            )

    def test_emit_stages_selected_files_and_creates_explicit_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "values"
            root.mkdir()
            paths = self.make_tree(root)
            output = Path(directory) / "artifacts" / "backup.json"
            output.parent.mkdir()
            manifest = emit_manifest(root, [paths[0]], output)
            self.assertEqual([entry["path"] for entry in manifest["entries"]], [paths[0]])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), manifest)
            self.assertTrue((root / paths[1]).is_file())

    def test_restore_backup_verifies_and_restores_selected_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.make_tree(root)
            backup = root / "backup"
            from migration_backup import create_backup, restore_backup

            create_backup(root, paths, backup)
            (root / "site" / "terraform.tfvars").write_text("changed\n", encoding="utf-8")
            restore_backup(backup, root)
            self.assertEqual((root / "site" / "terraform.tfvars").read_text(encoding="utf-8"), "address = 192.0.2.10\n")

    def test_recursive_expansion_is_sorted_posix_ignores_empty_dirs_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "service-backups" / "z").mkdir(parents=True)
            (root / "service-backups" / "a").mkdir()
            (root / "service-backups" / "z" / "later.tar").write_text("z", encoding="utf-8")
            (root / "service-backups" / "a" / "first.tar").write_text("a", encoding="utf-8")
            self.assertEqual(
                expand_backup_paths(root, ["service-backups", "service-backups/a/first.tar"]),
                ["service-backups/a/first.tar", "service-backups/z/later.tar"],
            )


    def test_recursive_expansion_rejects_nested_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "service-backups"
            selected.mkdir()
            (selected / "real.tar").write_text("real", encoding="utf-8")
            (selected / "link.tar").symlink_to(selected / "real.tar")
            with self.assertRaises(BackupManifestError):
                expand_backup_paths(root, ["service-backups"])

    def test_emit_accepts_directories_but_rejects_symlinked_parents_and_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "values"
            root.mkdir()
            paths = self.make_tree(root)
            output = Path(directory) / "backup.json"
            manifest = emit_manifest(root, ["site"], output)
            self.assertEqual([entry["path"] for entry in manifest["entries"]], paths)
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("sentinel", encoding="utf-8")
            (root / "escape").symlink_to(outside, target_is_directory=True)
            symlink_output = Path(directory) / "symlink-backup.json"
            with self.assertRaises(BackupManifestError):
                emit_manifest(root, ["escape/secret.txt"], symlink_output)
            output.write_text("do not replace", encoding="utf-8")
            with self.assertRaises(BackupManifestError):
                emit_manifest(root, paths, output)
            self.assertEqual(output.read_text(encoding="utf-8"), "do not replace")


    def test_recursive_expansion_is_sorted_unique_and_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            (root / "site" / "nested").mkdir()
            (root / "site" / "nested" / "extra.txt").write_text("public\n", encoding="utf-8")
            self.assertEqual(
                expand_backup_paths(root, ["site", "site/dns-records.json"]),
                ["site/dns-records.json", "site/nested/extra.txt", "site/terraform.tfvars"],
            )
            (root / "site" / "escape").symlink_to(root / "site" / "nested", target_is_directory=True)
            with self.assertRaises(BackupManifestError):
                expand_backup_paths(root, ["site"])


if __name__ == "__main__":
    unittest.main()

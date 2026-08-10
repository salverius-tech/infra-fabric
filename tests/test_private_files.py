from __future__ import annotations

import contextlib
import errno
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_files


class PrivateFilesTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_open_regular_file_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_bytes(b"data")
            source = root / "source"
            source.symlink_to(target)
            with self.assertRaisesRegex(
                private_files.PrivateFileError, "regular non-symlink"
            ), private_files.open_regular_file(source, "source"):
                pass

    def test_atomic_copy_is_private_fsynced_and_uses_atomic_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "private" / "destination"
            source.write_bytes(b"durable data")
            with patch.object(
                private_files.os, "fsync", wraps=os.fsync
            ) as fsync, patch.object(
                private_files.os, "replace", wraps=os.replace
            ) as replace:
                private_files.atomic_copy(source, destination, label="source")
            self.assertEqual(destination.read_bytes(), b"durable data")
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            self.assertGreaterEqual(fsync.call_count, 2)
            self.assertEqual(replace.call_count, 1)

    def test_private_directory_and_manifest_are_restrictive_and_durable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "private" / "nested"
            with patch.object(private_files.os, "fsync", wraps=os.fsync) as fsync:
                private_files.ensure_private_directory(directory)
                manifest = private_files.write_private_manifest(
                    directory / "manifest.json", {"ok": True}
                )
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o600)
            self.assertGreaterEqual(fsync.call_count, 3)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_private_directory_rejects_symlinked_ancestor_without_chmodding_existing_ancestor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir(mode=0o755)
            target = root / "target"
            target.mkdir()
            (existing / "redirect").symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(private_files.PrivateFileError, "unsafe"):
                private_files.ensure_private_directory(
                    existing / "redirect" / "private"
                )
            self.assertEqual(stat.S_IMODE(existing.stat().st_mode), 0o755)
            self.assertFalse((target / "private").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_private_directory_rejects_a_symlinked_final_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            destination = root / "private"
            destination.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(private_files.PrivateFileError, "unsafe"):
                private_files.ensure_private_directory(destination)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_staging_prune_unlinks_symlink_tree_through_held_root_after_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination_root = root / "ancestor" / "private"
            redirected = root / "redirected"
            redirected.mkdir()
            sentinel = redirected / "sentinel"
            sentinel.write_bytes(b"untouched")
            with patch.object(
                private_files.os, "fsync", wraps=os.fsync
            ) as fsync, private_files.staging_directory(
                destination_root, prefix=".next-"
            ) as staging:
                old = Path(f"/proc/self/fd/{staging._parent_fd}/snapshot-000")
                (old / "nested").mkdir(parents=True)
                (old / "nested" / "payload").write_bytes(b"old")
                (old / "nested" / "escape").symlink_to(redirected)
                new = Path(f"/proc/self/fd/{staging._parent_fd}/snapshot-999")
                new.mkdir()
                destination_root.parent.rename(root / "ancestor-held")
                destination_root.parent.symlink_to(redirected, target_is_directory=True)
                staging.prune(prefix="snapshot-", retain=1)
                self.assertFalse(old.exists())
                self.assertTrue(new.is_dir())
            self.assertEqual(sentinel.read_bytes(), b"untouched")
            self.assertGreaterEqual(fsync.call_count, 2)

    def test_staging_publish_preserves_real_collision_and_cleans_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination_root = root / "private"
            with self.assertRaisesRegex(
                private_files.PrivateFileError, "already exists"
            ), private_files.staging_directory(
                destination_root, prefix=".next-"
            ) as staging:
                (staging.path / "payload").write_bytes(b"staged")
                sentinel_dir = Path(f"/proc/self/fd/{staging._parent_fd}/snapshot")
                sentinel_dir.mkdir()
                (sentinel_dir / "sentinel").write_bytes(b"keep")
                staging.publish("snapshot")
            self.assertEqual(
                (destination_root / "snapshot" / "sentinel").read_bytes(), b"keep"
            )
            self.assertFalse(list(destination_root.glob(".next-*")))

    def test_staging_publish_fails_closed_when_renameat2_is_unsupported(self) -> None:
        class UnsupportedLibc:
            @staticmethod
            def syscall(*_args):
                return -1

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(
                private_files.ctypes, "CDLL", return_value=UnsupportedLibc()
            ), patch.object(
                private_files.ctypes, "get_errno", return_value=errno.ENOSYS
            ), self.assertRaisesRegex(
                private_files.PrivateFileError, "unavailable"
            ), private_files.staging_directory(
                root / "private", prefix=".next-"
            ) as staging:
                staging.publish("snapshot")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_atomic_copy_keeps_verified_parent_when_destination_path_is_replaced(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"durable data")
            destination_parent = root / "private"
            destination_parent.mkdir()
            destination = destination_parent / "destination"
            redirected = root / "redirected"
            redirected.mkdir()
            real_replace = os.replace

            def replace_with_parent_swap(
                source_name, destination_name, *args, **kwargs
            ):
                destination_parent.rename(root / "private-original")
                destination_parent.symlink_to(redirected, target_is_directory=True)
                return real_replace(source_name, destination_name, *args, **kwargs)

            with patch.object(
                private_files.os, "replace", side_effect=replace_with_parent_swap
            ):
                private_files.atomic_copy(source, destination, label="source")

            self.assertEqual(
                (root / "private-original" / "destination").read_bytes(),
                b"durable data",
            )
            self.assertFalse((redirected / "destination").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_staging_directory_publishes_through_the_verified_parent_after_path_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination_root = root / "private"
            destination_root.mkdir()
            redirected = root / "redirected"
            redirected.mkdir()
            with private_files.staging_directory(
                destination_root, prefix=".next-"
            ) as staging:
                (staging.path / "payload").write_bytes(b"durable data")
                destination_root.rename(root / "private-original")
                destination_root.symlink_to(redirected, target_is_directory=True)
                staging.publish("snapshot")
            self.assertEqual(
                (root / "private-original" / "snapshot" / "payload").read_bytes(),
                b"durable data",
            )
            self.assertFalse((redirected / "snapshot").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_staging_directory_publishes_populated_stage_through_held_ancestor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination_root = root / "ancestor" / "private"
            attacker = root / "attacker"
            attacker.mkdir()
            sentinel = attacker / "sentinel"
            sentinel.write_bytes(b"untouched")
            held_identity = (-1, -1)
            with private_files.staging_directory(
                destination_root, prefix=".next-"
            ) as staging:
                held_identity = (
                    os.fstat(staging._parent_fd).st_dev,
                    os.fstat(staging._parent_fd).st_ino,
                )
                (staging.path / "nested").mkdir()
                (staging.path / "nested" / "payload").write_bytes(b"staged")
                destination_root.parent.rename(root / "ancestor-held")
                destination_root.parent.symlink_to(attacker, target_is_directory=True)
                staging.publish("snapshot")
            held_root = root / "ancestor-held" / "private"
            self.assertEqual(
                (held_root.stat().st_dev, held_root.stat().st_ino), held_identity
            )
            self.assertEqual(
                (held_root / "snapshot" / "nested" / "payload").read_bytes(),
                b"staged",
            )
            self.assertEqual(sentinel.read_bytes(), b"untouched")
            self.assertFalse((attacker / "private" / "snapshot").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_staging_directory_cleans_populated_stage_through_held_ancestor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination_root = root / "ancestor" / "private"
            attacker = root / "attacker"
            attacker.mkdir()
            sentinel = attacker / "sentinel"
            sentinel.write_bytes(b"untouched")
            held_identity = (-1, -1)
            with self.assertRaisesRegex(
                RuntimeError, "abort"
            ), private_files.staging_directory(
                destination_root, prefix=".next-"
            ) as staging:
                held_identity = (
                    os.fstat(staging._parent_fd).st_dev,
                    os.fstat(staging._parent_fd).st_ino,
                )
                (staging.path / "nested").mkdir()
                (staging.path / "nested" / "payload").write_bytes(b"staged")
                destination_root.parent.rename(root / "ancestor-held")
                destination_root.parent.symlink_to(attacker, target_is_directory=True)
                raise RuntimeError("abort")
            held_root = root / "ancestor-held" / "private"
            self.assertEqual(
                (held_root.stat().st_dev, held_root.stat().st_ino), held_identity
            )
            self.assertFalse(list(held_root.glob(".next-*")))
            self.assertEqual(sentinel.read_bytes(), b"untouched")
            self.assertFalse((attacker / "private").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_atomic_copy_no_replace_preserves_racer_and_cleans_temp_after_parent_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"snapshot")
            parent = root / "ancestor" / "private"
            destination = parent / "destination"
            redirected = root / "redirected"
            redirected.mkdir()
            real_link = os.link

            def race_then_link(source_name, destination_name, *args, **kwargs):
                parent_fd = kwargs["dst_dir_fd"]
                racer_fd = os.open(
                    "destination",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_fd,
                )
                try:
                    os.write(racer_fd, b"racer")
                finally:
                    os.close(racer_fd)
                (root / "ancestor-held").mkdir()
                parent.rename(root / "ancestor-held" / "private")
                parent.symlink_to(redirected, target_is_directory=True)
                return real_link(source_name, destination_name, *args, **kwargs)

            with patch.object(
                private_files.os, "link", side_effect=race_then_link
            ), self.assertRaisesRegex(private_files.PrivateFileError, "already exists"):
                private_files.atomic_copy(
                    source, destination, label="source", replace_existing=False
                )
            held_parent = root / "ancestor-held" / "private"
            self.assertEqual((held_parent / "destination").read_bytes(), b"racer")
            self.assertFalse(list(held_parent.glob(".destination.*")))
            self.assertFalse(any(redirected.iterdir()))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_atomic_copy_installs_through_held_ancestor_after_temp_acquisition(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"snapshot")
            parent = root / "ancestor" / "private"
            parent.mkdir(parents=True)
            destination = parent / "destination"
            attacker = root / "attacker"
            attacker.mkdir()
            sentinel = attacker / "sentinel"
            sentinel.write_bytes(b"untouched")
            held_identity = (-1, -1)
            real_temporary_file = private_files._temporary_file

            def temporary_file_then_swap(parent_fd, prefix):
                nonlocal held_identity
                descriptor, name = real_temporary_file(parent_fd, prefix)
                held_identity = os.fstat(parent_fd).st_dev, os.fstat(parent_fd).st_ino
                parent.parent.rename(root / "ancestor-held")
                parent.parent.symlink_to(attacker, target_is_directory=True)
                return descriptor, name

            with patch.object(
                private_files,
                "_temporary_file",
                side_effect=temporary_file_then_swap,
            ):
                private_files.atomic_copy(source, destination, label="source")
            held_parent = root / "ancestor-held" / "private"
            self.assertEqual(
                (held_parent.stat().st_dev, held_parent.stat().st_ino), held_identity
            )
            self.assertEqual((held_parent / "destination").read_bytes(), b"snapshot")
            self.assertFalse(list(held_parent.glob(".destination.*")))
            self.assertEqual(sentinel.read_bytes(), b"untouched")
            self.assertFalse((attacker / "private" / "destination").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_atomic_copy_no_replace_cleans_held_ancestor_temp_after_collision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"snapshot")
            parent = root / "ancestor" / "private"
            parent.mkdir(parents=True)
            destination = parent / "destination"
            attacker = root / "attacker"
            attacker.mkdir()
            sentinel = attacker / "sentinel"
            sentinel.write_bytes(b"untouched")
            held_identity = (-1, -1)
            real_temporary_file = private_files._temporary_file

            def temporary_file_then_race_and_swap(parent_fd, prefix):
                nonlocal held_identity
                descriptor, name = real_temporary_file(parent_fd, prefix)
                held_identity = os.fstat(parent_fd).st_dev, os.fstat(parent_fd).st_ino
                racer_fd = os.open(
                    "destination",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_fd,
                )
                try:
                    os.write(racer_fd, b"racer")
                finally:
                    os.close(racer_fd)
                parent.parent.rename(root / "ancestor-held")
                parent.parent.symlink_to(attacker, target_is_directory=True)
                return descriptor, name

            with patch.object(
                private_files,
                "_temporary_file",
                side_effect=temporary_file_then_race_and_swap,
            ), self.assertRaisesRegex(private_files.PrivateFileError, "already exists"):
                private_files.atomic_copy(
                    source, destination, label="source", replace_existing=False
                )
            held_parent = root / "ancestor-held" / "private"
            self.assertEqual(
                (held_parent.stat().st_dev, held_parent.stat().st_ino), held_identity
            )
            self.assertEqual((held_parent / "destination").read_bytes(), b"racer")
            self.assertFalse(list(held_parent.glob(".destination.*")))
            self.assertEqual(sentinel.read_bytes(), b"untouched")
            self.assertFalse((attacker / "private" / "destination").exists())

    def test_atomic_copy_without_replacement_refuses_a_destination_created_before_install(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"snapshot")
            destination = root / "private" / "destination"
            real_open = private_files.open_regular_file

            @contextlib.contextmanager
            def create_destination_after_source_open(*args, **kwargs):
                with real_open(*args, **kwargs) as handle:
                    destination.parent.mkdir(exist_ok=True)
                    destination.write_bytes(b"racer")
                    yield handle

            with patch.object(
                private_files, "open_regular_file", create_destination_after_source_open
            ), self.assertRaisesRegex(private_files.PrivateFileError, "already exists"):
                private_files.atomic_copy(
                    source, destination, label="source", replace_existing=False
                )
            self.assertEqual(destination.read_bytes(), b"racer")
            self.assertFalse(list(destination.parent.glob(".destination.*")))

    def test_atomic_copy_removes_held_parent_temp_when_publication_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"source")
            destination = root / "private" / "destination"
            with patch.object(
                private_files.os, "replace", side_effect=OSError("boom")
            ), self.assertRaisesRegex(
                private_files.PrivateFileError, "atomically install"
            ):
                private_files.atomic_copy(source, destination, label="source")
            self.assertFalse(list(destination.parent.glob(".destination.*")))

    def test_staging_directory_propagates_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(
                private_files, "_remove_tree", side_effect=OSError("boom")
            ), self.assertRaisesRegex(
                private_files.PrivateFileError, "cleanup"
            ), private_files.staging_directory(
                root / "private", prefix=".next-"
            ) as staging:
                (staging.path / "payload").write_bytes(b"data")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_populated_unpublished_staging_is_removed_through_held_root_after_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination_root = root / "private"
            redirected = root / "redirected"
            redirected.mkdir()
            with self.assertRaisesRegex(
                RuntimeError, "abort"
            ), private_files.staging_directory(
                destination_root, prefix=".next-"
            ) as staging:
                (staging.path / "nested").mkdir()
                (staging.path / "nested" / "payload").write_bytes(b"data")
                destination_root.rename(root / "private-original")
                destination_root.symlink_to(redirected, target_is_directory=True)
                raise RuntimeError("abort")
            self.assertFalse(list((root / "private-original").glob(".next-*")))
            self.assertFalse(any(redirected.iterdir()))


if __name__ == "__main__":
    unittest.main()

"""Process-level contract for supported site operation serialization."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/site_lock.py"
spec = importlib.util.spec_from_file_location("site_lock", SCRIPT)
assert spec and spec.loader
site_lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site_lock)


class SiteLockTests(unittest.TestCase):
    def test_same_site_concurrent_operation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".infra-fabric.lock"
            with site_lock.acquire_site_lock(lock):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--lock-path", str(lock), "--", sys.executable, "-c", "pass"],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            self.assertEqual(result.returncode, 2)
            self.assertIn("another operation", result.stderr)

    def test_different_site_locks_can_be_held_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with site_lock.acquire_site_lock(root / "site-a.lock"):
                with site_lock.acquire_site_lock(root / "site-b.lock"):
                    pass

    def test_lock_is_private_persistent_and_released_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".infra-fabric.lock"
            self.assertEqual(site_lock.run_locked(lock, [sys.executable, "-c", "raise SystemExit(7)"]), 7)
            self.assertTrue(lock.is_file())
            self.assertEqual(lock.stat().st_mode & 0o777, 0o600)
            with site_lock.acquire_site_lock(lock):
                pass

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_lock_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text("sentinel", encoding="utf-8")
            lock = root / "lock"
            lock.symlink_to(target)
            with self.assertRaises(site_lock.SiteLockError):
                with site_lock.acquire_site_lock(lock):
                    pass
            self.assertEqual(target.read_text(encoding="utf-8"), "sentinel")

    def test_run_infra_wraps_container_command_before_preflight(self) -> None:
        source = (ROOT / "scripts/run-infra.sh").read_text(encoding="utf-8")
        self.assertIn('infra python scripts/site_lock.py --lock-path "${values_dir}/.infra-fabric.lock" -- "$@"', source)


if __name__ == "__main__":
    unittest.main()

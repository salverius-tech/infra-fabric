from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "forgejo-actions-monitor.py"
SPEC = importlib.util.spec_from_file_location("forgejo_actions_monitor", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class ActionsMonitorContextTests(unittest.TestCase):
    def test_monitor_rejects_unselected_site(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(monitor.MonitorError):
                monitor.main(["status"])

    def test_monitor_rejects_missing_canonical_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            values = Path(temp) / "values" / "sites" / "dev"
            values.mkdir(parents=True)
            (values / "site.yaml").write_text("schema_version: 1\nsite: {}\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"VALUES_DIR": str(Path(temp) / "values"), "VALUES_SITE": "dev"},
                clear=True,
            ):
                with self.assertRaises(monitor.MonitorError):
                    monitor.main(["status"])


if __name__ == "__main__":
    unittest.main()
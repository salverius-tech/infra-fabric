import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-design-reconciliation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("design_reconciliation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesignReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_generated_extraction_is_current_and_complete(self) -> None:
        result = subprocess.run(
            ["python3", "-B", str(SCRIPT), "--check-extraction"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("38 audit findings", result.stdout)

    def test_every_audit_finding_has_one_stable_record(self) -> None:
        ledger = json.loads(
            (ROOT / ".hermes" / "reconciliation" / "design-implementation-ledger.json").read_text(encoding="utf-8")
        )
        findings = [record for record in ledger["records"] if record["source"]["kind"] == "finding"]
        self.assertEqual({record["id"].upper() for record in findings}, set(self.module.AUDIT_IDS))
        self.assertEqual(len(findings), len(self.module.AUDIT_IDS))
        self.assertTrue(all(record["disposition"] == "unreconciled" for record in ledger["records"]))

    def test_all_tracked_markdown_sources_are_registered_and_hashed(self) -> None:
        register = json.loads(
            (ROOT / ".hermes" / "reconciliation" / "source-register.json").read_text(encoding="utf-8")
        )
        sources = {item["path"]: item for item in register["sources"]}
        tracked_markdown = {
            path for path in self.module.source_paths() if path.endswith(".md")
        }
        self.assertTrue(tracked_markdown.issubset(sources))
        self.assertTrue(all(len(sources[path]["sha256"]) == 64 for path in tracked_markdown))


if __name__ == "__main__":
    unittest.main()

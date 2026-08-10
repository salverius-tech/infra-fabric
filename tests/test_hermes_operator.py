from __future__ import annotations

import importlib.util
import os
import stat
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hermes-operator.py"
spec = importlib.util.spec_from_file_location("hermes_operator", SCRIPT)
assert spec and spec.loader
hermes_operator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hermes_operator
spec.loader.exec_module(hermes_operator)


class HermesOperatorTests(unittest.TestCase):
    def test_redaction_removes_secrets_private_addresses_and_paths(self) -> None:
        text = (
            "TOKEN=super-secret-value host=192.168.10.20 "  # public-safety: allow-ip # public-safety: allow-secret
            "path=/workspace/values/.env url=https://git.private.internal/"
        )
        redacted = hermes_operator.redact_output(text, {"super-secret-value"})
        self.assertNotIn("super-secret-value", redacted)
        self.assertNotIn("192.168.10.20", redacted)  # public-safety: allow-ip
        self.assertNotIn("git.private.example", redacted)
        self.assertNotIn("/workspace/values/.env", redacted)
        self.assertIn("<redacted>", redacted)

    def test_apply_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(hermes_operator.OperatorError):
                hermes_operator.run_action(Path(temp), "apply", approve=False, runner=lambda *_: 0)

    def test_apply_does_not_allow_destructive_plan_without_second_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata = root / "tfplan.meta.json"
            metadata.write_text(
                json.dumps(
                    {
                        "schema_version": hermes_operator.SCHEMA_VERSION,
                        "summary": {
                            "resource_changes": {"create": 0, "update": 0, "replace": 1, "delete": 0},
                            "destructive": True,
                            "destructive_changes": [{"address": "module.example", "actions": "delete/create"}],
                            "stateful_changes": [],
                            "stateful_targets": [],
                            "stateful_services": [],
                        },
                        "plan": {"sha256": "unused"},
                        "inputs": {},
                        "scope": {"target_service": "", "replace_service": ""},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(hermes_operator.OperatorError):
                hermes_operator.run_action(root, "apply", approve=True, runner=lambda *_: 0)

    def test_selected_site_plan_summary_uses_canonical_values_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            site_dir = root / "values" / "sites" / "dev"
            site_dir.mkdir(parents=True)
            metadata = site_dir / "tfplan.meta.json"
            metadata.write_text(
                json.dumps(
                    {
                        "schema_version": hermes_operator.SCHEMA_VERSION,
                        "summary": {
                            "resource_changes": {"create": 0, "update": 0, "replace": 0, "delete": 0},
                            "destructive": False,
                            "stateful_changes": [],
                            "stateful_targets": [],
                            "stateful_services": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            previous = os.environ.get("VALUES_SITE")
            os.environ["VALUES_SITE"] = "dev"
            try:
                result = hermes_operator.run_action(root, "plan", runner=lambda *_: (0, "ok\n"))
            finally:
                if previous is None:
                    os.environ.pop("VALUES_SITE", None)
                else:
                    os.environ["VALUES_SITE"] = previous
            self.assertEqual(result["plan"]["resource_changes"]["create"], 0)
            self.assertFalse(result["plan"]["destructive"])

    def test_action_writes_audit_record_without_command_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = hermes_operator.run_action(
                root,
                "validate",
                runner=lambda *_: (0, "TOKEN=secret-value 192.168.1.5\n"),  # public-safety: allow-ip # public-safety: allow-secret
            )
            self.assertTrue(result["ok"])
            audit = json.loads((root / ".tmp" / "hermes-operator-audit.jsonl").read_text())
            self.assertEqual(audit["action"], "validate")
            self.assertNotIn("secret-value", (root / ".tmp" / "hermes-operator-audit.jsonl").read_text())

    def test_audit_records_form_a_mode_restricted_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            previous = os.environ.get("HERMES_OPERATOR_AUDIT_PATH")
            os.environ["HERMES_OPERATOR_AUDIT_PATH"] = str(audit_path)
            try:
                hermes_operator.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
                hermes_operator.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
            finally:
                if previous is None:
                    os.environ.pop("HERMES_OPERATOR_AUDIT_PATH", None)
                else:
                    os.environ["HERMES_OPERATOR_AUDIT_PATH"] = previous
            records = [json.loads(line) for line in audit_path.read_text().splitlines()]
            self.assertEqual(records[0]["previous_hash"], "0" * 64)
            self.assertEqual(records[1]["previous_hash"], records[0]["record_hash"])
            self.assertEqual(stat.S_IMODE(audit_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(audit_path.with_suffix(".lock").stat().st_mode), 0o600)

    def test_tampered_audit_journal_fails_closed_before_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / ".tmp" / "hermes-operator-audit.jsonl"
            hermes_operator.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
            audit_path.write_text(audit_path.read_text().replace('"ok":true', '"ok":false'), encoding="utf-8")
            with self.assertRaises(hermes_operator.OperatorError):
                hermes_operator.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))

    def test_audit_verify_returns_only_safe_chain_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hermes_operator.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
            result = hermes_operator.verify_audit(root)
            self.assertEqual(result["action"], "audit-verify")
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(len(result["head_hash"]), 64)
            self.assertNotIn(str(root), json.dumps(result))

    def test_audit_verify_fails_closed_when_journal_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(hermes_operator.OperatorError, "audit journal is unavailable"):
                hermes_operator.verify_audit(Path(temp))

    def test_status_is_machine_readable_and_does_not_include_private_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra").mkdir()
            (root / "infra" / "services.json").write_text(
                json.dumps({"default_services": ["hermes"], "services": {"hermes": {}}}),
                encoding="utf-8",
            )
            (root / "settings.local.json").write_text(
                '{"services":["hermes"]}\n', encoding="utf-8"
            )
            status = hermes_operator.status(root)
            self.assertEqual(status["action"], "status")
            self.assertEqual(status["enabled_services"], ["hermes"])
            self.assertNotIn("settings.local.json", json.dumps(status))
            self.assertNotIn("terraform.tfvars", json.dumps(status))


if __name__ == "__main__":
    unittest.main()

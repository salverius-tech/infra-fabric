from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hermes-operator.py"
spec = importlib.util.spec_from_file_location("hermes_operator", SCRIPT)
assert spec and spec.loader
hermes_operator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hermes_operator
spec.loader.exec_module(hermes_operator)


class HermesOperatorTests(unittest.TestCase):
    def write_hash_valid_audit(self, path: Path, records: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        previous_hash = "0" * 64
        encoded: list[str] = []
        for supplied in records:
            remove = supplied.get("_remove", [])
            record = {
                "timestamp": "2026-08-11T00:00:00+00:00",
                "correlation_id": "a" * 32,
                "phase": "intent",
                "action": "validate",
                "returncode": None,
                "ok": None,
                "plan": {"destructive": False, "resource_changes": {}},
                "previous_hash": previous_hash,
            }
            record.update(
                {key: value for key, value in supplied.items() if key != "_remove"}
            )
            for key in remove if isinstance(remove, list) else []:
                record.pop(str(key), None)
            record["previous_hash"] = previous_hash
            record["record_hash"] = hermes_operator.audit_record_hash(record)
            previous_hash = str(record["record_hash"])
            encoded.append(json.dumps(record, sort_keys=True, separators=(",", ":")))
        path.write_text("\n".join(encoded) + "\n", encoding="utf-8")

    def assert_hash_valid_audit_rejected(
        self, records: list[dict[str, Any]], message: str
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = root / "private" / "audit.jsonl"
            self.write_hash_valid_audit(audit, records)
            with (
                mock.patch.dict(os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit)}),
                self.assertRaisesRegex(hermes_operator.OperatorError, message),
            ):
                hermes_operator.verify_audit(root)

    def write_safe_plan(self, root: Path) -> None:
        (root / "tfplan.meta.json").write_text(
            json.dumps(
                {
                    "schema_version": hermes_operator.SCHEMA_VERSION,
                    "summary": {
                        "resource_changes": {
                            "create": 0,
                            "update": 0,
                            "replace": 0,
                            "delete": 0,
                        },
                        "destructive": False,
                        "stateful_changes": [],
                        "stateful_targets": [],
                        "stateful_services": [],
                    },
                }
            ),
            encoding="utf-8",
        )

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

    def test_apply_is_source_disabled_even_with_environment_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runner = mock.Mock()
            with (
                mock.patch.dict(
                    os.environ,
                    {"HERMES_OPERATOR_MUTATION_ENABLED": "1"},
                    clear=True,
                ),
                self.assertRaisesRegex(
                    hermes_operator.OperatorError, "hard read-only pilot"
                ),
            ):
                hermes_operator.run_action(
                    Path(temp), "apply", approve=True, runner=runner
                )
            runner.assert_not_called()

    def test_cli_apply_is_source_disabled_even_with_all_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with (
                mock.patch.dict(
                    os.environ,
                    {"HERMES_OPERATOR_MUTATION_ENABLED": "1"},
                    clear=True,
                ),
                mock.patch.object(sys, "stderr"),
            ):
                returncode = hermes_operator.main(
                    [
                        "apply",
                        "--repo",
                        temp,
                        "--approve",
                        "--allow-destructive",
                        "--allow-stateful-batch",
                    ]
                )
            self.assertEqual(returncode, 1)

    def test_apply_does_not_allow_destructive_plan_without_second_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata = root / "tfplan.meta.json"
            metadata.write_text(
                json.dumps(
                    {
                        "schema_version": hermes_operator.SCHEMA_VERSION,
                        "summary": {
                            "resource_changes": {
                                "create": 0,
                                "update": 0,
                                "replace": 1,
                                "delete": 0,
                            },
                            "destructive": True,
                            "destructive_changes": [
                                {
                                    "address": "module.example",
                                    "actions": "delete/create",
                                }
                            ],
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
            with (
                mock.patch.object(
                    hermes_operator, "mutation_enabled", return_value=True
                ),
                self.assertRaises(hermes_operator.OperatorError),
            ):
                hermes_operator.run_action(
                    root, "apply", approve=True, runner=lambda *_: 0
                )

    def test_apply_snapshots_durable_intent_before_runner_and_correlates_result(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_safe_plan(root)
            audit = root / "private" / "audit.jsonl"
            backups = root / "durable-backups"
            observed: list[str] = []

            def runner(*_):
                records = [json.loads(line) for line in audit.read_text().splitlines()]
                self.assertEqual([record["phase"] for record in records], ["intent"])
                snapshots = list(backups.iterdir())
                self.assertEqual(len(snapshots), 1)
                manifest = hermes_operator.verify_snapshot(snapshots[0])
                self.assertEqual(manifest["record_count"], 1)
                observed.append(records[0]["correlation_id"])
                return 0, "applied\n"

            with (
                mock.patch.object(
                    hermes_operator, "mutation_enabled", return_value=True
                ),
                mock.patch.dict(
                    os.environ,
                    {
                        "VALUES_SITE": "",
                        "HERMES_OPERATOR_MUTATION_ENABLED": "1",
                        "HERMES_OPERATOR_AUDIT_PATH": str(audit),
                        "HERMES_OPERATOR_AUDIT_BACKUP_DIR": str(backups),
                    },
                ),
            ):
                result = hermes_operator.run_action(
                    root, "apply", approve=True, runner=runner
                )

            records = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertEqual(
                [record["phase"] for record in records], ["intent", "completed"]
            )
            self.assertEqual(observed, [result["correlation_id"]])
            self.assertEqual(records[1]["correlation_id"], result["correlation_id"])

    def test_apply_snapshot_failure_is_audited_and_never_invokes_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_safe_plan(root)
            audit = root / "private" / "audit.jsonl"
            runner = mock.Mock()
            with (
                mock.patch.object(
                    hermes_operator, "mutation_enabled", return_value=True
                ),
                mock.patch.dict(
                    os.environ,
                    {
                        "VALUES_SITE": "",
                        "HERMES_OPERATOR_MUTATION_ENABLED": "1",
                        "HERMES_OPERATOR_AUDIT_PATH": str(audit),
                        "HERMES_OPERATOR_AUDIT_BACKUP_DIR": str(root / "backups"),
                    },
                ),
                mock.patch.object(
                    hermes_operator,
                    "create_snapshot",
                    side_effect=hermes_operator.AuditSnapshotError("unavailable"),
                ),
                self.assertRaisesRegex(
                    hermes_operator.OperatorError, "snapshot failed"
                ),
            ):
                hermes_operator.run_action(root, "apply", approve=True, runner=runner)
            runner.assert_not_called()
            records = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertEqual(
                [record["phase"] for record in records], ["intent", "failed"]
            )
            self.assertEqual(records[0]["correlation_id"], records[1]["correlation_id"])

    def test_apply_without_configured_backup_fails_before_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_safe_plan(root)
            runner = mock.Mock()
            with (
                mock.patch.object(
                    hermes_operator, "mutation_enabled", return_value=True
                ),
                mock.patch.dict(
                    os.environ,
                    {
                        "VALUES_SITE": "",
                        "HERMES_OPERATOR_MUTATION_ENABLED": "1",
                        "HERMES_OPERATOR_AUDIT_PATH": str(
                            root / "private" / "audit.jsonl"
                        ),
                        "HERMES_OPERATOR_AUDIT_BACKUP_DIR": "",
                    },
                ),
                self.assertRaisesRegex(
                    hermes_operator.OperatorError, "snapshot failed"
                ),
            ):
                hermes_operator.run_action(root, "apply", approve=True, runner=runner)
            runner.assert_not_called()

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
                            "resource_changes": {
                                "create": 0,
                                "update": 0,
                                "replace": 0,
                                "delete": 0,
                            },
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
                result = hermes_operator.run_action(
                    root, "plan", runner=lambda *_: (0, "ok\n")
                )
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
                runner=lambda *_: (
                    0,
                    "TOKEN=secret-value 192.168.1.5\n",  # public-safety: allow-ip # public-safety: allow-secret
                ),
            )
            self.assertTrue(result["ok"])
            records = [
                json.loads(line)
                for line in (root / ".tmp" / "hermes-operator-audit.jsonl")
                .read_text()
                .splitlines()
            ]
            self.assertEqual(
                [record["phase"] for record in records], ["intent", "completed"]
            )
            self.assertEqual(records[0]["correlation_id"], records[1]["correlation_id"])
            self.assertEqual(records[1]["action"], "validate")
            self.assertNotIn(
                "secret-value",
                (root / ".tmp" / "hermes-operator-audit.jsonl").read_text(),
            )

    def test_audit_records_form_a_mode_restricted_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            previous = os.environ.get("HERMES_OPERATOR_AUDIT_PATH")
            os.environ["HERMES_OPERATOR_AUDIT_PATH"] = str(audit_path)
            try:
                hermes_operator.run_action(
                    root, "validate", runner=lambda *_: (0, "ok\n")
                )
                hermes_operator.run_action(
                    root, "validate", runner=lambda *_: (0, "ok\n")
                )
            finally:
                if previous is None:
                    os.environ.pop("HERMES_OPERATOR_AUDIT_PATH", None)
                else:
                    os.environ["HERMES_OPERATOR_AUDIT_PATH"] = previous
            records = [json.loads(line) for line in audit_path.read_text().splitlines()]
            self.assertEqual(records[0]["previous_hash"], "0" * 64)
            self.assertEqual(records[1]["previous_hash"], records[0]["record_hash"])
            self.assertEqual(stat.S_IMODE(audit_path.stat().st_mode), 0o600)
            self.assertEqual(
                stat.S_IMODE(audit_path.with_suffix(".lock").stat().st_mode), 0o600
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_audit_write_stays_in_held_parent_after_parent_path_is_swapped(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "audit-parent" / "audit.jsonl"
            audit_path.parent.mkdir()
            held_parent = root / "held-parent"
            redirect = root / "redirect"
            redirect.mkdir()
            original_directory_fd = hermes_operator._private_directory_fd

            @hermes_operator.contextlib.contextmanager
            def swap_parent_after_acquire(*args, **kwargs):
                with original_directory_fd(*args, **kwargs) as parent_fd:
                    audit_path.parent.rename(held_parent)
                    audit_path.parent.symlink_to(redirect, target_is_directory=True)
                    yield parent_fd

            with mock.patch.object(
                hermes_operator, "_private_directory_fd", swap_parent_after_acquire
            ), mock.patch.dict(
                os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
            ):
                hermes_operator.write_audit_record(root, "validate", 0, {})

            self.assertTrue(audit_path.parent.is_symlink())
            self.assertTrue((held_parent / "audit.jsonl").is_file())
            self.assertTrue((held_parent / "audit.lock").is_file())
            self.assertFalse((redirect / "audit.jsonl").exists())
            self.assertFalse((redirect / "audit.lock").exists())

    def test_first_lock_creation_syncs_parent_before_flock_when_journal_open_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            audit_path.parent.mkdir()
            events: list[str] = []
            original_open = hermes_operator.os.open
            original_fsync = hermes_operator.os.fsync
            original_flock = hermes_operator.fcntl.flock
            parent_fd: int | None = None
            original_directory_fd = hermes_operator._private_directory_fd

            @hermes_operator.contextlib.contextmanager
            def capture_parent_fd(*args, **kwargs):
                nonlocal parent_fd
                with original_directory_fd(*args, **kwargs) as descriptor:
                    parent_fd = descriptor
                    yield descriptor

            def wrapped_open(name, flags, *args, **kwargs):
                if name == "audit.lock":
                    events.append("lock-open")
                if name == "audit.jsonl":
                    events.append("journal-open")
                    raise OSError("journal open failed")
                return original_open(name, flags, *args, **kwargs)

            def wrapped_fsync(descriptor):
                if descriptor == parent_fd:
                    events.append("parent-fsync")
                return original_fsync(descriptor)

            def wrapped_flock(descriptor, operation):
                if operation == hermes_operator.fcntl.LOCK_EX:
                    events.append("flock")
                return original_flock(descriptor, operation)

            with (
                mock.patch.dict(
                    os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
                ),
                mock.patch.object(
                    hermes_operator, "_private_directory_fd", capture_parent_fd
                ),
                mock.patch.object(hermes_operator.os, "open", side_effect=wrapped_open),
                mock.patch.object(
                    hermes_operator.os, "fsync", side_effect=wrapped_fsync
                ),
                mock.patch.object(
                    hermes_operator.fcntl, "flock", side_effect=wrapped_flock
                ),
                self.assertRaisesRegex(hermes_operator.OperatorError, "append"),
            ):
                hermes_operator.write_audit_record(root, "validate", 0, {})

            self.assertLess(events.index("lock-open"), events.index("parent-fsync"))
            self.assertLess(events.index("parent-fsync"), events.index("flock"))
            self.assertLess(events.index("flock"), events.index("journal-open"))

    def test_first_journal_creation_syncs_parent_before_locked_read_and_append(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            audit_path.parent.mkdir()
            events: list[str] = []
            journal_opens: list[int] = []
            original_open = hermes_operator.os.open
            original_fsync = hermes_operator.os.fsync
            original_flock = hermes_operator.fcntl.flock
            original_reader = hermes_operator.read_audit_stream
            original_write = hermes_operator.os.write
            parent_fd: int | None = None
            journal_fd: int | None = None
            lock_held = False
            original_directory_fd = hermes_operator._private_directory_fd

            @hermes_operator.contextlib.contextmanager
            def capture_parent_fd(*args, **kwargs):
                nonlocal parent_fd
                with original_directory_fd(*args, **kwargs) as descriptor:
                    parent_fd = descriptor
                    yield descriptor

            def wrapped_open(name, flags, *args, **kwargs):
                nonlocal journal_fd
                descriptor = original_open(name, flags, *args, **kwargs)
                if name == "audit.jsonl":
                    journal_opens.append(descriptor)
                    journal_fd = descriptor
                    events.append("journal-open")
                return descriptor

            def wrapped_fsync(descriptor):
                if descriptor == parent_fd:
                    events.append("parent-fsync")
                elif descriptor == journal_fd:
                    events.append("journal-fsync")
                return original_fsync(descriptor)

            def wrapped_flock(descriptor, operation):
                nonlocal lock_held
                if operation == hermes_operator.fcntl.LOCK_EX:
                    lock_held = True
                    events.append("flock")
                elif operation == hermes_operator.fcntl.LOCK_UN:
                    lock_held = False
                return original_flock(descriptor, operation)

            def wrapped_reader(handle):
                self.assertTrue(lock_held)
                assert journal_fd is not None
                self.assertEqual(
                    os.fstat(handle.fileno()).st_ino, os.fstat(journal_fd).st_ino
                )
                events.append("read")
                return original_reader(handle)

            def wrapped_write(descriptor, data):
                self.assertTrue(lock_held)
                self.assertEqual(descriptor, journal_fd)
                events.append("append")
                return original_write(descriptor, data)

            with (
                mock.patch.dict(
                    os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
                ),
                mock.patch.object(
                    hermes_operator, "_private_directory_fd", capture_parent_fd
                ),
                mock.patch.object(hermes_operator.os, "open", side_effect=wrapped_open),
                mock.patch.object(
                    hermes_operator.os, "fsync", side_effect=wrapped_fsync
                ),
                mock.patch.object(
                    hermes_operator.fcntl, "flock", side_effect=wrapped_flock
                ),
                mock.patch.object(
                    hermes_operator, "read_audit_stream", side_effect=wrapped_reader
                ),
                mock.patch.object(
                    hermes_operator.os, "write", side_effect=wrapped_write
                ),
            ):
                hermes_operator.write_audit_record(root, "validate", 0, {})

            self.assertEqual(len(journal_opens), 1)
            journal_created_at = events.index("journal-open")
            parent_synced_at = events.index("parent-fsync", journal_created_at + 1)
            self.assertLess(journal_created_at, parent_synced_at)
            self.assertLess(parent_synced_at, events.index("read"))
            self.assertLess(events.index("read"), events.index("append"))
            self.assertLess(events.index("append"), events.index("journal-fsync"))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_audit_lock_symlink_is_rejected_without_touching_its_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            audit_path.parent.mkdir()
            target = root / "target-lock"
            target.write_text("untouched", encoding="utf-8")
            audit_path.with_suffix(".lock").symlink_to(target)
            previous = os.environ.get("HERMES_OPERATOR_AUDIT_PATH")
            os.environ["HERMES_OPERATOR_AUDIT_PATH"] = str(audit_path)
            try:
                with self.assertRaisesRegex(
                    hermes_operator.OperatorError, "cannot lock"
                ):
                    hermes_operator.run_action(
                        root, "validate", runner=lambda *_: (0, "ok\n")
                    )
            finally:
                if previous is None:
                    os.environ.pop("HERMES_OPERATOR_AUDIT_PATH", None)
                else:
                    os.environ["HERMES_OPERATOR_AUDIT_PATH"] = previous
            self.assertEqual(target.read_text(encoding="utf-8"), "untouched")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_audit_journal_symlink_is_rejected_without_touching_its_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            audit_path.parent.mkdir()
            target = root / "target-journal"
            target.write_text("untouched", encoding="utf-8")
            audit_path.symlink_to(target)
            previous = os.environ.get("HERMES_OPERATOR_AUDIT_PATH")
            os.environ["HERMES_OPERATOR_AUDIT_PATH"] = str(audit_path)
            try:
                with self.assertRaisesRegex(hermes_operator.OperatorError, "append"):
                    hermes_operator.run_action(
                        root, "validate", runner=lambda *_: (0, "ok\n")
                    )
            finally:
                if previous is None:
                    os.environ.pop("HERMES_OPERATOR_AUDIT_PATH", None)
                else:
                    os.environ["HERMES_OPERATOR_AUDIT_PATH"] = previous
            self.assertEqual(target.read_text(encoding="utf-8"), "untouched")

    def test_tampered_audit_journal_fails_closed_before_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / ".tmp" / "hermes-operator-audit.jsonl"
            hermes_operator.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
            audit_path.write_text(
                audit_path.read_text().replace('"ok":true', '"ok":false'),
                encoding="utf-8",
            )
            with self.assertRaises(hermes_operator.OperatorError):
                hermes_operator.run_action(
                    root, "validate", runner=lambda *_: (0, "ok\n")
                )

    def test_audit_verify_returns_only_safe_chain_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hermes_operator.run_action(root, "validate", runner=lambda *_: (0, "ok\n"))
            result = hermes_operator.verify_audit(root)
            self.assertEqual(result["action"], "audit-verify")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(len(result["head_hash"]), 64)
            self.assertNotIn(str(root), json.dumps(result))

    def test_audit_verify_accepts_valid_interleaved_operations(self) -> None:
        first = "a" * 32
        second = "b" * 32
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = root / "private" / "audit.jsonl"
            self.write_hash_valid_audit(
                audit,
                [
                    {"correlation_id": first, "action": "validate"},
                    {"correlation_id": second, "action": "plan"},
                    {
                        "correlation_id": second,
                        "phase": "failed",
                        "action": "plan",
                        "returncode": 7,
                        "ok": False,
                    },
                    {
                        "correlation_id": first,
                        "phase": "completed",
                        "action": "validate",
                        "returncode": 0,
                        "ok": True,
                    },
                ],
            )
            with mock.patch.dict(
                os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit)}
            ):
                result = hermes_operator.verify_audit(root)
            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 4)
            self.assertEqual(result["unresolved_correlations"], [])

    def test_audit_verify_rejects_empty_and_unsupported_actions(self) -> None:
        for action in ("", "status", "VALIDATE"):
            with self.subTest(action=action):
                self.assert_hash_valid_audit_rejected(
                    [{"action": action}], "action is empty or unsupported"
                )

    def test_audit_verify_rejects_intent_with_non_null_result_fields(self) -> None:
        for invalid in ({"returncode": 0}, {"ok": False}):
            with self.subTest(invalid=invalid):
                self.assert_hash_valid_audit_rejected(
                    [invalid], "intent result shape is invalid"
                )

    def test_audit_verify_rejects_invalid_completed_result_shape(self) -> None:
        terminal_base: dict[str, object] = {
            "phase": "completed",
            "returncode": 0,
            "ok": True,
        }
        for invalid in (
            {"returncode": 1, "ok": True},
            {"returncode": 0, "ok": False},
            {"returncode": True, "ok": True},
            {"returncode": "0", "ok": True},
        ):
            with self.subTest(invalid=invalid):
                self.assert_hash_valid_audit_rejected(
                    [{}, terminal_base | invalid], "completed result shape is invalid"
                )

    def test_audit_verify_rejects_invalid_failed_result_shape(self) -> None:
        terminal_base: dict[str, object] = {
            "phase": "failed",
            "returncode": 1,
            "ok": False,
        }
        for invalid in (
            {"returncode": 0, "ok": False},
            {"returncode": 1, "ok": True},
            {"returncode": False, "ok": False},
            {"returncode": None, "ok": False},
        ):
            with self.subTest(invalid=invalid):
                self.assert_hash_valid_audit_rejected(
                    [{}, terminal_base | invalid], "failed result shape is invalid"
                )

    def test_audit_verify_rejects_missing_phase_specific_fields(self) -> None:
        for missing in ("returncode", "ok"):
            with self.subTest(missing=missing):
                self.assert_hash_valid_audit_rejected(
                    [{"_remove": [missing]}], "lifecycle record shape is invalid"
                )

    def test_audit_verify_rejects_invalid_phase_metadata(self) -> None:
        for invalid in (
            {"phase": ""},
            {"phase": "started"},
            {"phase": []},
            {"correlation_id": "A" * 32},
            {"correlation_id": "a" * 31},
        ):
            with self.subTest(invalid=invalid):
                self.assert_hash_valid_audit_rejected(
                    [invalid], "lifecycle metadata is invalid"
                )

    def test_audit_verify_rejects_terminal_before_intent(self) -> None:
        self.assert_hash_valid_audit_rejected(
            [{"phase": "completed", "returncode": 0, "ok": True}],
            "terminal record has no intent",
        )

    def test_audit_verify_rejects_duplicate_terminal(self) -> None:
        terminal = {"phase": "completed", "returncode": 0, "ok": True}
        self.assert_hash_valid_audit_rejected(
            [{}, terminal, terminal], "duplicate terminal records"
        )

    def test_audit_verify_rejects_reused_correlation_id(self) -> None:
        self.assert_hash_valid_audit_rejected(
            [
                {},
                {"phase": "completed", "returncode": 0, "ok": True},
                {},
            ],
            "correlation is reused",
        )

    def test_audit_verify_rejects_action_change_within_lifecycle(self) -> None:
        self.assert_hash_valid_audit_rejected(
            [
                {},
                {
                    "phase": "completed",
                    "action": "plan",
                    "returncode": 0,
                    "ok": True,
                },
            ],
            "lifecycle action changed",
        )

    def test_dangling_intent_fails_explicit_verify_but_allows_terminal_append(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = root / "private" / "audit.jsonl"
            correlation = "c" * 32
            with mock.patch.dict(
                os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit)}
            ):
                hermes_operator.write_audit_record(
                    root,
                    "validate",
                    None,
                    {},
                    phase="intent",
                    correlation_id=correlation,
                )
                self.assertEqual(hermes_operator.read_audit_chain(audit)[1], 1)
                unresolved = hermes_operator.verify_audit(root)
                self.assertFalse(unresolved["ok"])
                self.assertEqual(unresolved["unresolved_correlations"], [correlation])
                hermes_operator.write_audit_record(
                    root,
                    "validate",
                    0,
                    {},
                    phase="completed",
                    correlation_id=correlation,
                )
                resolved = hermes_operator.verify_audit(root)
            self.assertTrue(resolved["ok"])

    def test_audit_verify_fails_closed_when_journal_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(
            hermes_operator.OperatorError, "audit journal is unavailable"
        ), mock.patch.object(
            Path,
            "exists",
            side_effect=AssertionError("audit verification must not precheck"),
        ):
            hermes_operator.verify_audit(Path(temp))

    def test_chain_allows_first_write_missing_journal_without_a_path_precheck(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            Path, "exists", side_effect=AssertionError("chain reads must open directly")
        ):
            self.assertEqual(
                hermes_operator.read_audit_chain(
                    Path(temp) / "missing.jsonl", allow_missing=True
                ),
                ("0" * 64, 0),
            )

    def test_writer_uses_one_held_parent_and_exact_fd_boundary_order(self) -> None:
        """Record real syscall arguments/FD identities without replacing I/O."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            audit_path.parent.mkdir()
            events: list[tuple[str, int]] = []
            opens: list[tuple[str, int, int | None, tuple[int, int]]] = []
            chmods: list[tuple[int, int, tuple[int, int]]] = []
            parent_fd: int | None = None
            parent_identity: tuple[int, int] | None = None
            lock_fd: int | None = None
            journal_fd: int | None = None
            reader_dup_fd: int | None = None
            original_directory_fd = hermes_operator._private_directory_fd
            original_open = hermes_operator.os.open
            original_fchmod = hermes_operator.os.fchmod
            original_fsync = hermes_operator.os.fsync
            original_flock = hermes_operator.fcntl.flock
            original_reader = hermes_operator.read_audit_stream
            original_write = hermes_operator.os.write
            original_dup = hermes_operator.os.dup

            @hermes_operator.contextlib.contextmanager
            def capture_parent(*args, **kwargs):
                nonlocal parent_fd, parent_identity
                with original_directory_fd(*args, **kwargs) as descriptor:
                    parent_fd = descriptor
                    parent_identity = (
                        os.fstat(descriptor).st_dev,
                        os.fstat(descriptor).st_ino,
                    )
                    yield descriptor

            def wrapped_open(name, flags, *args, **kwargs):
                nonlocal lock_fd, journal_fd
                descriptor = original_open(name, flags, *args, **kwargs)
                if name in {"audit.lock", "audit.jsonl"}:
                    assert parent_identity is not None
                    self.assertEqual(
                        (
                            os.fstat(kwargs["dir_fd"]).st_dev,
                            os.fstat(kwargs["dir_fd"]).st_ino,
                        ),
                        parent_identity,
                    )
                    identity = (
                        os.fstat(descriptor).st_dev,
                        os.fstat(descriptor).st_ino,
                    )
                    opens.append((name, flags, kwargs.get("dir_fd"), identity))
                    events.append((f"{name}-open", descriptor))
                    if name == "audit.lock":
                        lock_fd = descriptor
                    else:
                        journal_fd = descriptor
                return descriptor

            def wrapped_fchmod(descriptor, mode):
                if descriptor in {lock_fd, journal_fd}:
                    assert descriptor is not None
                    chmods.append(
                        (
                            descriptor,
                            mode,
                            (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino),
                        )
                    )
                    events.append(("fchmod", descriptor))
                return original_fchmod(descriptor, mode)

            def wrapped_fsync(descriptor):
                events.append(
                    (
                        "parent-fsync" if descriptor == parent_fd else "file-fsync",
                        descriptor,
                    )
                )
                return original_fsync(descriptor)

            def wrapped_flock(descriptor, operation):
                events.append(
                    (
                        (
                            "flock-ex"
                            if operation == hermes_operator.fcntl.LOCK_EX
                            else "flock-un"
                        ),
                        descriptor,
                    )
                )
                return original_flock(descriptor, operation)

            def wrapped_reader(handle):
                assert journal_fd is not None and reader_dup_fd is not None
                self.assertEqual(handle.fileno(), reader_dup_fd)
                self.assertEqual(
                    (
                        os.fstat(handle.fileno()).st_dev,
                        os.fstat(handle.fileno()).st_ino,
                    ),
                    (os.fstat(journal_fd).st_dev, os.fstat(journal_fd).st_ino),
                )
                events.append(("chain-read", handle.fileno()))
                return original_reader(handle)

            def wrapped_dup(descriptor):
                nonlocal reader_dup_fd
                duplicate = original_dup(descriptor)
                if descriptor == journal_fd:
                    reader_dup_fd = duplicate
                    events.append(("journal-dup", duplicate))
                return duplicate

            def wrapped_write(descriptor, data):
                self.assertEqual(descriptor, journal_fd)
                events.append(("append", descriptor))
                return original_write(descriptor, data)

            with (
                mock.patch.dict(
                    os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
                ),
                mock.patch.object(
                    hermes_operator, "_private_directory_fd", capture_parent
                ),
                mock.patch.object(hermes_operator.os, "open", side_effect=wrapped_open),
                mock.patch.object(
                    hermes_operator.os, "fchmod", side_effect=wrapped_fchmod
                ),
                mock.patch.object(
                    hermes_operator.os, "fsync", side_effect=wrapped_fsync
                ),
                mock.patch.object(
                    hermes_operator.fcntl, "flock", side_effect=wrapped_flock
                ),
                mock.patch.object(
                    hermes_operator, "read_audit_stream", side_effect=wrapped_reader
                ),
                mock.patch.object(hermes_operator.os, "dup", side_effect=wrapped_dup),
                mock.patch.object(
                    hermes_operator.os, "write", side_effect=wrapped_write
                ),
            ):
                hermes_operator.write_audit_record(root, "validate", 0, {})

            assert (
                parent_fd is not None
                and parent_identity is not None
                and lock_fd is not None
                and journal_fd is not None
                and reader_dup_fd is not None
            )
            required = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            lock_open = next(entry for entry in opens if entry[0] == "audit.lock")
            journal_open = next(entry for entry in opens if entry[0] == "audit.jsonl")
            self.assertEqual(lock_open[2], parent_fd)
            self.assertEqual(journal_open[2], parent_fd)
            self.assertEqual(lock_open[1] & required, required)
            self.assertEqual(
                journal_open[1] & (required | os.O_APPEND), required | os.O_APPEND
            )
            self.assertEqual(
                lock_open[1] & (os.O_CREAT | os.O_EXCL), os.O_CREAT | os.O_EXCL
            )
            self.assertEqual(
                journal_open[1] & (os.O_CREAT | os.O_EXCL), os.O_CREAT | os.O_EXCL
            )
            self.assertEqual({mode for _, mode, _ in chmods}, {0o600})
            self.assertEqual(
                {identity for _, _, identity in chmods}, {lock_open[3], journal_open[3]}
            )
            names = [name for name, _ in events]
            self.assertLess(names.index("audit.lock-open"), names.index("parent-fsync"))
            self.assertLess(names.index("parent-fsync"), names.index("flock-ex"))
            self.assertLess(names.index("flock-ex"), names.index("audit.jsonl-open"))
            self.assertLess(names.index("audit.jsonl-open"), names.index("chain-read"))
            self.assertLess(names.index("journal-dup"), names.index("chain-read"))
            self.assertLess(
                names.index("audit.jsonl-open"),
                names.index("parent-fsync", names.index("audit.jsonl-open") + 1),
            )
            self.assertLess(
                names.index("parent-fsync", names.index("audit.jsonl-open") + 1),
                names.index("chain-read"),
            )
            self.assertLess(names.index("chain-read"), names.index("append"))
            self.assertLess(names.index("append"), names.index("file-fsync"))
            self.assertLess(names.index("file-fsync"), names.index("flock-un"))

    def test_concurrent_first_writers_create_one_complete_valid_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            audit_path.parent.mkdir()
            workers = 12
            barrier = threading.Barrier(workers)
            errors: list[Exception] = []

            def writer() -> None:
                try:
                    barrier.wait(timeout=5)
                    hermes_operator.write_audit_record(root, "validate", 0, {})
                except (
                    threading.BrokenBarrierError,
                    hermes_operator.OperatorError,
                ) as error:
                    errors.append(error)

            with mock.patch.dict(
                os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
            ):
                threads = [threading.Thread(target=writer) for _ in range(workers)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=10)
            self.assertFalse([thread for thread in threads if thread.is_alive()])
            self.assertEqual(errors, [])
            head, count = hermes_operator.read_audit_chain(audit_path)
            self.assertEqual(count, workers)
            self.assertEqual(len(head), 64)
            self.assertEqual(
                len(audit_path.read_text(encoding="utf-8").splitlines()), workers
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_lock_and_journal_reject_ancestor_symlink_substitution(self) -> None:
        for victim_name in ("audit.lock", "audit.jsonl"):
            with self.subTest(
                victim_name=victim_name
            ), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                ancestor = root / "base" / "ancestor"
                original_parent = ancestor / "private"
                original_parent.mkdir(parents=True)
                audit_path = original_parent / "audit.jsonl"
                attacker = root / "attacker"
                attacker_parent = attacker / "private"
                attacker_parent.mkdir(parents=True)
                target = attacker_parent / victim_name
                target.write_text("untouched", encoding="utf-8")
                original_directory_fd = hermes_operator._private_directory_fd

                @hermes_operator.contextlib.contextmanager
                def substitute_after_hold(
                    *args,
                    original_directory_fd=original_directory_fd,
                    ancestor=ancestor,
                    root=root,
                    attacker=attacker,
                    **kwargs,
                ):
                    with original_directory_fd(*args, **kwargs) as descriptor:
                        ancestor.rename(root / "held-ancestor")
                        ancestor.symlink_to(attacker, target_is_directory=True)
                        yield descriptor

                with (
                    mock.patch.dict(
                        os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
                    ),
                    mock.patch.object(
                        hermes_operator, "_private_directory_fd", substitute_after_hold
                    ),
                ):
                    hermes_operator.write_audit_record(root, "validate", 0, {})
                held = root / "held-ancestor" / "private"
                self.assertTrue((held / "audit.lock").is_file())
                self.assertTrue((held / "audit.jsonl").is_file())
                self.assertEqual(target.read_text(encoding="utf-8"), "untouched")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_race_created_lock_or_journal_symlink_is_never_followed(self) -> None:
        """A final-entry symlink introduced between create and fallback is rejected."""
        for victim_name in ("audit.lock", "audit.jsonl"):
            with self.subTest(
                victim_name=victim_name
            ), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                audit_path = root / "private" / "audit.jsonl"
                audit_path.parent.mkdir()
                sentinel = root / "attacker-sentinel"
                sentinel.write_text("untouched", encoding="utf-8")
                original_open = hermes_operator.os.open
                raced = False

                def create_symlink_before_fallback(
                    name,
                    flags,
                    *args,
                    victim_name=victim_name,
                    audit_path=audit_path,
                    sentinel=sentinel,
                    original_open=original_open,
                    **kwargs,
                ):
                    nonlocal raced
                    if (
                        name == victim_name
                        and flags & os.O_CREAT
                        and flags & os.O_EXCL
                        and not raced
                    ):
                        raced = True
                        (audit_path.parent / victim_name).symlink_to(sentinel)
                    return original_open(name, flags, *args, **kwargs)

                with (
                    mock.patch.dict(
                        os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
                    ),
                    mock.patch.object(
                        hermes_operator.os,
                        "open",
                        side_effect=create_symlink_before_fallback,
                    ),
                    self.assertRaises(hermes_operator.OperatorError),
                ):
                    hermes_operator.write_audit_record(root, "validate", 0, {})
                self.assertTrue(raced)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "untouched")

    def test_malformed_or_tampered_history_never_changes_bytes_before_append(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "private" / "audit.jsonl"
            audit_path.parent.mkdir()
            with mock.patch.dict(
                os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
            ):
                for contents in ("not-json\n", '{"previous_hash":"0"}\n'):
                    with self.subTest(contents=contents):
                        audit_path.write_text(contents, encoding="utf-8")
                        before = audit_path.read_bytes()
                        with self.assertRaisesRegex(
                            hermes_operator.OperatorError, "append"
                        ):
                            hermes_operator.write_audit_record(root, "validate", 0, {})
                        self.assertEqual(audit_path.read_bytes(), before)
                        with self.assertRaises(hermes_operator.OperatorError):
                            hermes_operator.verify_audit(root)

    def test_first_normal_action_creates_chain_while_recovery_verify_requires_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path = root / "fresh" / "audit.jsonl"
            with mock.patch.dict(
                os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit_path)}
            ):
                with self.assertRaisesRegex(
                    hermes_operator.OperatorError, "unavailable"
                ):
                    hermes_operator.verify_audit(root)
                result = hermes_operator.run_action(
                    root, "validate", runner=lambda *_: (0, "normal action")
                )
                self.assertTrue(result["ok"])
                verified = hermes_operator.verify_audit(root)
            self.assertEqual(verified["record_count"], 2)
            self.assertTrue(audit_path.is_file())

    def test_status_is_machine_readable_and_does_not_include_private_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra").mkdir()
            (root / "infra" / "services.json").write_text(
                json.dumps(
                    {"default_services": ["hermes"], "services": {"hermes": {}}}
                ),
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

    def test_plan_summary_rejects_non_count_data_before_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = (
                (
                    "extra key",
                    lambda summary: summary["resource_changes"].update(
                        {"private": {"token": "SECRET_SENTINEL_DO_NOT_PRINT"}}
                    ),
                ),
                (
                    "string count",
                    lambda summary: summary["resource_changes"].update({"create": "1"}),
                ),
                (
                    "negative count",
                    lambda summary: summary["resource_changes"].update({"delete": -1}),
                ),
                (
                    "boolean count",
                    lambda summary: summary["resource_changes"].update(
                        {"update": True}
                    ),
                ),
                (
                    "private target",
                    lambda summary: summary.update(
                        {"stateful_targets": ["private.example.internal"]}
                    ),
                ),
            )
            for label, mutate in cases:
                with self.subTest(label=label):
                    self.write_safe_plan(root)
                    path = root / "tfplan.meta.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    mutate(payload["summary"])
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(
                        hermes_operator.OperatorError, "unsafe"
                    ):
                        hermes_operator.load_plan_summary(root)
            self.assertFalse((root / ".tmp").exists())

    def test_post_runner_metadata_failure_gets_correlated_terminal_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_safe_plan(root)

            def corrupting_runner(*_):
                (root / "tfplan.meta.json").write_text(
                    '{"schema_version": 7, "summary": {"resource_changes": "bad"}}',
                    encoding="utf-8",
                )
                return 0, "plan complete"

            with self.assertRaises(hermes_operator.OperatorError) as caught:
                hermes_operator.run_action(root, "plan", runner=corrupting_runner)
            records = [
                json.loads(line)
                for line in (root / ".tmp" / "hermes-operator-audit.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [record["phase"] for record in records], ["intent", "failed"]
            )
            self.assertEqual(records[0]["correlation_id"], records[1]["correlation_id"])
            self.assertEqual(
                caught.exception.correlation_id, records[0]["correlation_id"]
            )

    def test_invalid_runner_result_gets_correlated_terminal_record(self) -> None:
        for invalid in ((0,), ("zero", "output"), (0, b"bytes")):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                with self.assertRaises(hermes_operator.OperatorError) as caught:
                    hermes_operator.run_action(
                        root, "validate", runner=lambda *_: invalid
                    )
                records = [
                    json.loads(line)
                    for line in (root / ".tmp" / "hermes-operator-audit.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                self.assertEqual(
                    [record["phase"] for record in records], ["intent", "failed"]
                )
                self.assertEqual(
                    caught.exception.correlation_id, records[0]["correlation_id"]
                )
                self.assertEqual(
                    records[0]["correlation_id"], records[1]["correlation_id"]
                )

    def test_audit_verification_reports_orphan_and_rejects_impossible_lifecycle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = root / "private" / "audit.jsonl"
            correlation = "a" * 32
            with mock.patch.dict(
                os.environ, {"HERMES_OPERATOR_AUDIT_PATH": str(audit)}
            ):
                hermes_operator.write_audit_record(
                    root,
                    "validate",
                    None,
                    {},
                    phase="intent",
                    correlation_id=correlation,
                )
                unresolved = hermes_operator.verify_audit(root)
                self.assertFalse(unresolved["ok"])
                self.assertEqual(unresolved["unresolved_correlations"], [correlation])
                hermes_operator.write_audit_record(
                    root,
                    "validate",
                    0,
                    {},
                    phase="completed",
                    correlation_id=correlation,
                )
                hermes_operator.write_audit_record(
                    root,
                    "validate",
                    1,
                    {},
                    phase="failed",
                    correlation_id=correlation,
                )
                with self.assertRaisesRegex(
                    hermes_operator.OperatorError, "duplicate terminal"
                ):
                    hermes_operator.verify_audit(root)

    def test_json_cli_errors_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stream = io.StringIO()
            with redirect_stdout(stream):
                returncode = hermes_operator.main(["status", "--repo", temp, "--json"])
            self.assertEqual(returncode, 1)
            payload = json.loads(stream.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "operator_error")
            self.assertIsInstance(payload["error"]["message"], str)


if __name__ == "__main__":
    unittest.main()

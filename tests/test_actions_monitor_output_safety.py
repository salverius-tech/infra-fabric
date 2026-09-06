from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "forgejo-actions-monitor.py"
SPEC = importlib.util.spec_from_file_location("forgejo_actions_monitor_output", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)

SENTINELS = (
    "https://forgejo.private.example/runs/9",
    "192.168.44.9",  # public-safety: allow-ip
    "2001:db8:feed::9",  # public-safety: allow-ip
    "operator@private.example",
    "TOKEN=ghp_super_private_token",  # public-safety: allow-secret
    "PRIVATE-INVENTORY-SENTINEL",
)


def assert_sentinels_absent(test: unittest.TestCase, output: str) -> None:
    for sentinel in SENTINELS:
        test.assertNotIn(sentinel, output)


class ActionsMonitorOutputSafetyTests(unittest.TestCase):
    def hostile_status_row(self) -> dict[str, object]:
        hostile = " ".join(SENTINELS)
        return {
            "id": 9,
            "status": 6,
            "event": hostile,
            "workflow_id": hostile,
            "created": hostile,
            "updated": hostile,
            "job_name": hostile,
            "job_status": 1,
            "task_id": hostile,
            "started": hostile,
            "stopped": hostile,
            "unexpected": hostile,
        }

    def hostile_runner_row(self) -> dict[str, object]:
        hostile = " ".join(SENTINELS)
        return {
            "id": 4,
            "name": hostile,
            "owner_id": 3,
            "repo_id": 0,
            "last_online": hostile,
            "last_active": hostile,
            "agent_labels": json.dumps(list(SENTINELS)),
            "unexpected": hostile,
        }

    def capture_status(self, as_json: bool) -> str:
        stream = io.StringIO()
        with (
            patch.object(
                monitor, "latest_runs", return_value=[self.hostile_status_row()]
            ),
            contextlib.redirect_stdout(stream),
        ):
            monitor.print_status(10, as_json)
        return stream.getvalue()

    def capture_runners(self, as_json: bool) -> str:
        stream = io.StringIO()
        with (
            patch.object(
                monitor, "forgejo_sql", return_value=[self.hostile_runner_row()]
            ),
            patch.object(
                monitor, "run_ansible_shell", return_value=" ".join(SENTINELS)
            ),
            contextlib.redirect_stdout(stream),
        ):
            monitor.print_runners(as_json)
        return stream.getvalue()

    def test_status_text_and_json_use_only_the_bounded_safe_schema(self) -> None:
        for as_json in (False, True):
            with self.subTest(as_json=as_json):
                output = self.capture_status(as_json)
                assert_sentinels_absent(self, output)
                self.assertLess(len(output), 2_000)
                self.assertNotIn("workflow_id", output)
                self.assertNotIn("job_name", output)
                if as_json:
                    payload = json.loads(output)
                    self.assertEqual(
                        set(payload),
                        {"schema_version", "kind", "runs", "truncated"},
                    )
                    self.assertEqual(
                        set(payload["runs"][0]),
                        {"run_id", "status", "event", "age", "duration", "job_status"},
                    )
                    self.assertEqual(payload["runs"][0]["event"], "unknown")

    def test_runner_text_and_json_use_only_the_bounded_safe_schema(self) -> None:
        for as_json in (False, True):
            with self.subTest(as_json=as_json):
                output = self.capture_runners(as_json)
                assert_sentinels_absent(self, output)
                self.assertLess(len(output), 2_000)
                self.assertNotIn("agent_labels", output)
                self.assertNotIn("name", output)
                if as_json:
                    payload = json.loads(output)
                    self.assertEqual(
                        set(payload),
                        {
                            "schema_version",
                            "kind",
                            "service",
                            "runners",
                            "truncated",
                        },
                    )
                    self.assertEqual(
                        set(payload["runners"][0]),
                        {"runner_id", "scope", "last_seen", "label_count"},
                    )
                    self.assertEqual(payload["service"], "unknown")

    def test_payload_cardinality_is_bounded_even_with_mocked_excess_rows(self) -> None:
        status = monitor.status_payload(
            [self.hostile_status_row() for _ in range(monitor.MAX_STATUS_ROWS + 20)],
            10_000,
        )
        runners = monitor.runners_payload(
            [self.hostile_runner_row() for _ in range(monitor.MAX_RUNNERS + 20)],
            SENTINELS[0],
        )
        self.assertEqual(len(status["runs"]), monitor.MAX_STATUS_ROWS)
        self.assertEqual(len(runners["runners"]), monitor.MAX_RUNNERS)
        self.assertTrue(status["truncated"])
        self.assertTrue(runners["truncated"])
        assert_sentinels_absent(
            self, json.dumps({"status": status, "runners": runners})
        )

    def test_watch_does_not_emit_raw_job_or_workflow_fields(self) -> None:
        stream = io.StringIO()
        with (
            patch.object(monitor, "run_id_or_latest", return_value=9),
            patch.object(
                monitor,
                "run_state",
                return_value={**self.hostile_status_row(), "status": 1},
            ),
            contextlib.redirect_stdout(stream),
        ):
            self.assertEqual(monitor.watch("latest", 1, 1), 0)
        assert_sentinels_absent(self, stream.getvalue())
        self.assertLess(len(stream.getvalue()), 200)

    def test_remote_command_failures_never_replay_private_output(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["ansible"],
            returncode=1,
            stdout=" ".join(SENTINELS),
            stderr=" ".join(reversed(SENTINELS)),
        )
        with patch.object(monitor.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(
                monitor.MonitorError, "command failed"
            ) as raised:
                monitor.run_ansible_shell("safe-test-command")
        assert_sentinels_absent(self, str(raised.exception))

    def test_logs_are_content_free_by_default_and_raw_only_when_explicit(self) -> None:
        hostile = "\n".join(SENTINELS)
        with patch.object(monitor, "run_ansible_shell", return_value=hostile):
            safe_output = io.StringIO()
            with contextlib.redirect_stdout(safe_output):
                monitor.print_logs("9", 200, False)
            assert_sentinels_absent(self, safe_output.getvalue())
            self.assertLess(len(safe_output.getvalue()), 100)

            unsafe_output = io.StringIO()
            with contextlib.redirect_stdout(unsafe_output):
                monitor.print_logs("9", 200, True)
            self.assertEqual(unsafe_output.getvalue().strip(), hostile)

    def test_hermes_adapter_cannot_dispatch_the_direct_unsafe_log_flag(self) -> None:
        adapter = (
            ROOT
            / "infra"
            / "ansible"
            / "roles"
            / "hermes"
            / "files"
            / "homelab-infra-operator"
            / "__init__.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("forgejo-actions-monitor", adapter)
        self.assertNotIn("unsafe-no-redact", adapter)
        self.assertIn(
            '_ACTIONS = ("status", "audit-verify", "validate", "plan")', adapter
        )


if __name__ == "__main__":
    unittest.main()

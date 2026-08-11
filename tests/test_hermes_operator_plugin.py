from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = (
    ROOT
    / "infra"
    / "ansible"
    / "roles"
    / "hermes"
    / "files"
    / "homelab-infra-operator"
    / "__init__.py"
)
DASHBOARD_API = PLUGIN.parent / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("homelab_infra_operator_plugin", PLUGIN)
assert spec and spec.loader
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


class FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FakeRouter:
    def get(self, _path: str):
        return lambda function: function

    def post(self, _path: str):
        return lambda function: function


fake_fastapi = types.ModuleType("fastapi")
setattr(fake_fastapi, "APIRouter", FakeRouter)
setattr(fake_fastapi, "HTTPException", FakeHTTPException)
setattr(fake_fastapi, "Request", object)

dashboard_spec = importlib.util.spec_from_file_location(
    "homelab_infra_operator_dashboard_api", DASHBOARD_API
)
assert dashboard_spec and dashboard_spec.loader
dashboard = importlib.util.module_from_spec(dashboard_spec)
with patch.dict(sys.modules, {"fastapi": fake_fastapi}):
    dashboard_spec.loader.exec_module(dashboard)


class FakeRequest:
    def __init__(self, body: object) -> None:
        self.body = body

    async def json(self) -> object:
        return self.body


class FakeContext:
    def __init__(self) -> None:
        self.tools: list[dict[str, object]] = []
        self.commands: list[dict[str, object]] = []

    def register_tool(self, **kwargs: object) -> None:
        self.tools.append(kwargs)

    def register_command(self, **kwargs: object) -> None:
        self.commands.append(kwargs)


class HermesOperatorPluginTests(unittest.TestCase):
    def test_registers_read_only_tool_without_apply_by_default(self) -> None:
        context = FakeContext()
        with patch.dict(os.environ, {}, clear=True):
            plugin.register(context)

        self.assertEqual(
            [tool["name"] for tool in context.tools], ["homelab_infra_operator"]
        )
        schema = context.tools[0]["schema"]
        assert isinstance(schema, dict)
        self.assertEqual(
            schema["parameters"]["properties"]["action"]["enum"],
            ["status", "validate", "plan"],
        )
        self.assertEqual(context.commands, [])

    def test_explicit_activation_registers_separate_apply_command(self) -> None:
        context = FakeContext()
        with patch.dict(
            os.environ, {"HERMES_OPERATOR_MUTATION_ENABLED": "1"}, clear=True
        ):
            plugin.register(context)
        self.assertEqual(
            [command["name"] for command in context.commands], ["infra-apply"]
        )

    def test_tool_handler_dispatches_action_without_apply_arguments(self) -> None:
        context = FakeContext()
        plugin.register(context)
        handler = cast(object, context.tools[0]["handler"])
        assert callable(handler)

        with patch.object(
            plugin, "_run", return_value=json.dumps({"action": "status", "ok": True})
        ) as run:
            result = cast(str, handler({"action": "status"}))

        self.assertEqual(json.loads(result)["action"], "status")
        run.assert_called_once_with("status")

    def test_apply_command_requires_only_explicit_approved_flags(self) -> None:
        context = FakeContext()
        with patch.dict(
            os.environ, {"HERMES_OPERATOR_MUTATION_ENABLED": "1"}, clear=True
        ):
            plugin.register(context)
        handler = cast(object, context.commands[0]["handler"])
        assert callable(handler)

        with patch.object(
            plugin, "_run", return_value=json.dumps({"action": "apply", "ok": True})
        ) as run:
            result = cast(str, handler("--allow-stateful-batch"))

        self.assertTrue(json.loads(result)["ok"])
        run.assert_called_once_with("apply", ("--approve", "--allow-stateful-batch"))
        self.assertIn("unsupported apply argument", cast(str, handler("--unexpected")))

    def test_disabled_direct_apply_dispatch_fails_before_subprocess(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(plugin.subprocess, "run") as run,
        ):
            result = json.loads(plugin._run("apply", ("--approve",)))
        self.assertFalse(result["ok"])
        self.assertIn("not activated", result["error"])
        run.assert_not_called()

    def test_dashboard_apply_is_fail_closed_until_activated(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(dashboard.HTTPException) as context:
                asyncio.run(dashboard.apply(FakeRequest({"confirm": "APPLY"})))
        self.assertEqual(context.exception.status_code, 404)

    def test_dashboard_apply_still_requires_confirmation_after_activation(self) -> None:
        with patch.dict(
            os.environ, {"HERMES_OPERATOR_MUTATION_ENABLED": "1"}, clear=True
        ):
            with self.assertRaises(dashboard.HTTPException) as context:
                asyncio.run(dashboard.apply(FakeRequest({})))
        self.assertEqual(context.exception.status_code, 400)

        with (
            patch.dict(
                os.environ, {"HERMES_OPERATOR_MUTATION_ENABLED": "1"}, clear=True
            ),
            patch.object(dashboard, "_bridge", return_value={"ok": True}) as bridge,
        ):
            result = asyncio.run(
                dashboard.apply(
                    FakeRequest({"confirm": "APPLY", "allow_destructive": True})
                )
            )
        self.assertTrue(result["ok"])
        bridge.assert_called_once_with("apply", "--approve", "--allow-destructive")


if __name__ == "__main__":
    unittest.main()

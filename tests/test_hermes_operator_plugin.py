from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "infra" / "ansible" / "roles" / "hermes" / "files" / "homelab-infra-operator" / "__init__.py"
spec = importlib.util.spec_from_file_location("homelab_infra_operator_plugin", PLUGIN)
assert spec and spec.loader
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


class FakeContext:
    def __init__(self) -> None:
        self.tools: list[dict[str, object]] = []
        self.commands: list[dict[str, object]] = []

    def register_tool(self, **kwargs: object) -> None:
        self.tools.append(kwargs)

    def register_command(self, **kwargs: object) -> None:
        self.commands.append(kwargs)


class HermesOperatorPluginTests(unittest.TestCase):
    def test_registers_read_only_tool_and_separate_apply_command(self) -> None:
        context = FakeContext()
        plugin.register(context)

        self.assertEqual([tool["name"] for tool in context.tools], ["homelab_infra_operator"])
        schema = context.tools[0]["schema"]
        assert isinstance(schema, dict)
        self.assertEqual(schema["parameters"]["properties"]["action"]["enum"], ["status", "validate", "plan"])
        self.assertEqual([command["name"] for command in context.commands], ["infra-apply"])

    def test_tool_handler_dispatches_action_without_apply_arguments(self) -> None:
        context = FakeContext()
        plugin.register(context)
        handler = cast(object, context.tools[0]["handler"])
        assert callable(handler)

        with patch.object(plugin, "_run", return_value=json.dumps({"action": "status", "ok": True})) as run:
            result = cast(str, handler({"action": "status"}))

        self.assertEqual(json.loads(result)["action"], "status")
        run.assert_called_once_with("status")

    def test_apply_command_requires_only_explicit_approved_flags(self) -> None:
        context = FakeContext()
        plugin.register(context)
        handler = cast(object, context.commands[0]["handler"])
        assert callable(handler)

        with patch.object(plugin, "_run", return_value=json.dumps({"action": "apply", "ok": True})) as run:
            result = cast(str, handler("--allow-stateful-batch"))

        self.assertTrue(json.loads(result)["ok"])
        run.assert_called_once_with("apply", ("--approve", "--allow-stateful-batch"))
        self.assertIn("unsupported apply argument", cast(str, handler("--unexpected")))


if __name__ == "__main__":
    unittest.main()

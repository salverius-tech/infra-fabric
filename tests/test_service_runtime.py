from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

try:
    import hcl2  # noqa: F401
except ImportError:
    hcl2_stub = types.ModuleType("hcl2")
    hcl2_stub.load = lambda _file: {}
    sys.modules.setdefault("hcl2", hcl2_stub)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "service-runtime.py"
spec = importlib.util.spec_from_file_location("service_runtime", SCRIPT)
assert spec and spec.loader
service_runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service_runtime
spec.loader.exec_module(service_runtime)


class ServiceRuntimeTests(unittest.TestCase):
    def test_defaults_to_lxc_for_service_guests(self) -> None:
        self.assertEqual(service_runtime.runtime_type("hermes", {}), "lxc")

    def test_partial_shared_runtime_uses_the_catalog_default_type(self) -> None:
        self.assertEqual(
            service_runtime.runtime_type("forgejo", {"service_runtime": {"forgejo": {"cloud_init_user": "forgejo"}}}),
            "lxc",
        )

    def test_onramp_host_defaults_to_vm(self) -> None:
        self.assertEqual(service_runtime.runtime_type("onramp_host", {}), "vm")

    def test_shared_runtime_map_takes_precedence(self) -> None:
        self.assertEqual(
            service_runtime.runtime_type("forgejo", {"service_runtime": {"forgejo": {"type": "vm"}}}),
            "vm",
        )

    def test_retired_runtime_alias_is_rejected(self) -> None:
        with self.assertRaisesRegex(service_runtime.ServiceRuntimeError, "retired runtime alias is not accepted"):
            service_runtime.runtime_type("forgejo", {"forgejo_runtime": {"type": "vm"}})

    def test_rejects_unknown_runtime(self) -> None:
        with self.assertRaises(service_runtime.ServiceRuntimeError):
            service_runtime.runtime_type("hermes", {"service_runtime": {"hermes": {"type": "baremetal"}}})

    def test_main_accepts_canonical_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            projection = Path(temp) / "terraform.auto.tfvars.json"
            projection.write_text(
                json.dumps(
                    {
                        "enabled_services": ["forgejo"],
                        "service_runtime": {"forgejo": {"type": "vm"}},
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = service_runtime.main(["forgejo", "--projection", str(projection)])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), "vm")


if __name__ == "__main__":
    unittest.main()

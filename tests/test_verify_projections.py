from __future__ import annotations

import contextlib
import io
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from canonical_projections import ProjectionError, _assert_non_secret

_SPEC = importlib.util.spec_from_file_location(
    "verify_projections", Path(__file__).resolve().parents[1] / "scripts" / "verify-projections.py"
)
assert _SPEC is not None and _SPEC.loader is not None
verify_projections = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_projections)


class VerifyProjectionsTests(unittest.TestCase):
    def test_security_policy_booleans_are_not_secret_values(self) -> None:
        _assert_non_secret({"allow_passwordless_sudo": True, "password_authentication": False})
        with self.assertRaisesRegex(ProjectionError, "api_token"):
            _assert_non_secret({"api_token": "sentinel"})

    def test_projection_identity_failure_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site_file = root / "site.yaml"
            generated = root / "generated"
            generated.mkdir()
            site_file.write_text("placeholder: true\n", encoding="utf-8")
            for name in verify_projections.PROJECTION_FILES:
                (generated / name).write_text("{}\n", encoding="utf-8")
            (generated / "manifest.json").write_text("{}\n", encoding="utf-8")
            error_output = io.StringIO()
            with (
                patch.object(verify_projections, "load_site", return_value=SimpleNamespace(site=SimpleNamespace(name="dev"))),
                patch.object(verify_projections, "load_catalog"),
                patch.object(verify_projections, "verify_projection_permissions"),
                patch.object(verify_projections, "verify_manifest"),
                patch.object(
                    verify_projections,
                    "verify_cross_projection_identity",
                    side_effect=ProjectionError("service identity sets disagree across projections"),
                ),
                contextlib.redirect_stderr(error_output),
            ):
                result = verify_projections.main(["--site-file", str(site_file), "--generated-dir", str(generated)])
            self.assertEqual(result, 1)
            self.assertIn("service identity sets disagree across projections", error_output.getvalue())
            self.assertNotIn("Traceback", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()

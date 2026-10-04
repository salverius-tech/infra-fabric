from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location(
    "canonical_provider_env", SCRIPTS / "canonical-provider-env.py"
)
assert spec is not None and spec.loader is not None
canonical_provider_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical_provider_env)


class CanonicalProviderEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = SimpleNamespace(
            canonical_site_path=ROOT / "values/sites/dev/site.yaml",
            values_dir=ROOT / "values/sites/dev",
        )
        self.provider = Mock()
        self.provider_factory = patch.object(
            canonical_provider_env, "SopsAgeProvider", return_value=self.provider
        )
        self.provider_factory.start()
        self.addCleanup(self.provider_factory.stop)
        self.context_factory = patch.object(
            canonical_provider_env, "from_environment", return_value=self.context
        )
        self.context_factory.start()
        self.addCleanup(self.context_factory.stop)
        self.delivery = patch.object(
            canonical_provider_env,
            "deliver_environment",
            return_value={"TF_VAR_token": "test-token"},
        )
        self.delivery.start()
        self.addCleanup(self.delivery.stop)

    def test_removes_exported_age_key_from_provider_child_environment(self) -> None:
        with patch.dict(
            os.environ, {"SOPS_AGE_KEY": "dummy-not-a-real-key"}, clear=False
        ):
            with patch.object(canonical_provider_env.os, "execvpe") as execvpe:
                result = canonical_provider_env.main(["--", "tofu", "plan"])

        self.assertEqual(result, 1)
        command, arguments, child_environment = execvpe.call_args.args
        self.assertEqual(command, "tofu")
        self.assertEqual(arguments, ["tofu", "plan"])
        self.assertNotIn("SOPS_AGE_KEY", child_environment)
        self.assertEqual(child_environment["TF_VAR_token"], "test-token")

    def test_preserves_other_operator_environment_variables(self) -> None:
        with patch.dict(os.environ, {"OPERATOR_TEST_FLAG": "present"}, clear=False):
            with patch.object(canonical_provider_env.os, "execvpe") as execvpe:
                canonical_provider_env.main(["--", "tofu", "plan"])

        child_environment = execvpe.call_args.args[2]
        self.assertEqual(child_environment["OPERATOR_TEST_FLAG"], "present")

    def test_rejects_missing_canonical_site_before_provider_access(self) -> None:
        context = SimpleNamespace(canonical_site_path=None, values_dir=ROOT / "values")
        with patch.object(
            canonical_provider_env, "from_environment", return_value=context
        ):
            with patch.object(
                canonical_provider_env, "SopsAgeProvider"
            ) as provider_factory:
                result = canonical_provider_env.main(["--", "tofu", "plan"])

        self.assertEqual(result, 2)
        provider_factory.assert_not_called()

    def test_reports_provider_failure_without_exposing_environment_values(self) -> None:
        with patch.object(
            canonical_provider_env,
            "SopsAgeProvider",
            side_effect=canonical_provider_env.SecretProviderError("safe failure"),
        ):
            with patch("sys.stderr") as stderr:
                result = canonical_provider_env.main(["--", "tofu", "plan"])

        self.assertEqual(result, 1)
        self.assertIn(
            "safe failure",
            "".join(call.args[0] for call in stderr.write.call_args_list),
        )

    def test_requires_a_provider_command(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            canonical_provider_env.main([])

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

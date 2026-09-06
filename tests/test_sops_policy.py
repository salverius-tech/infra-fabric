from __future__ import annotations

import re
import unittest
from pathlib import Path


class SopsPolicyContractTests(unittest.TestCase):
    def test_public_policy_is_site_scoped_and_non_operational(self) -> None:
        path = Path(__file__).resolve().parents[1] / ".sops.yaml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("path_regex:", text)
        self.assertIn("^values/sites/[^/]+/secrets\\.sops\\.yaml$", text)
        self.assertIn("age1REPLACE_WITH_SITE_RECIPIENT", text)
        self.assertNotRegex(text, r"age1(?!REPLACE_WITH_SITE_RECIPIENT)[a-z0-9]{20,}")

        pattern = re.compile(r"^values/sites/[^/]+/secrets\.sops\.yaml$")
        self.assertTrue(pattern.fullmatch("values/sites/dev/secrets.sops.yaml"))
        self.assertFalse(pattern.fullmatch("values/.env"))
        self.assertFalse(pattern.fullmatch("values/sites/dev/terraform.tfstate"))
        self.assertFalse(pattern.fullmatch("values/sites/dev/tfplan"))


if __name__ == "__main__":
    unittest.main()

"""Focused source contract for reviewed production artifact acquisition."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CACHE_TASK = ROOT / "infra/ansible/tasks/reviewed-artifact-cache.yml"
CADDY_TASKS = {
    "infra/ansible/roles/caddy_proxy/tasks/main.yml": "caddy_proxy",
    "infra/ansible/roles/forgejo/tasks/caddy.yml": "forgejo",
    "infra/ansible/roles/hermes/tasks/main.yml": "hermes",
    "infra/ansible/roles/infisical/tasks/main.yml": "infisical",
    "infra/ansible/roles/onramp_host/tasks/main.yml": "onramp_host",
}


class ReviewedArtifactCacheTests(unittest.TestCase):
    def test_cache_contract_fails_closed_on_controller_before_staging(self) -> None:
        text = CACHE_TASK.read_text(encoding="utf-8")
        self.assertIn("delegate_to: localhost", text)
        self.assertIn("checksum_algorithm: sha256", text)
        self.assertIn("item.stat.exists", text)
        self.assertIn("item.stat.checksum == item.item.sha256", text)
        self.assertIn("deployment never fetches or populates this cache", text)
        self.assertLess(text.index("Require reviewed artifacts before guest mutation"), text.index("Stage checksum-verified reviewed artifacts"))
        for required in ("item.version", "item.architecture", "item.filename", "item.sha256"):
            self.assertIn(required, text)

    def test_every_custom_caddy_build_uses_a_reviewed_binary_not_a_remote_build(self) -> None:
        forbidden = ("go.dev/dl", "xcaddy build", "go install github.com/caddyserver/xcaddy", "curl -fsSL https://go")
        for relative, prefix in CADDY_TASKS.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("reviewed-artifact-cache.yml", text, relative)
            self.assertIn(f"{prefix}_caddy_cloudflare_version", text, relative)
            self.assertIn(f"{prefix}_caddy_cloudflare_sha256", text, relative)
            self.assertIn("name: caddy-cloudflare", text, relative)
            self.assertIn("architecture:", text, relative)
            self.assertIn("Install reviewed", text, relative)
            for token in forbidden:
                self.assertNotIn(token, text, f"{relative}: {token}")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "infra/ansible/roles"


class CaddyTemplateDeduplicationTests(unittest.TestCase):
    def test_service_roles_reference_shared_templates(self) -> None:
        for role, task_file in (
            ("forgejo", "tasks/caddy.yml"),
            ("hermes", "tasks/main.yml"),
            ("infisical", "tasks/main.yml"),
            ("onramp_host", "tasks/main.yml"),
        ):
            with self.subTest(role=role):
                tasks = (ROLES / role / task_file).read_text(encoding="utf-8")
                self.assertIn("../caddy_proxy/templates/caddy.env.j2", tasks)
                self.assertIn("../caddy_proxy/templates/caddy-override.conf.j2", tasks)
                self.assertFalse((ROLES / role / "templates/caddy.env.j2").exists())
                self.assertFalse((ROLES / role / "templates/caddy-override.conf.j2").exists())

    def test_shared_override_preserves_onramp_systemd_behavior(self) -> None:
        source = (ROLES / "caddy_proxy/templates/caddy-override.conf.j2").read_text(
            encoding="utf-8"
        )
        environment = Environment()
        template = environment.from_string(source)

        standard = template.render()
        onramp = template.render(caddy_override_execstart=False)

        self.assertIn("ExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile", standard)
        self.assertNotIn("ExecStart=", onramp)
        self.assertIn("EnvironmentFile=/etc/caddy/env", onramp)


if __name__ == "__main__":
    unittest.main()

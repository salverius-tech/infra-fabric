"""Regression coverage for digest-qualified stateful Infisical images."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_TEMPLATES = (
    ROOT / "infra/ansible/roles/infisical/templates/docker-compose.yml.j2",
    ROOT / "infra/ansible/roles/infisical_onramp/templates/docker-compose.yml.j2",
)
DIGEST_IMAGE = re.compile(r"^\s*image:\s+\S+@sha256:[0-9a-f]{64}\s*$", re.MULTILINE)


class InfisicalImageIntegrityTests(unittest.TestCase):
    def test_postgres_and_redis_images_are_digest_qualified_in_each_mode(self) -> None:
        for template in COMPOSE_TEMPLATES:
            text = template.read_text(encoding="utf-8")
            images = DIGEST_IMAGE.findall(text)
            self.assertGreaterEqual(len(images), 2, template)
            self.assertTrue(any("postgres:16-alpine@sha256:" in image for image in images), template)
            self.assertTrue(any("redis:7-alpine@sha256:" in image for image in images), template)


if __name__ == "__main__":
    unittest.main()

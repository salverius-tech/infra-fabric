"""Rendered canonical pins supply every reviewed-artifact consumer."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_projections import _compatibility_value, _resource, render_ansible_vars
from canonical_values import CanonicalSite, load_site
from service_catalog import load_catalog


class ArtifactProjectionTests(unittest.TestCase):
    def test_enabled_public_fixture_projects_reviewed_artifact_pins(self) -> None:
        data = yaml.safe_load((ROOT / "scaffold/sites/_template/site.yaml").read_text())
        # The full-catalog fixture is intentionally merged by the loader tests; this
        # focused instance enables only artifacts that have a complete public pin.
        data["platform"]["ingress"] = {"acme": {"email": "ops@example.invalid"}, "dns_providers": {"cloudflare": {}}}
        data["services"]["technitium"]["configuration"] = {
            "caddy": {"enabled": True, "server_names": ["dns.example.internal"], "upstream": {"host": "127.0.0.1", "port": 5380}, "tls": {"dns_provider": "cloudflare"}, "artifact": {"version": "2.8.4", "checksums": {"amd64": "a" * 64, "arm64": "b" * 64}}}
        }
        data["services"]["forgejo"]["configuration"]["caddy_artifact"] = {"version": "2.8.4", "checksums": {"amd64": "a" * 64, "arm64": "b" * 64}}
        with __import__("tempfile").TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "example"
            site_dir.mkdir()
            site = site_dir / "site.yaml"
            site.write_text(yaml.safe_dump(data, sort_keys=False))
            model = load_site(site, catalog_path=ROOT / "infra/services.json")
        projected = render_ansible_vars(model, load_catalog(ROOT / "infra/services.json"))
        for service, prefix in (("technitium", "caddy_proxy"), ("forgejo", "forgejo")):
            legacy = projected["services"][service]["legacy_vars"]
            self.assertEqual(legacy[f"{prefix}_caddy_cloudflare_version"], "2.8.4")
            self.assertEqual(legacy[f"{prefix}_caddy_cloudflare_sha256_amd64"], "a" * 64)
            self.assertEqual(legacy[f"{prefix}_caddy_cloudflare_sha256_arm64"], "b" * 64)

    def test_artifact_pin_rejects_uppercase_digest_and_version(self) -> None:
        data = yaml.safe_load((ROOT / "scaffold/sites/dev/site.yaml").read_text())
        data["services"]["technitium"]["configuration"] = {
            "caddy": {"enabled": True, "server_names": ["dns.example.internal"], "upstream": {"host": "127.0.0.1", "port": 5380}, "tls": {"dns_provider": "cloudflare"}, "artifact": {"version": "V2.8.4", "checksums": {"amd64": "A" * 64, "arm64": "b" * 64}}}
        }
        with __import__("tempfile").TemporaryDirectory() as tmp:
            site = Path(tmp) / "site.yaml"
            site.write_text(yaml.safe_dump(data, sort_keys=False))
            with self.assertRaises(ValueError):
                load_site(site, catalog_path=ROOT / "infra/services.json")

    def test_full_catalog_projects_every_unconditional_artifact_consumer(self) -> None:
        data = yaml.safe_load((ROOT / "scaffold/sites/dev/site.yaml").read_text())
        data["resources"] = yaml.safe_load((ROOT / "scaffold/fixtures/resource-runtime.yaml").read_text())
        data["services"] = yaml.safe_load((ROOT / "scaffold/fixtures/full-catalog-services.yaml").read_text())["services"]
        model = CanonicalSite.model_validate(data)
        catalog = load_catalog(ROOT / "infra/services.json")
        catalog.validate_model_services(model.services, model.resources)
        expected = {
            "forgejo_runner": {
                "forgejo_runner_version": "12.7.3",
                "forgejo_runner_compose_version": "2.29.7",
                "forgejo_runner_compose_sha256_amd64": "a" * 64,
                "forgejo_runner_compose_sha256_arm64": "b" * 64,
                "forgejo_runner_just_version": "1.36.0",
                "forgejo_runner_just_sha256_amd64": "c" * 64,
                "forgejo_runner_just_sha256_arm64": "d" * 64,
                "forgejo_runner_sha256_amd64": "e" * 64,
                "forgejo_runner_sha256_arm64": "f" * 64,
            },
            "infisical": {
                "infisical_caddy_cloudflare_version": "2.8.4",
                "infisical_caddy_cloudflare_sha256_amd64": "a" * 64,
                "infisical_caddy_cloudflare_sha256_arm64": "b" * 64,
                "infisical_compose_version": "2.29.7",
                "infisical_compose_sha256_amd64": "c" * 64,
                "infisical_compose_sha256_arm64": "d" * 64,
            },
            "hermes": {
                "hermes_caddy_cloudflare_version": "2.8.4",
                "hermes_caddy_cloudflare_sha256_amd64": "a" * 64,
                "hermes_caddy_cloudflare_sha256_arm64": "b" * 64,
                "hermes_compose_version": "2.29.7",
                "hermes_compose_sha256_amd64": "c" * 64,
                "hermes_compose_sha256_arm64": "d" * 64,
                "hermes_just_version": "1.36.0",
                "hermes_just_sha256_amd64": "e" * 64,
                "hermes_just_sha256_arm64": "f" * 64,
            },
            "onramp_host": {
                "onramp_host_caddy_cloudflare_version": "2.8.4",
                "onramp_host_caddy_cloudflare_sha256_amd64": "a" * 64,
                "onramp_host_caddy_cloudflare_sha256_arm64": "b" * 64,
            },
        }
        for service, values in expected.items():
            with self.subTest(service=service):
                selected = model.services[service]
                resource = _resource(model, selected.resource)
                mapping = catalog.get(service).inventory["canonical_play_vars"]
                resolved = {
                    key: _compatibility_value(model, selected, resource, mapping[key])
                    for key in values
                }
                self.assertEqual(resolved, values)

    def test_role_specs_declare_every_projected_artifact_variable(self) -> None:
        catalog = load_catalog(ROOT / "infra/services.json")
        roles = {
            "technitium": "caddy_proxy",
            "forgejo": "forgejo",
            "forgejo_runner": "forgejo_runner",
            "infisical": "infisical",
            "hermes": "hermes",
            "onramp_host": "onramp_host",
        }
        for service, role in roles.items():
            spec = yaml.safe_load(
                (ROOT / f"infra/ansible/roles/{role}/meta/argument_specs.yml").read_text()
            )["argument_specs"]["main"]["options"]
            artifact_vars = {
                name
                for name in catalog.get(service).inventory["canonical_play_vars"]
                if "caddy_cloudflare" in name or "_sha256_" in name
            }
            self.assertLessEqual(artifact_vars, set(spec), service)


if __name__ == "__main__":
    unittest.main()

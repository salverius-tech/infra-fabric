from __future__ import annotations

import copy
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_projections import (  # noqa: E402
    ONRAMP_HANDOFF_API_VERSION,
    ProjectionError,
    render_onramp_handoff,
    render_projection_set,
    verify_onramp_handoff_identity,
)
from canonical_values import CanonicalSite, load_site, model_digest  # noqa: E402
from projection_manifest import build_manifest, content_digest  # noqa: E402
from service_catalog import ServiceCatalogError, load_catalog  # noqa: E402

SITE = {
    "schema_version": 1,
    "site": {
        "name": "dev",
        "class": "development",
        "lifecycle": "disposable",
        "allow_apply": True,
        "allow_destroy": True,
    },
    "platform": {
        "proxmox": {
            "endpoint": "https://proxmox.example.internal:8006/",
            "node": "pve",
            "insecure": True,
        },
        "network": {
            "default_bridge": "vmbr0",
            "default_gateway": "192.0.2.1",
            "default_dns_servers": ["192.0.2.53"],
            "default_search_domain": "example.internal",
        },
        "storage": {
            "rootfs_datastore": "local-lvm",
            "template_datastore": "local",
        },
    },
    "resources": {
        "shared_hosts": {
            "onramp-node": {
                "type": "vm",
                "identity": {
                    "vmid": 120,
                    "hostname": "onramp-host",
                    "description": "Public-safe Onramp handoff fixture",
                },
                "network": {
                    "address": "192.0.2.120/24",
                },
                "compute": {
                    "cores": 4,
                    "memory_mb": 8192,
                },
                "storage": {
                    "root": {
                        "type": "proxmox_volume",
                        "storage_id": "local-lvm",
                        "size_gb": 64,
                        "target": "/",
                    }
                },
                "runtime": {
                    "started": True,
                    "start_on_boot": True,
                    "cloud_init_user": "infra",
                },
                "security": {
                    "deploy_user": "onramp",
                    "deploy_dir": "/srv/onramp",
                    "password_authentication": False,
                    "permit_root_login": False,
                    "allow_passwordless_sudo": False,
                    "allowed_ssh_cidrs": ["192.0.2.0/24"],
                },
                "artifacts": {
                    "caddy_cloudflare": {
                        "version": "2.8.4",
                        "checksums": {"amd64": "b" * 64, "arm64": "c" * 64},
                    }
                },
            }
        }
    },
    "services": {
        "onramp_host": {
            "enabled": True,
            "resource": "onramp-node",
            "state": {"capable": True, "disable_policy": "retain"},
        },
        "searxng_onramp": {
            "enabled": True,
            "resource": "onramp-node",
            "dependencies": ["onramp_host"],
            "state": {"capable": True, "disable_policy": "retain"},
            "endpoints": {
                "public_names": ["search.example.internal"],
                "public_url": "https://search.example.internal/",
                "visibility": "internal",
            },
            "release": {
                "source": "container",
                "image": "docker.io/searxng/searxng",
                "digest": "sha256:" + "a" * 64,
            },
        },
    },
}


class OnrampHandoffProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "infra" / "services.json")

    def model(self, data: dict[str, object] | None = None) -> CanonicalSite:
        return CanonicalSite.model_validate(copy.deepcopy(data or SITE))

    def test_projection_is_versioned_identity_bound_and_non_secret(self) -> None:
        model = self.model()
        handoff = render_onramp_handoff(model, self.catalog)

        self.assertEqual(handoff["api_version"], ONRAMP_HANDOFF_API_VERSION)
        self.assertEqual(handoff["kind"], "OnrampSubstrate")
        self.assertEqual(handoff["metadata"]["canonical_site"], "dev")
        self.assertEqual(handoff["metadata"]["canonical_service"], "onramp_host")
        self.assertEqual(handoff["metadata"]["canonical_resource"], "onramp-node")
        self.assertTrue(handoff["metadata"]["enabled"])
        self.assertRegex(handoff["metadata"]["canonical_model_digest"], r"^[0-9a-f]{64}$")
        spec = handoff["spec"]
        self.assertEqual(
            spec["identity"],
            {
                "canonical_resource": "onramp-node",
                "resource_type": "vm",
                "hostname": "onramp-host",
            },
        )
        self.assertEqual(
            spec["connection"],
            {"address": "192.0.2.120", "ssh_port": 22, "user": "onramp"},
        )
        self.assertEqual(
            spec["substrate"]["operating_system"],
            {"family": "debian", "major_version": 13},
        )
        self.assertNotIn("architecture", spec["substrate"]["operating_system"])
        self.assertEqual(
            spec["substrate"]["container_runtime"],
            {
                "engine": "podman",
                "rootless": True,
                "compose_command": "podman-compose",
            },
        )
        permissions = spec["authority"]["onramp_permissions"]
        self.assertFalse(permissions["proxmox_lifecycle"])
        self.assertFalse(permissions["generated_projection_write"])
        self.assertTrue(permissions["application_lifecycle"])
        rendered = repr(handoff).lower()
        for forbidden in (
            "vmid",
            "temporary_workloads",
            "ssh_public_keys",
            "api_token",
            "password",
            "secret_key",
            "datastore",
            "image_url",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_disabled_host_emits_explicit_non_consumable_contract(self) -> None:
        data = copy.deepcopy(SITE)
        data["services"]["searxng_onramp"]["enabled"] = False
        data["services"]["onramp_host"]["enabled"] = False
        handoff = render_onramp_handoff(self.model(data), self.catalog)
        self.assertFalse(handoff["metadata"]["enabled"])
        self.assertIsNone(handoff["metadata"]["canonical_resource"])
        self.assertRegex(handoff["metadata"]["canonical_model_digest"], r"^[0-9a-f]{64}$")
        self.assertIsNone(handoff["spec"])

    def test_projection_rejects_guest_owned_or_non_vm_substrate(self) -> None:
        data = copy.deepcopy(SITE)
        resource = data["resources"]["shared_hosts"].pop("onramp-node")
        data["resources"]["guests"] = {"onramp-node": resource}
        with self.assertRaisesRegex(ProjectionError, "resources.shared_hosts"):
            render_onramp_handoff(self.model(data), self.catalog)

        data = copy.deepcopy(SITE)
        data["resources"]["shared_hosts"]["onramp-node"]["type"] = "lxc"
        data["resources"]["shared_hosts"]["onramp-node"]["runtime"] = {
            "started": True,
            "start_on_boot": True,
            "unprivileged": True,
        }
        with self.assertRaisesRegex(ProjectionError, "VM shared host"):
            render_onramp_handoff(self.model(data), self.catalog)

    def test_identity_verification_rejects_tampering(self) -> None:
        model = self.model()
        handoff = render_onramp_handoff(model, self.catalog)
        verify_onramp_handoff_identity(model, self.catalog, handoff)
        altered = copy.deepcopy(handoff)
        altered["metadata"]["canonical_model_digest"] = "0" * 64
        with self.assertRaisesRegex(ProjectionError, "identity disagrees"):
            verify_onramp_handoff_identity(model, self.catalog, altered)

    def test_projection_rejects_insecure_ssh_boundary(self) -> None:
        for field in ("password_authentication", "permit_root_login"):
            data = copy.deepcopy(SITE)
            data["resources"]["shared_hosts"]["onramp-node"]["security"][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(
                ProjectionError, "password and root SSH login"
            ):
                render_onramp_handoff(self.model(data), self.catalog)

    def test_canonical_resource_rejects_invalid_handoff_connection_identity(self) -> None:
        cases = (
            ("deploy_user", "root"),
            ("deploy_user", "Bad User"),
            ("deploy_dir", "relative/path"),
            ("deploy_dir", "/srv/../root"),
        )
        for field, value in cases:
            data = copy.deepcopy(SITE)
            data["resources"]["shared_hosts"]["onramp-node"]["security"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.model(data)

    def test_catalog_handoff_metadata_is_strict(self) -> None:
        catalog_path = ROOT / "infra" / "services.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["services"]["onramp_host"]["handoff"]["container_runtime"][
            "engine"
        ] = "docker"
        with tempfile.TemporaryDirectory() as temporary:
            altered = Path(temporary) / "services.json"
            altered.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ServiceCatalogError, "reviewed v1 contract"):
                load_catalog(altered)

    def test_complete_projection_set_carries_handoff(self) -> None:
        projections = render_projection_set(self.model(), self.catalog)
        self.assertEqual(
            set(projections),
            {
                "terraform.auto.tfvars.json",
                "ansible-inventory.json",
                "ansible-vars.json",
                "dns-records.json",
                "onramp-handoff.json",
            },
        )

    def _render_enabled_fixture(self, root: Path) -> tuple[Path, Path]:
        site_dir = root / "dev"
        site_dir.mkdir()
        site = site_dir / "site.yaml"
        site.write_text(yaml.safe_dump(SITE, sort_keys=False), encoding="utf-8")
        generated = site_dir / "generated"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "canonical-render.py"),
                "--site-file",
                str(site),
                "--catalog",
                str(ROOT / "infra" / "services.json"),
                "--output-dir",
                str(generated),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return site, generated

    def test_enabled_handoff_cli_render_manifest_and_verify_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, generated = self._render_enabled_fixture(Path(temporary))
            self.assertEqual(stat.S_IMODE(generated.stat().st_mode), 0o700)
            for path in generated.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)
            manifest = json.loads(
                (generated / "manifest.json").read_text(encoding="utf-8")
            )
            handoff = json.loads(
                (generated / "onramp-handoff.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["projections"]["onramp-handoff.json"]["digest"],
                content_digest(handoff),
            )
            verify = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify-projections.py"),
                    "--site-file",
                    str(site),
                    "--catalog",
                    str(ROOT / "infra" / "services.json"),
                    "--generated-dir",
                    str(generated),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_verify_rejects_tampered_handoff_with_rebuilt_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, generated = self._render_enabled_fixture(Path(temporary))
            manifest_path = generated / "manifest.json"
            original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            projections = {
                name: json.loads((generated / name).read_text(encoding="utf-8"))
                for name in original_manifest["projections"]
            }
            projections["onramp-handoff.json"]["spec"]["authority"][
                "onramp_permissions"
            ]["proxmox_lifecycle"] = True
            handoff_path = generated / "onramp-handoff.json"
            handoff_path.write_text(
                json.dumps(projections["onramp-handoff.json"]) + "\n",
                encoding="utf-8",
            )
            handoff_path.chmod(0o600)
            model = load_site(
                site, catalog_path=ROOT / "infra" / "services.json"
            )
            rebuilt = build_manifest(
                site=model.site.name,
                schema_version=model.schema_version,
                model_digest=model_digest(model),
                secret_digest=None,
                projections=projections,
                renderer_version=original_manifest["renderer_version"],
                source_commit=original_manifest["source_commit"],
            )
            manifest_path.write_text(json.dumps(rebuilt) + "\n", encoding="utf-8")
            manifest_path.chmod(0o600)
            verify = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify-projections.py"),
                    "--site-file",
                    str(site),
                    "--catalog",
                    str(ROOT / "infra" / "services.json"),
                    "--generated-dir",
                    str(generated),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 1)
            self.assertIn("handoff identity disagrees", verify.stderr)


if __name__ == "__main__":
    unittest.main()

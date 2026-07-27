from __future__ import annotations

import sys
import subprocess
import tempfile
import stat
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from canonical_values import CanonicalValuesError, load_site, model_digest, normalized_model, redacted_summary
from canonical_projections import (
    render_ansible_inventory,
    render_ansible_vars,
    render_dns_records,
    render_opentofu_variables,
)
from service_catalog import load_catalog


VALID_SITE = """
schema_version: 1
site:
  name: dev
  class: development
  lifecycle: disposable
  allow_apply: true
  allow_destroy: true
platform:
  proxmox:
    endpoint: https://proxmox.example.internal:8006/
    node: pve
    insecure: true
  network:
    default_bridge: vmbr0
    default_gateway: 192.0.2.1
    default_dns_servers: [1.1.1.1, 9.9.9.9]
    default_search_domain: example.internal
  storage:
    rootfs_datastore: local-lvm
    template_datastore: local
resources:
  guests:
    forgejo:
      type: lxc
      identity:
        vmid: 107
        hostname: forgejo
      network:
        address: dhcp
        expected_address: 192.0.2.62
      compute:
        cores: 2
        memory_mb: 2048
      storage:
        root:
          type: proxmox_volume
          storage_id: local-lvm
          size_gb: 8
          target: /
      runtime:
        started: true
        start_on_boot: true
        unprivileged: true
services:
  forgejo:
    enabled: true
    resource: forgejo
    state:
      capable: true
      disable_policy: retain
    endpoints:
      public_names: [git.example.internal]
      public_url: https://git.example.internal/
      visibility: internal
    release:
      source: package
      version: 12.0.4
"""


class CanonicalValuesTests(unittest.TestCase):
    def write_site(self, content: str, *, directory_name: str = "dev") -> Path:
        root = Path(tempfile.mkdtemp())
        site_dir = root / directory_name
        site_dir.mkdir()
        path = site_dir / "site.yaml"
        path.write_text(content, encoding="utf-8")
        self.addCleanup(lambda: self._remove(root))
        return path

    @staticmethod
    def _remove(path: Path) -> None:
        import shutil

        shutil.rmtree(path, ignore_errors=True)

    def test_loads_valid_site_and_returns_redacted_summary(self) -> None:
        model = load_site(self.write_site(VALID_SITE), expected_site="dev")
        summary = redacted_summary(model)
        self.assertEqual(summary["site"]["name"], "dev")
        self.assertEqual(summary["enabled_services"], ["forgejo"])
        self.assertNotIn("secret", summary)
        self.assertEqual(len(model.resources.guests), 1)

    def test_digest_is_stable_across_formatting_and_key_order(self) -> None:
        first = load_site(self.write_site(VALID_SITE))
        reformatted = VALID_SITE.replace("  name: dev", "  # comment\n  name: dev").replace(
            "default_bridge: vmbr0\n    default_gateway: 192.0.2.1",
            "default_gateway: 192.0.2.1\n    default_bridge: vmbr0",
        )
        second = load_site(self.write_site(reformatted))
        self.assertEqual(model_digest(first), model_digest(second))
        self.assertEqual(normalized_model(first), normalized_model(second))

    def test_rejects_duplicate_yaml_keys(self) -> None:
        content = VALID_SITE.replace("schema_version: 1", "schema_version: 1\nschema_version: 1", 1)
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_rejects_yaml_aliases(self) -> None:
        content = VALID_SITE.replace(
            "      network:\n        address: dhcp",
            "      network: &network\n        address: dhcp",
        ).replace(
            "      compute:\n        cores: 2",
            "      compute: *network\n        cores: 2",
        )
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_rejects_site_directory_mismatch(self) -> None:
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(VALID_SITE, directory_name="staging"))

    def test_rejects_production_destroy_policy(self) -> None:
        content = VALID_SITE.replace("class: development", "class: production")
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_rejects_duplicate_vmids(self) -> None:
        content = VALID_SITE.replace(
            "services:\n", "  guests:\n    other:\n      type: lxc\n      identity:\n        vmid: 107\n        hostname: other\n      network:\n        address: dhcp\n      compute:\n        cores: 1\n        memory_mb: 512\n      storage:\n        root:\n          type: directory\n          target: /\n      runtime: {}\nservices:\n",
        )
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_rejects_unresolved_enabled_service_resource(self) -> None:
        content = VALID_SITE.replace("resource: forgejo", "resource: missing")
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_rejects_static_resource_with_expected_address(self) -> None:
        content = VALID_SITE.replace("address: dhcp", "address: 192.0.2.62/24")
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_platform_defaults_fill_only_unset_resource_fields(self) -> None:
        model = load_site(self.write_site(VALID_SITE))
        network = model.resources.guests["forgejo"].network
        self.assertEqual(network.bridge, "vmbr0")
        self.assertEqual(network.dns_servers, ["1.1.1.1", "9.9.9.9"])
        self.assertEqual(network.search_domain, "example.internal")
        self.assertEqual(model.resources.guests["forgejo"].storage.root.storage_id, "local-lvm")

    def test_resource_network_overlaps_are_rejected(self) -> None:
        content = VALID_SITE.replace(
            "services:\n",
            "    other:\n      type: lxc\n      identity:\n        vmid: 108\n        hostname: other\n      network:\n        address: 192.0.2.0/25\n      compute:\n        cores: 1\n        memory_mb: 512\n      storage:\n        root:\n          type: directory\n          target: /\n      runtime: {}\nservices:\n",
            1,
        ).replace("address: dhcp", "address: 192.0.2.64/26", 1).replace("        expected_address: 192.0.2.62\n", "")
        with self.assertRaisesRegex(CanonicalValuesError, "network ranges overlap"):
            load_site(self.write_site(content))

    def test_invalid_ipv4_octets_are_rejected(self) -> None:
        content = VALID_SITE.replace("expected_address: 192.0.2.62", "expected_address: 999.0.2.62")
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_loads_public_scaffold_fixture(self) -> None:
        path = Path(__file__).resolve().parents[1] / "scaffold" / "sites" / "dev" / "site.yaml"
        model = load_site(path, expected_site="dev", catalog_path=Path(__file__).resolve().parents[1] / "infra" / "services.json")
        self.assertEqual(model.site.class_, "development")
        self.assertEqual(sorted(name for name, service in model.services.items() if service.enabled), ["forgejo", "technitium"])

    def test_renderer_writes_non_secret_projection_set_with_restricted_directory(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: self._remove(root))
        script = Path(__file__).resolve().parents[1] / "scripts" / "canonical-render.py"
        site = Path(__file__).resolve().parents[1] / "scaffold" / "sites" / "dev" / "site.yaml"
        catalog = Path(__file__).resolve().parents[1] / "infra" / "services.json"
        output = root / "generated"
        result = subprocess.run(
            [sys.executable, str(script), "--site-file", str(site), "--catalog", str(catalog), "--output-dir", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        self.assertEqual(
            sorted(path.name for path in output.iterdir()),
            [
                "ansible-inventory.json",
                "ansible-vars.json",
                "dns-records.json",
                "manifest.json",
                "terraform.auto.tfvars.json",
            ],
        )
        self.assertNotIn("password", (output / "manifest.json").read_text(encoding="utf-8").lower())

    def test_cli_summary_is_redacted_and_catalog_validated(self) -> None:
        site_path = self.write_site(VALID_SITE)
        script = Path(__file__).resolve().parents[1] / "scripts" / "canonical-values.py"
        catalog = Path(__file__).resolve().parents[1] / "infra" / "services.json"
        result = subprocess.run(
            [sys.executable, str(script), "--site-file", str(site_path), "--catalog", str(catalog), "summary"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"enabled_services": [\n    "forgejo"', result.stdout)
        self.assertNotIn("password", result.stdout.lower())

    def test_non_secret_consumer_projections_use_canonical_ownership(self) -> None:
        content = VALID_SITE.replace(
            "      visibility: internal",
            "      visibility: internal\n      dns:\n        enabled: true",
        )
        site_path = self.write_site(content)
        catalog_path = Path(__file__).resolve().parents[1] / "infra" / "services.json"
        model = load_site(site_path, catalog_path=catalog_path)
        catalog = load_catalog(catalog_path)
        tofu = render_opentofu_variables(model)
        inventory = render_ansible_inventory(model, catalog)
        ansible_vars = render_ansible_vars(model, catalog)
        dns = render_dns_records(model)
        self.assertEqual(tofu["forgejo_container_vmid"], 107)
        self.assertEqual(tofu["forgejo_server_name"], "git.example.internal")
        self.assertEqual(inventory["forgejo"]["hosts"], ["forgejo_lxc"])
        self.assertEqual(ansible_vars["canonical_site"], "dev")
        self.assertEqual(ansible_vars["services"]["forgejo"]["resource"], "forgejo")
        self.assertEqual(
            ansible_vars["services"]["forgejo"]["endpoints"]["public_names"],
            ["git.example.internal"],
        )
        self.assertEqual(dns["a_records"], {"git.example.internal": "192.0.2.62"})


if __name__ == "__main__":
    unittest.main()

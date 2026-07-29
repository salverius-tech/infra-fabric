from __future__ import annotations

import sys
import subprocess
import tempfile
import stat
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import atomic_output
from atomic_output import atomic_output_directory
from canonical_values import CanonicalValuesError, HermesConfiguration, ImageChecksum, ImageDefinition, PlatformImages, ResourceNetwork, ServiceRelease, load_site, model_digest, normalize_container_image_reference, normalized_model, redacted_summary
from canonical_projections import (
    ProjectionError,
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

    def test_hermes_non_secret_configuration_is_strictly_typed(self) -> None:
        configuration = HermesConfiguration.model_validate(
            {
                "runtime_user": "anvil",
                "repository_path": "/srv/homelab-infra",
                "allow_legacy_runtime": False,
                "tuning": {
                    "compression_threshold": 0.75,
                    "max_concurrent_children": 5,
                    "max_spawn_depth": 2,
                },
                "node": {
                    "version": "22.23.1",
                    "checksums": {"amd64": "a" * 64, "arm64": "b" * 64},
                },
                "dashboard": {"enabled": True, "host": "127.0.0.1", "auth_username": "admin"},
                "web": {"searxng_url": "https://searxng.example.internal"},
                "control": {
                    "enabled": True,
                    "domain": "Control.Hermes.Example.Internal.",
                    "source_url": "https://github.com/example/hermes-control.git",
                    "source_ref": "c" * 40,
                },
            }
        )
        self.assertEqual(configuration.runtime_user, "anvil")
        self.assertEqual(configuration.repository_path, "/srv/homelab-infra")
        self.assertEqual(configuration.node.checksums["arm64"], "b" * 64)
        self.assertTrue(configuration.control.enabled)
        self.assertEqual(configuration.control.domain, "control.hermes.example.internal")
        self.assertEqual(configuration.control.api_host, "127.0.0.1")
        self.assertEqual(configuration.control.api_port, 8787)
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"runtime_user": "root"})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"repository_path": "relative/repo"})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"repository_path": "/srv/../repo"})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"dashboard": {"host": "0.0.0.0"}})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"tuning": {"max_spawn_depth": 4}})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"control": {"enabled": True}})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"control": {"api_host": "0.0.0.0"}})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"control": {"require_task_approval": False}})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"control": {"source_url": "http://example.internal/control"}})
        with self.assertRaises(ValueError):
            HermesConfiguration.model_validate({"control": {"plugin_socket": "/run/../tmp.sock"}})

    def test_hermes_release_metadata_validates_managed_pins(self) -> None:
        release = ServiceRelease(
            source="binary",
            version="0.18.0",
            tag="v2026.7.1",
            commit="a" * 40,
            checksum="b" * 64,
        )
        self.assertEqual(release.tag, "v2026.7.1")
        with self.assertRaises(ValueError):
            ServiceRelease(source="binary", version="0.18.0", tag="main")
        with self.assertRaises(ValueError):
            ServiceRelease(source="binary", version="0.18.0", commit="A" * 40)

    def test_loads_valid_site_and_returns_redacted_summary(self) -> None:
        model = load_site(self.write_site(VALID_SITE), expected_site="dev")
        summary = redacted_summary(model)
        self.assertEqual(summary["site"]["name"], "dev")
        self.assertEqual(summary["enabled_services"], ["forgejo"])
        self.assertNotIn("secret", summary)
        self.assertEqual(len(model.resources.guests), 1)

    def test_typed_cloud_init_and_template_timeout_projection(self) -> None:
        content = VALID_SITE.replace(
            "  storage:\n    rootfs_datastore: local-lvm",
            "  vm_cloud_init_user: vmadmin\n  lxc_template_download_timeout_seconds: 1800\n  storage:\n    rootfs_datastore: local-lvm",
        ).replace(
            "        unprivileged: true",
            "        unprivileged: true\n        cloud_init_user: forgejo-admin",
        )
        model = load_site(self.write_site(content))
        values = render_opentofu_variables(model)
        self.assertEqual(values["guest_vm_cloud_init_user"], "vmadmin")
        self.assertEqual(values["lxc_template_download_timeout_seconds"], 1800)
        self.assertEqual(values["service_runtime"]["forgejo"]["cloud_init_user"], "forgejo-admin")
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content.replace("vmadmin", "bad user")))

    def test_resource_lifecycle_projection_preserves_existing_variable_names(self) -> None:
        model = load_site(self.write_site(VALID_SITE))
        values = render_opentofu_variables(model)
        resource = model.resources.guests["forgejo"]
        from canonical_projections import _resource_variables

        projected = _resource_variables("hermes", resource)
        self.assertEqual(projected["hermes_started"], True)
        self.assertEqual(projected["hermes_start_on_boot"], True)
        self.assertNotIn("hermes_container_started", projected)
        self.assertNotIn("hermes_started", values)

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

    def test_normalizes_protocols_and_rejects_duplicate_protocols(self) -> None:
        content = VALID_SITE.replace(
            "      public_url: https://git.example.internal/",
            "      public_url: https://git.example.internal/\n      protocols:\n        - HTTPS\n        - ssh",
        )
        model = load_site(self.write_site(content))
        self.assertEqual(model.services["forgejo"].endpoints.protocols, ["https", "ssh"])
        duplicate = content.replace("        - ssh", "        - HTTPS")
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(duplicate))

    def test_endpoint_port_names_are_lowercase_identifiers(self) -> None:
        for port_name in ("", "HTTPS", "web.port", " web", "-ssh"):
            with self.subTest(port_name=port_name):
                content = VALID_SITE.replace(
                    "      public_url: https://git.example.internal/",
                    f"      public_url: https://git.example.internal/\n      ports:\n        {port_name or '':} 443",
                )
                with self.assertRaises(CanonicalValuesError):
                    load_site(self.write_site(content))

    def test_endpoint_port_values_remain_strict_integers(self) -> None:
        for value in ('"443"', "443.0"):
            with self.subTest(value=value):
                content = VALID_SITE.replace(
                    "      public_url: https://git.example.internal/",
                    f"      public_url: https://git.example.internal/\n      ports:\n        https: {value}",
                )
                with self.assertRaises(CanonicalValuesError):
                    load_site(self.write_site(content))

    def test_rejects_endpoint_ports_outside_tcp_range(self) -> None:
        content = VALID_SITE.replace(
            "      public_url: https://git.example.internal/",
            "      public_url: https://git.example.internal/\n      ports:\n        https: 65536",
        )
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

    def test_renderer_failure_does_not_leave_partial_output_or_secret(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: self._remove(root))
        output = root / "generated"
        output.mkdir()
        (output / "previous.json").write_text("previous\n", encoding="utf-8")
        script = Path(__file__).resolve().parents[1] / "scripts" / "canonical-render.py"
        site = Path(__file__).resolve().parents[1] / "scaffold" / "sites" / "dev" / "site.yaml"
        catalog = Path(__file__).resolve().parents[1] / "infra" / "services.json"
        invalid_site = root / "invalid-site.yaml"
        invalid_site.write_text(
            site.read_text(encoding="utf-8").replace(
                "      public_url: https://git.example.internal/",
                "      public_url: https://git.example.internal/\n      dns:\n        enabled: true\n        innocuous_secret_carrier: SECRET_SENTINEL",
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(script), "--site-file", str(invalid_site), "--catalog", str(catalog), "--output-dir", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((output / "previous.json").read_text(encoding="utf-8"), "previous\n")
        self.assertEqual(sorted(path.name for path in output.iterdir()), ["previous.json"])
        self.assertNotIn("SECRET_SENTINEL", result.stderr)

    def test_atomic_output_preserves_previous_directory_when_replacement_fails(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: self._remove(root))
        output = root / "generated"
        output.mkdir()
        (output / "previous.json").write_text("previous\n", encoding="utf-8")
        original_replace = atomic_output.os.replace

        def fail_install(source: str | Path, destination: str | Path) -> None:
            if Path(source).name.startswith(".generated.tmp-"):
                raise OSError("simulated replacement failure")
            original_replace(source, destination)

        with mock.patch("atomic_output.os.replace", side_effect=fail_install):
            with self.assertRaisesRegex(OSError, "simulated replacement failure"):
                atomic_output_directory(
                    output,
                    lambda directory: (directory / "new.json").write_text("new\n", encoding="utf-8"),
                )
        self.assertEqual((output / "previous.json").read_text(encoding="utf-8"), "previous\n")
        self.assertFalse((output / "new.json").exists())

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

    def test_non_secret_projection_rejects_sensitive_configuration_fields(self) -> None:
        content = VALID_SITE.replace(
            "      version: 12.0.4",
            "      version: 12.0.4\n    configuration:\n      api_token: SECRET_SENTINEL_DO_NOT_PROJECT",
        )
        model = load_site(self.write_site(content))
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        with self.assertRaisesRegex(ProjectionError, "sensitive field"):
            render_ansible_vars(model, catalog)

    def test_non_secret_projection_rejects_opaque_runtime_template(self) -> None:
        content = VALID_SITE.replace(
            "        unprivileged: true",
            "        unprivileged: true\n        template:\n          image: public-template",
        )
        model = load_site(self.write_site(content))
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        with self.assertRaisesRegex(ProjectionError, "runtime.template"):
            render_ansible_vars(model, catalog)

    def test_dns_metadata_rejects_unknown_fields_without_exposing_values(self) -> None:
        content = VALID_SITE.replace(
            "      visibility: internal",
            "      visibility: internal\n      dns:\n        enabled: true\n        innocuous_secret_carrier: SECRET_SENTINEL",
        )
        with self.assertRaises(CanonicalValuesError) as context:
            load_site(self.write_site(content))
        self.assertNotIn("SECRET_SENTINEL", str(context.exception))

    def test_dns_metadata_requires_strict_supported_values(self) -> None:
        for replacement in (
            "      visibility: internal\n      dns:\n        enabled: \"true\"",
            "      visibility: internal\n      dns:\n        record_type: AAAA",
        ):
            with self.subTest(replacement=replacement):
                with self.assertRaises(CanonicalValuesError):
                    load_site(self.write_site(VALID_SITE.replace("      visibility: internal", replacement)))

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


    def test_distinct_vm_image_families_project_independently_without_file_id(self) -> None:
        model = load_site(self.write_site(VALID_SITE), catalog_path=Path(__file__).resolve().parents[1] / "infra" / "services.json")
        model.platform.images.vm["guest"] = ImageDefinition(
            type="vm_image",
            datastore_id="guest-store",
            url="https://images.example.internal/guest.qcow2",
            file_name="guest.qcow2",
            checksum=ImageChecksum(algorithm="sha256", value="a" * 64),
        )
        model.platform.images.vm["onramp_host"] = ImageDefinition(
            type="vm_image",
            datastore_id="onramp-store",
            url="https://images.example.internal/onramp.qcow2",
            file_name="onramp.qcow2",
            checksum=ImageChecksum(algorithm="sha256", value="b" * 64),
        )
        tofu = render_opentofu_variables(model)
        self.assertEqual(tofu["guest_vm_image_datastore_id"], "guest-store")
        self.assertEqual(tofu["onramp_host_image_datastore_id"], "onramp-store")
        self.assertEqual(tofu["guest_vm_image_checksum"], "a" * 64)
        self.assertEqual(tofu["onramp_host_image_checksum"], "b" * 64)
        self.assertNotIn("guest_vm_image_file_id", tofu)
        self.assertNotIn("onramp_host_image_file_id", tofu)

    def test_searxng_immutable_image_reference_splits_and_rejects_mutable_forms(self) -> None:
        digest = "sha256:" + "a" * 64
        self.assertEqual(
            normalize_container_image_reference("docker.io/searxng/searxng@" + digest),
            ("docker.io/searxng/searxng", digest),
        )
        for reference in (
            "docker.io/searxng/searxng:latest",
            "docker.io/searxng/searxng@sha256:" + "A" * 64,
            "Docker.io/searxng/searxng@" + digest,
        ):
            with self.subTest(reference=reference), self.assertRaises(CanonicalValuesError):
                normalize_container_image_reference(reference)

    def test_container_release_requires_separate_lowercase_sha256_digest(self) -> None:
        valid = ServiceRelease(source="container", image="ghcr.io/example/app:1.0", digest="sha256:" + "a" * 64)
        self.assertEqual(valid.digest, "sha256:" + "a" * 64)
        for digest in ("not-a-digest", "SHA256:" + "a" * 64, "sha512:" + "a" * 128):
            with self.assertRaises(ValueError):
                ServiceRelease(source="container", image="ghcr.io/example/app:1.0", digest=digest)
        with self.assertRaises(ValueError):
            ServiceRelease(source="container", image="ghcr.io/example/app@sha256:" + "a" * 64, digest="sha256:" + "a" * 64)

        network = ResourceNetwork(address="dhcp", mac_address="AA:bb:00:11:22:33")
        self.assertEqual(network.mac_address, "aa:bb:00:11:22:33")
        with self.assertRaises(ValueError):
            ResourceNetwork(address="dhcp", mac_address="not-a-mac")

    def test_image_definitions_require_safe_transport_metadata(self) -> None:
        checksum = ImageChecksum(algorithm="sha256", value="a" * 64)
        image = ImageDefinition(
            type="lxc_template",
            url="https://images.example.internal/debian.tar.zst",
            file_name="debian.tar.zst",
            checksum=checksum,
        )
        self.assertEqual(image.file_name, "debian.tar.zst")
        with self.assertRaises(ValueError):
            ImageDefinition(type="lxc_template", url="http://images.example.internal/image", file_name="image", checksum=checksum)
        with self.assertRaises(ValueError):
            ImageDefinition(type="lxc_template", url="https://images.example.internal/image", file_name="../image", checksum=checksum)

    def test_image_family_and_identifier_must_match(self) -> None:
        checksum = ImageChecksum(algorithm="sha256", value="b" * 64)
        valid = ImageDefinition(
            type="vm_image",
            datastore_id="local-vm",
            url="https://images.example.internal/debian.img",
            file_name="debian.img",
            checksum=checksum,
        )
        with self.assertRaises(ValueError):
            PlatformImages(lxc={"debian": valid})
        with self.assertRaises(ValueError):
            PlatformImages(vm={"Debian": valid})


if __name__ == "__main__":
    unittest.main()

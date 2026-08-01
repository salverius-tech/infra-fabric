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
from pydantic import ValidationError

import canonical_values
from canonical_values import CaddyConfiguration, CanonicalValuesError, DNSSettings, ForgejoRunnerConfiguration, HermesConfiguration, ImageChecksum, ImageDefinition, InfisicalConfiguration, InfisicalOnrampConfiguration, PlatformDNS, PlatformImages, ResourceNetwork, ServiceEndpoints, ServiceRelease, SearxngConfiguration, TailscaleConfiguration, TechnitiumConfiguration, load_site, model_digest, normalize_container_image_reference, normalized_model, redacted_summary
from canonical_projections import (
    ProjectionError,
    render_ansible_inventory,
    render_ansible_vars,
    render_dns_records,
    render_opentofu_variables,
)
from canonical_mapping import MappingContractError, MappingEntry, validate_mapping_matrix
from service_catalog import ServiceCatalogError, load_catalog


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
        volumes:
          data:
            type: directory
            target: /var/lib/forgejo
            backup: true
            read_only: true
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
    def test_bootstrap_ssh_policy_accepts_site_and_host_keys(self) -> None:
        site = canonical_values.YAML(typ="safe").load(VALID_SITE)
        site["bootstrap"] = {
            "ssh": {
                "user": "infra",
                "public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIsite site@example"],
                "host_additional_keys": {
                    "forgejo": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIhost host@example"],
                },
            }
        }

        model = canonical_values.CanonicalSite.model_validate(site)

        self.assertEqual(model.bootstrap.ssh.user, "infra")
        self.assertEqual(model.bootstrap.ssh.public_keys[0].split()[0], "ssh-ed25519")
        self.assertIn("forgejo", model.bootstrap.ssh.host_additional_keys)

    def test_bootstrap_ssh_keys_project_by_canonical_resource(self) -> None:
        site = canonical_values.YAML(typ="safe").load(VALID_SITE)
        site["bootstrap"] = {
            "ssh": {
                "user": "infra",
                "public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIsite site@example"],
                "host_additional_keys": {
                    "forgejo": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIhost host@example"],
                },
            }
        }
        model = canonical_values.CanonicalSite.model_validate(site)
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")

        tofu = render_opentofu_variables(model)
        inventory = render_ansible_inventory(model, catalog)

        self.assertEqual(tofu["bootstrap_ssh_user"], "infra")
        self.assertEqual(len(tofu["bootstrap_ssh_public_keys"]["forgejo"]), 2)
        hostvars = inventory["_meta"]["hostvars"][catalog.get("forgejo").inventory["host"]]
        self.assertEqual(hostvars["ansible_user"], "infra")
        self.assertEqual(hostvars["bootstrap_ssh_public_keys"], tofu["bootstrap_ssh_public_keys"]["forgejo"])

    def test_operator_policy_projects_separate_keys_and_pinned_dotfiles(self) -> None:
        site = canonical_values.YAML(typ="safe").load(VALID_SITE)
        site["operator"] = {
            "user": "systemboss",
            "ssh": {
                "public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIoperator operator@example"],
                "host_additional_keys": {
                    "forgejo": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIoperatorhost host@example"],
                },
            },
            "dotfiles": {
                "repository": "https://github.com/salverius-tech/dotfiles",
                "revision": "4aeeadd928b0d03090e5aa973d10d989e846cf15",
                "chezmoi": {
                    "version": "v2.71.1",
                    "sha256": "e1fb16c962644d57f4d451c324aa86163d00faf5d035500f41fb48943a66dfed",
                },
            },
        }
        model = canonical_values.CanonicalSite.model_validate(site)
        tofu = render_opentofu_variables(model)
        self.assertEqual(tofu["operator_user"], "systemboss")
        self.assertEqual(len(tofu["operator_ssh_public_keys"]["forgejo"]), 2)
        self.assertEqual(tofu["operator_dotfiles_revision"], "4aeeadd928b0d03090e5aa973d10d989e846cf15")
        self.assertEqual(tofu["operator_chezmoi_version"], "v2.71.1")

    def test_root_password_policy_defaults_to_automatic_site_inheritance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "dev"
            site_dir.mkdir()
            path = site_dir / "site.yaml"
            path.write_text(VALID_SITE, encoding="utf-8")
            model = load_site(path, expected_site="dev", catalog_path=Path(__file__).resolve().parents[1] / "infra" / "services.json")
        self.assertEqual(model.bootstrap.root_password.inheritance, "automatic")
        self.assertEqual(model.bootstrap.root_password.default_secret, "secrets.bootstrap.root_password")
        self.assertEqual(model.bootstrap.root_password.host_overrides, {})

    def test_root_password_policy_accepts_existing_resource_override(self) -> None:
        document = VALID_SITE.replace(
            "services:\n",
            "bootstrap:\n  root_password:\n    host_overrides:\n      forgejo: secrets.bootstrap.hosts.forgejo.root_password\nservices:\n",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "dev"
            site_dir.mkdir()
            path = site_dir / "site.yaml"
            path.write_text(document, encoding="utf-8")
            model = load_site(path, expected_site="dev", catalog_path=Path(__file__).resolve().parents[1] / "infra" / "services.json")
        self.assertEqual(
            model.bootstrap.root_password.host_overrides["forgejo"],
            "secrets.bootstrap.hosts.forgejo.root_password",
        )

    def test_root_password_policy_rejects_unknown_resource_override(self) -> None:
        document = VALID_SITE.replace(
            "services:\n",
            "bootstrap:\n  root_password:\n    host_overrides:\n      missing: secrets.bootstrap.hosts.missing.root_password\nservices:\n",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "dev"
            site_dir.mkdir()
            path = site_dir / "site.yaml"
            path.write_text(document, encoding="utf-8")
            with self.assertRaises(CanonicalValuesError):
                load_site(path, expected_site="dev", catalog_path=Path(__file__).resolve().parents[1] / "infra" / "services.json")

    def test_service_configuration_registry_covers_typed_services(self) -> None:
        self.assertEqual(
            set(canonical_values.SERVICE_CONFIGURATION_MODELS),
            {"forgejo", "forgejo_runner", "hermes", "infisical", "infisical_onramp", "searxng_onramp", "tailscale_client", "technitium"},
        )
        for name, model in canonical_values.SERVICE_CONFIGURATION_MODELS.items():
            with self.subTest(service=name):
                with self.assertRaises(ValidationError):
                    model.model_validate({"unknown_field": True})

    def test_infisical_onramp_configuration_validates_deployment_contract(self) -> None:
        configuration = InfisicalOnrampConfiguration.model_validate(
            {
                "base_dir": "/srv/infisical",
                "container_port": 8081,
                "bind_address": "127.0.0.1",
                "compose_provider_command": "podman-compose",
                "version": "v1.2.3",
                "postgres_user": "infisical",
                "postgres_db": "infisical",
                "required_packages": ["podman", "curl"],
            }
        )
        self.assertEqual(configuration.container_port, 8081)
        for field, value in (
            ("base_dir", "../infisical"),
            ("bind_address", "0.0.0.0"),
            ("compose_provider_command", "podman compose"),
            ("postgres_user", "bad-user"),
            ("required_packages", ["podman", "podman"]),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    InfisicalOnrampConfiguration.model_validate({field: value})

        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        contract = canonical_values.service_configuration_contract(
            set(catalog.names),
            {name: catalog.get(name).configuration_schema for name in catalog.names},
        )
        self.assertEqual(set(contract), set(catalog.names))
        self.assertEqual(contract["infisical_onramp"]["kind"], "typed-model")
        self.assertEqual(contract["infisical_onramp"]["model"], "InfisicalOnrampConfiguration")
        self.assertEqual(contract["onramp_host"]["kind"], "resource-owned")
        self.assertEqual(contract["onramp_host"]["schema"], "ResourceOwnedConfiguration")
        self.assertEqual(contract["forgejo"]["kind"], "typed-model")
        with self.assertRaises(CanonicalValuesError):
            canonical_values.service_configuration_contract(set(catalog.names) | {"new_service"})
        with self.assertRaises(CanonicalValuesError):
            canonical_values.service_configuration_contract(set(catalog.names) - {"technitium"})

    def test_public_service_configuration_fixture_matches_registry(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "scaffold" / "fixtures" / "service-configurations.yaml"
        yaml = canonical_values.YAML(typ="safe")
        document = yaml.load(fixture.read_text(encoding="utf-8"))
        self.assertIsInstance(document, dict)
        services = document["services"]
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "infra" / "services.json")
        contract = canonical_values.service_configuration_contract(set(catalog.names))
        self.assertEqual(set(services), set(contract))
        for name, entry in services.items():
            with self.subTest(service=name):
                self.assertIsInstance(entry, dict)
                if contract[name]["kind"] == "typed-model":
                    self.assertIn("configuration", entry)
                    model = canonical_values.SERVICE_CONFIGURATION_MODELS[name]
                    model.model_validate(entry["configuration"])
                else:
                    self.assertEqual(entry["resource_owned"]["owner"], contract[name]["owner"])

    def test_public_scaffold_declares_every_catalog_service(self) -> None:
        root = Path(__file__).resolve().parents[1]
        catalog = load_catalog(root / "infra" / "services.json")
        site = load_site(root / "scaffold" / "sites" / "dev" / "site.yaml", expected_site="dev", catalog_path=root / "infra" / "services.json")
        self.assertEqual(set(site.services), set(catalog.names))
        self.assertEqual({name for name, service in site.services.items() if service.enabled}, {"forgejo", "technitium"})

        fixture = Path(__file__).resolve().parents[1] / "scaffold" / "fixtures" / "resource-runtime.yaml"
        yaml = canonical_values.YAML(typ="safe")
        document = yaml.load(fixture.read_text(encoding="utf-8"))
        resources = canonical_values.Resources.model_validate(document)
        self.assertEqual(set(resources.guests), {"example-lxc", "example-vm"})
        self.assertEqual(set(resources.shared_hosts), {"onramp-host"})
        self.assertEqual(resources.guests["example-lxc"].type, "lxc")
        self.assertTrue(resources.guests["example-lxc"].runtime.unprivileged)
        self.assertEqual(resources.guests["example-vm"].type, "vm")
        self.assertEqual(resources.guests["example-vm"].runtime.firmware, "uefi")
        self.assertEqual(resources.shared_hosts["onramp-host"].security.deploy_user, "operator")

        invalid_vm = document["guests"]["example-vm"].copy()
        invalid_vm["runtime"] = {"unprivileged": True}
        invalid = {"guests": {"bad-vm": invalid_vm}, "shared_hosts": {}}
        with self.assertRaises(ValidationError):
            canonical_values.Resources.model_validate(invalid)

    def test_service_state_policy_is_explicit_for_stateful_and_stateless_services(self) -> None:
        stateful = canonical_values.ServiceState.model_validate({"capable": True, "disable_policy": "retain"})
        self.assertTrue(stateful.capable)
        with self.assertRaises(ValidationError):
            canonical_values.ServiceState.model_validate({"capable": True})
        with self.assertRaises(ValidationError):
            canonical_values.ServiceState.model_validate({"capable": False, "disable_policy": "retain"})
        with self.assertRaises(ValidationError):
            canonical_values.ServiceState.model_validate({"capable": False, "backup": {"retention_days": 7}})

    def _full_catalog_site_document(self) -> dict:
        root = Path(__file__).resolve().parents[1]
        yaml = canonical_values.YAML(typ="safe")
        site = yaml.load((root / "scaffold/sites/dev/site.yaml").read_text(encoding="utf-8"))
        site["resources"] = yaml.load((root / "scaffold/fixtures/resource-runtime.yaml").read_text(encoding="utf-8"))
        site["services"] = yaml.load((root / "scaffold/fixtures/full-catalog-services.yaml").read_text(encoding="utf-8"))["services"]
        return site

    def test_full_catalog_fixture_loads_as_one_valid_canonical_site(self) -> None:
        root = Path(__file__).resolve().parents[1]
        site = self._full_catalog_site_document()
        canonical = canonical_values.CanonicalSite.model_validate(site)
        catalog = load_catalog(root / "infra/services.json")
        enabled = set(canonical.services)
        catalog.validate_selection(enabled)
        catalog.validate_model_services(canonical.services, canonical.resources)
        validate_mapping_matrix(canonical)
        self.assertEqual(enabled, set(catalog.names))
        self.assertEqual(canonical.services["forgejo_runner"].dependencies, ["forgejo"])
        self.assertEqual(canonical.services["forgejo"].release.source, "package")
        self.assertEqual(canonical.services["forgejo"].overrides["ansible"]["forgejo_domain"], "git.example.internal")
        self.assertEqual(catalog.get("forgejo").required_fields, ("resource", "state.capable", "release.version"))
        self.assertEqual(catalog.get("technitium").required_fields, ("resource", "state.capable", "release.version", "release.checksum"))
        self.assertEqual(catalog.get("forgejo_runner").required_fields, ("resource", "configuration.url", "configuration.scope", "configuration.label"))
        self.assertEqual(canonical.services["searxng_onramp"].resource, "onramp-host")

    def test_full_catalog_cross_field_failure_matrix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        catalog = load_catalog(root / "infra/services.json")
        cases = {
            "stateful_missing_disable_policy": lambda site: site["services"]["forgejo"]["state"].update(
                {"capable": True, "disable_policy": None}
            ),
            "enabled_service_missing_resource": lambda site: site["services"]["forgejo"].update({"resource": None}),
            "stateful_service_missing_state_capability": lambda site: site["services"]["forgejo"].update({"state": {"capable": False}}),
            "service_missing_release_version": lambda site: site["services"]["forgejo"]["release"].update({"version": None}),
            "runner_missing_registration_url": lambda site: site["services"]["forgejo_runner"]["configuration"].update({"url": None}),
            "unknown_service_resource": lambda site: site["services"]["forgejo"].update({"resource": "missing"}),
            "stateless_service_claims_state": lambda site: site["services"]["tailscale_client"].update(
                {"state": {"capable": True, "disable_policy": "retain"}}
            ),
            "resource_owned_release": lambda site: site["services"]["onramp_host"].update(
                {"release": {"source": "package", "version": "1.0.0"}}
            ),
            "unknown_override_namespace": lambda site: site["services"]["forgejo"].update(
                {"overrides": {"runtime": {"debug": True}}}
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                site = self._full_catalog_site_document()
                mutate(site)
                with self.assertRaises((ValidationError, ServiceCatalogError)):
                    canonical = canonical_values.CanonicalSite.model_validate(site)
                    catalog.validate_model_services(canonical.services, canonical.resources)

        missing_dependency = self._full_catalog_site_document()
        missing_dependency["services"]["forgejo"]["enabled"] = False
        with self.assertRaises(ServiceCatalogError):
            catalog.validate_selection({name for name, service in missing_dependency["services"].items() if service["enabled"]})

        canonical = canonical_values.CanonicalSite.model_validate(self._full_catalog_site_document())
        canonical.services["forgejo"].resource = None
        with self.assertRaises(ServiceCatalogError):
            catalog.validate_model_services(canonical.services, canonical.resources)

    def test_mapping_matrix_required_paths_fail_closed(self) -> None:
        canonical = canonical_values.CanonicalSite.model_validate(self._full_catalog_site_document())
        canonical.services["forgejo"].resource = None
        with self.assertRaises(MappingContractError):
            validate_mapping_matrix(
                canonical,
                (MappingEntry("services.forgejo.resource", ("opentofu",), "derived", required=True),),
            )

    def test_ssh_port_requires_ssh_protocol(self) -> None:
        with self.assertRaises(ValidationError):
            ServiceEndpoints.model_validate({"ports": {"ssh": 22}})

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

    def test_technitium_non_secret_configuration_is_typed(self) -> None:
        configuration = TechnitiumConfiguration.model_validate(
            {"api_url": "http://192.0.2.53:5380/", "admin_user": "admin"}
        )
        self.assertEqual(configuration.admin_user, "admin")

    def test_technitium_caddy_configuration_is_typed_and_normalized(self) -> None:
        configuration = CaddyConfiguration.model_validate(
            {
                "server_names": ["DNS.Example.Internal."],
                "upstream": {"host": "127.0.0.1", "port": 5380},
                "tls": {"dns_provider": "cloudflare"},
                "extra_vhosts": [],
            }
        )
        self.assertEqual(configuration.server_names, ["dns.example.internal"])
        self.assertEqual(configuration.upstream.port, 5380)
        with self.assertRaises(ValueError):
            CaddyConfiguration.model_validate(
                {"server_names": ["dns.example.internal", "DNS.example.internal"], "upstream": {"host": "127.0.0.1", "port": 5380}, "tls": {"dns_provider": "cloudflare"}}
            )


    def test_searxng_non_secret_configuration_is_typed(self) -> None:
        configuration = SearxngConfiguration.model_validate(
            {"container_port": 8080, "bind_address": "127.0.0.1", "instance_name": "Search", "enable_public_url": True}
        )
        self.assertEqual(configuration.container_port, 8080)
        with self.assertRaises(ValueError):
            SearxngConfiguration.model_validate({"bind_address": "0.0.0.0"})

    def test_forgejo_runner_non_secret_configuration_is_typed(self) -> None:
        configuration = ForgejoRunnerConfiguration.model_validate(
            {
                "url": "https://git.example.internal/",
                "name": "homelab-deploy",
                "scope": "owner/repository",
                "label": "homelab-deploy",
                "labels": ["homelab-deploy:host"],
                "hosts": [{"name": "git", "address": "192.0.2.62"}],
            }
        )
        self.assertEqual(configuration.scope, "owner/repository")
        self.assertEqual(configuration.hosts[0].address, "192.0.2.62")

    def test_tailscale_non_secret_configuration_is_typed(self) -> None:
        configuration = TailscaleConfiguration.model_validate(
            {"restore_backup": True, "backup_archive": "backups/tailscale.tgz", "enable_ip_forwarding": True, "up_args": ["--accept-dns=false"]}
        )
        self.assertTrue(configuration.restore_backup)
        self.assertEqual(configuration.up_args, ["--accept-dns=false"])

    def test_infisical_non_secret_configuration_is_typed(self) -> None:
        configuration = InfisicalConfiguration.model_validate(
            {"data_dir": "/var/lib/infisical", "postgres_user": "infisical", "postgres_db": "infisical"}
        )
        self.assertEqual(configuration.data_dir, "/var/lib/infisical")
        self.assertEqual(configuration.postgres_user, "infisical")

    def test_resource_owned_service_configuration_is_rejected(self) -> None:
        content = VALID_SITE.replace(
            "services:\n  forgejo:",
            "services:\n  onramp_host:\n    enabled: false\n    configuration:\n      unsafe: true\n  forgejo:",
        )
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content))

    def test_forgejo_database_is_typed_and_projected(self) -> None:
        content = VALID_SITE.replace(
            "    release:\n",
            "    configuration:\n      database:\n        type: postgres\n        name: forgejo_db\n        user: forgejo_user\n    release:\n",
        )
        model = load_site(self.write_site(content))
        values = render_opentofu_variables(model)
        self.assertEqual(values["forgejo_database"]["type"], "postgres")
        self.assertEqual(values["forgejo_database"]["name"], "forgejo_db")
        with self.assertRaises(CanonicalValuesError):
            load_site(self.write_site(content.replace("forgejo_db", "bad-name")))

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

    def test_service_storage_projection_preserves_typed_volume_fields(self) -> None:
        model = load_site(self.write_site(VALID_SITE))
        values = render_opentofu_variables(model)
        self.assertEqual(
            values["service_storage"]["forgejo"]["data"],
            {
                "type": "directory",
                "storage_id": None,
                "size_gb": None,
                "target": "/var/lib/forgejo",
                "backup": True,
                "read_only": True,
            },
        )

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
        with self.assertRaisesRegex(CanonicalValuesError, "services.forgejo.configuration"):
            load_site(self.write_site(content))

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

    def test_technitium_release_fields_project_to_ansible_compatibility_vars(self) -> None:
        content = (
            VALID_SITE.replace("forgejo", "technitium")
            .replace("git.example.internal", "dns.example.internal")
            .replace("12.0.4", "15.2.0")
            .replace(
                "      version: 15.2.0",
                "      version: 15.2.0\n      checksum: " + "a" * 64,
            )
        )
        site_path = self.write_site(content)
        catalog_path = Path(__file__).resolve().parents[1] / "infra" / "services.json"
        model = load_site(site_path, catalog_path=catalog_path)
        catalog = load_catalog(catalog_path)
        ansible_vars = render_ansible_vars(model, catalog)
        legacy_vars = ansible_vars["services"]["technitium"]["legacy_vars"]
        self.assertEqual(legacy_vars["technitium_discovery_version"], "15.2.0")
        self.assertEqual(legacy_vars["technitium_portable_sha256"], "a" * 64)

    def test_infisical_scalar_fields_project_to_ansible_compatibility_vars(self) -> None:
        content = VALID_SITE.replace(
            "  forgejo:\n    enabled: true",
            "  infisical:\n"
            "    enabled: true\n"
            "    resource: forgejo\n"
            "    state:\n"
            "      capable: true\n"
            "      disable_policy: retain\n"
            "    configuration:\n"
            "      data_dir: /var/lib/infisical\n"
            "      postgres_user: infisical\n"
            "      postgres_db: infisical\n"
            "    endpoints:\n"
            "      public_names: [infisical.example.internal]\n"
            "    release:\n"
            "      version: 'v0.162.3@sha256:" + "a" * 64 + "'\n"
            "  forgejo:\n    enabled: true",
        )
        site_path = self.write_site(content)
        catalog_path = Path(__file__).resolve().parents[1] / "infra" / "services.json"
        model = load_site(site_path, catalog_path=catalog_path)
        catalog = load_catalog(catalog_path)
        ansible_vars = render_ansible_vars(model, catalog)
        legacy_vars = ansible_vars["services"]["infisical"]["legacy_vars"]
        self.assertEqual(legacy_vars["infisical_data_dir"], "/var/lib/infisical")
        self.assertEqual(legacy_vars["infisical_postgres_user"], "infisical")
        self.assertEqual(legacy_vars["infisical_postgres_db"], "infisical")
        self.assertEqual(legacy_vars["infisical_domain"], "infisical.example.internal")
        self.assertEqual(legacy_vars["infisical_version"], "v0.162.3@sha256:" + "a" * 64)

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


    def test_general_dns_contract_projects_owned_records_and_settings(self) -> None:
        model = load_site(
            self.write_site(VALID_SITE.replace(
                "      visibility: internal",
                "      visibility: internal\n      dns:\n        enabled: true\n        record_type: A",
            )),
            catalog_path=Path(__file__).resolve().parents[1] / "infra" / "services.json",
        )
        model.platform.dns = PlatformDNS(
            enabled=True,
            settings=DNSSettings(
                forwarders=["resolver.example.internal (192.0.2.1:53)"],
                forwarder_protocol="Tls",
                concurrent_forwarding=False,
                dnssec_validation=True,
                prefer_ipv6=False,
            ),
            zones={"Example.Internal.": ["192.0.2.10:54"]},
            a_records={"static.Example.Internal.": "192.0.2.80"},
            cname_records={"www.Example.Internal.": "proxy.example.internal."},
        )
        dns = render_dns_records(model)
        self.assertEqual(dns["zones"], {"example.internal": ["192.0.2.10:54"]})
        self.assertEqual(dns["a_records"]["static.example.internal"], "192.0.2.80")
        self.assertEqual(dns["a_records"]["git.example.internal"], "192.0.2.62")
        self.assertEqual(dns["cname_records"], {"www.example.internal": "proxy.example.internal"})
        self.assertEqual(dns["settings"]["forwarderProtocol"], "Tls")

    def test_general_dns_contract_rejects_overlap_and_out_of_zone_records(self) -> None:
        with self.assertRaises(ValueError):
            PlatformDNS(
                enabled=True,
                settings=DNSSettings(
                    forwarders=["192.0.2.1:53"],
                    forwarder_protocol="Udp",
                    concurrent_forwarding=False,
                    dnssec_validation=True,
                    prefer_ipv6=False,
                ),
                zones={"example.internal": ["192.0.2.10:54"]},
                a_records={"same.example.internal": "192.0.2.80"},
                cname_records={"same.example.internal": "target.example.internal"},
            )
        with self.assertRaises(ValueError):
            PlatformDNS(
                enabled=True,
                settings=DNSSettings(
                    forwarders=["192.0.2.1:53"],
                    forwarder_protocol="Udp",
                    concurrent_forwarding=False,
                    dnssec_validation=True,
                    prefer_ipv6=False,
                ),
                zones={"example.internal": ["192.0.2.10:54"]},
                a_records={"outside.other.internal": "192.0.2.80"},
            )

    def test_general_dns_projection_rejects_derived_target_conflict(self) -> None:
        model = load_site(
            self.write_site(VALID_SITE.replace(
                "      visibility: internal",
                "      visibility: internal\n      dns:\n        enabled: true\n        record_type: A",
            )),
            catalog_path=Path(__file__).resolve().parents[1] / "infra" / "services.json",
        )
        model.platform.dns = PlatformDNS(
            enabled=True,
            settings=DNSSettings(
                forwarders=["192.0.2.1:53"],
                forwarder_protocol="Udp",
                concurrent_forwarding=False,
                dnssec_validation=True,
                prefer_ipv6=False,
            ),
            zones={"example.internal": ["192.0.2.10:54"]},
            a_records={"git.example.internal": "192.0.2.63"},
        )
        with self.assertRaises(ProjectionError):
            render_dns_records(model)

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

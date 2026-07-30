from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from canonical_projections import _compatibility_value, _resource_variables, render_ansible_inventory, render_ansible_vars, render_opentofu_variables
from canonical_values import HermesConfiguration, Service, load_site
from service_catalog import load_catalog


ROOT = Path(__file__).resolve().parents[1]


class CanonicalAnsibleProjectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_site(ROOT / "scaffold/sites/dev/site.yaml", catalog_path=ROOT / "infra/services.json")
        cls.catalog = load_catalog(ROOT / "infra/services.json")

    def test_inventory_has_consistent_catalog_owned_enabled_service_hosts(self) -> None:
        inventory = render_ansible_inventory(self.model, self.catalog)
        hostvars = inventory["_meta"]["hostvars"]
        enabled = {name for name, service in self.model.services.items() if service.enabled}
        self.assertEqual(set(inventory["all"]["children"]), {self.catalog.get(name).inventory["group"] for name in enabled})
        for name in enabled:
            capability = self.catalog.get(name)
            host = capability.inventory["host"]
            group = capability.inventory["group"]
            self.assertIn(host, hostvars)
            self.assertIn(host, inventory[group]["hosts"])
            self.assertEqual(hostvars[host]["canonical_service"], name)
            self.assertEqual(hostvars[host]["canonical_site"], "dev")

    def test_vars_projection_contains_enabled_services_only_and_preserves_ownership(self) -> None:
        projected = render_ansible_vars(self.model, self.catalog)
        enabled = {name for name, service in self.model.services.items() if service.enabled}
        self.assertEqual(set(projected["services"]), enabled)
        self.assertEqual(projected["canonical_site"], "dev")
        for name in enabled:
            service = self.model.services[name]
            self.assertEqual(projected["services"][name]["resource"], service.resource)
            resource = self.model.resources.guests.get(service.resource) or self.model.resources.shared_hosts.get(service.resource)
            self.assertEqual(projected["services"][name]["resource_type"], resource.type)
            self.assertIn("endpoints", projected["services"][name])
            self.assertIn("release", projected["services"][name])

    def test_catalog_owned_release_compatibility_flattens_non_secret_technitium_vars(self) -> None:
        model = self.model.model_copy(deep=True)
        model.services["technitium"].release = model.services["technitium"].release.model_copy(
            update={"version": "14.0.0", "checksum": "a" * 64, "source": "binary"}
        )
        projected = render_ansible_vars(model, self.catalog)
        self.assertEqual(
            projected["services"]["technitium"]["legacy_vars"],
            {"technitium_discovery_version": "14.0.0", "technitium_portable_sha256": "a" * 64},
        )

    def test_onramp_root_datastore_projects_from_typed_resource_storage(self) -> None:
        resource = self.model.resources.guests["forgejo"]
        projected = _resource_variables("onramp_host", resource)
        self.assertEqual(projected["onramp_host_datastore_id"], resource.storage.root.storage_id)

    def test_enabled_hermes_control_renders_all_non_secret_fields_report_only(self) -> None:
        model = self.model.model_copy(deep=True)
        configuration = HermesConfiguration.model_validate(
            {
                "control": {
                    "enabled": True,
                    "domain": "control.example.internal",
                    "source_url": "https://github.com/example/control.git",
                    "source_ref": "a" * 40,
                },
                "runtime_user": "anvil",
                "repository_path": "/srv/homelab-infra",
                "allow_legacy_runtime": False,
                "tuning": {"compression_threshold": 0.7, "max_concurrent_children": 2, "max_spawn_depth": 1},
                "node": {"version": "22.0.0", "checksums": {"amd64": "b" * 64, "arm64": "c" * 64}},
                "dashboard": {"enabled": False, "host": "127.0.0.1", "auth_username": "admin"},
                "web": {"searxng_url": "http://127.0.0.1:8080"},
            }
        ).model_dump(mode="json", exclude_none=True)
        model.services["hermes"] = Service.model_validate(
            {
                "enabled": True,
                "resource": "forgejo",
                "endpoints": {"ports": {"dashboard": 8080}},
                "release": {"version": "1.0.0", "tag": "v2026.7.1", "commit": "d" * 40, "checksum": "e" * 64},
                "configuration": configuration,
            }
        )
        projected = render_ansible_vars(model, self.catalog)["services"]["hermes"]["legacy_vars"]
        self.assertEqual(
            {key: projected[key] for key in projected if key.startswith("hermes_control_")},
            {
                "hermes_control_enabled": True,
                "hermes_control_domain": "control.example.internal",
                "hermes_control_source_url": "https://github.com/example/control.git",
                "hermes_control_source_ref": "a" * 40,
                "hermes_control_api_host": "127.0.0.1",
                "hermes_control_api_port": 8787,
                "hermes_control_require_task_approval": True,
                "hermes_control_plugin_socket": "/run/hermes/control-extension.sock",
            },
        )
        self.assertNotIn("control_api_token", repr(projected))
        self.assertNotIn("control_bridge_token", repr(projected))
        self.assertNotIn("password_hash", repr(projected))
        self.assertNotIn("basic_auth_secret", repr(projected))

        mapping = self.catalog.get("forgejo").inventory["canonical_play_vars"]
        self.assertEqual(
            mapping,
            {
                "forgejo_domain": "endpoints.public_names.0",
                "forgejo_ssh_port": "endpoints.ports.ssh",
                "forgejo_version": "release.version",
                "forgejo_database": "configuration.database",
                "forgejo_enable_caddy": "configuration.enable_caddy",
                "forgejo_configure_system_ssh": "configuration.configure_system_ssh",
                "forgejo_write_initial_config": "configuration.write_initial_config",
                "forgejo_bootstrap_enabled": "configuration.bootstrap_enabled",
                "forgejo_bootstrap_admin_username": "configuration.bootstrap_admin_username",
                "forgejo_bootstrap_admin_email": "configuration.bootstrap_admin_email",
                "forgejo_bootstrap_owner_email": "configuration.bootstrap_owner_email",
                "forgejo_actions_enabled": "configuration.actions_enabled",
                "forgejo_actions_default_url": "configuration.actions_default_url",
            },
        )
        model = self.model.model_copy(deep=True)
        model.services["forgejo"].release = model.services["forgejo"].release.model_copy(update={"version": "10.0.0"})
        projected = render_ansible_vars(model, self.catalog)
        self.assertEqual(
            projected["services"]["forgejo"]["legacy_vars"],
            {
                "forgejo_domain": "git.example.internal",
                "forgejo_ssh_port": 22,
                "forgejo_version": "10.0.0",
                "forgejo_database": {
                    "type": "sqlite",
                    "managed": True,
                    "host": "127.0.0.1",
                    "port": 5432,
                    "name": "forgejo",
                    "user": "forgejo",
                    "ssl_mode": "disable",
                },
            },
        )

        mapping = self.catalog.get("hermes").inventory["canonical_play_vars"]
        self.assertEqual(mapping["hermes_runtime_user"], "configuration.runtime_user")
        self.assertEqual(mapping["hermes_repo_path"], "configuration.repository_path")
        self.assertEqual(mapping["hermes_control_enabled"], "configuration.control.enabled")
        self.assertEqual(mapping["hermes_control_domain"], "configuration.control.domain")
        self.assertEqual(mapping["hermes_control_source_url"], "configuration.control.source_url")
        self.assertEqual(mapping["hermes_control_source_ref"], "configuration.control.source_ref")
        self.assertEqual(mapping["hermes_control_api_host"], "configuration.control.api_host")
        self.assertEqual(mapping["hermes_control_api_port"], "configuration.control.api_port")
        self.assertEqual(mapping["hermes_control_require_task_approval"], "configuration.control.require_task_approval")
        self.assertEqual(mapping["hermes_control_plugin_socket"], "configuration.control.plugin_socket")
        self.assertEqual(
            set(self.catalog.get("hermes").conditional_required_secrets),
            {"configuration.control.enabled", "configuration.dashboard.enabled"},
        )
        self.assertEqual(
            set(self.catalog.get("hermes").required_secrets),
            {
                "services.hermes.secrets.control_api_token",
                "services.hermes.secrets.control_bridge_token",
                "services.hermes.secrets.dashboard_basic_auth_password_hash",
                "services.hermes.secrets.dashboard_basic_auth_secret",
            },
        )
        self.assertEqual(mapping["hermes_runtime_passwordless_sudo"], "resource.security.allow_passwordless_sudo")

        self.assertEqual(mapping["hermes_discovery_tag"], "release.tag")
        self.assertEqual(mapping["hermes_discovery_commit"], "release.commit")
        self.assertEqual(mapping["hermes_node_sha256_arm64"], "configuration.node.checksums.arm64")
        service = type("Service", (), {"configuration": {"runtime_user": "anvil", "repository_path": "/srv/homelab-infra"}, "release": type("Release", (), {"tag": "v2026.7.1"})()})()
        resource = type("Resource", (), {"security": type("Security", (), {"allow_passwordless_sudo": False})()})()
        self.assertEqual(_compatibility_value(service, resource, "configuration.runtime_user"), "anvil")
        self.assertEqual(_compatibility_value(service, resource, "configuration.repository_path"), "/srv/homelab-infra")
        self.assertFalse(_compatibility_value(service, resource, "resource.security.allow_passwordless_sudo"))

    def test_inventory_and_vars_projections_share_service_identity(self) -> None:
        inventory = render_ansible_inventory(self.model, self.catalog)
        variables = render_ansible_vars(self.model, self.catalog)
        hostvars = inventory["_meta"]["hostvars"]
        for name, service_vars in variables["services"].items():
            capability = self.catalog.get(name)
            host = capability.inventory["host"]
            identity = hostvars[host]
            self.assertEqual(identity["canonical_site"], variables["canonical_site"])
            self.assertEqual(identity["canonical_service"], name)
            self.assertEqual(identity["canonical_resource"], service_vars["resource"])
            self.assertEqual(identity["service_runtime_current"]["type"], service_vars["resource_type"])

    def test_forgejo_public_name_has_paired_ansible_and_opentofu_transport(self) -> None:
        ansible = render_ansible_vars(self.model, self.catalog)
        tofu = render_opentofu_variables(self.model)
        self.assertEqual(ansible["services"]["forgejo"]["legacy_vars"]["forgejo_domain"], "git.example.internal")
        self.assertEqual(tofu["forgejo_server_name"], "git.example.internal")

    def test_projection_does_not_emit_sensitive_sentinel(self) -> None:
        inventory = render_ansible_inventory(self.model, self.catalog)
        variables = render_ansible_vars(self.model, self.catalog)
        self.assertNotIn("REPLACE_SECRET", repr((inventory, variables)))


if __name__ == "__main__":
    unittest.main()

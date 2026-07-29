from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "canonical_mapping_inventory",
    ROOT / "scripts" / "canonical-mapping-inventory.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CanonicalMappingInventoryTests(unittest.TestCase):
    def test_current_sources_are_fully_classified(self) -> None:
        report = MODULE.build_report(ROOT)

        self.assertEqual(report["opentofu"]["variable_count"], 182)
        self.assertEqual(len(report["opentofu"]["variables"]), 182)
        self.assertEqual(report["classification"]["unclassified_variables"], [])
        self.assertEqual(len(report["service_catalog"]["services"]), 9)
        self.assertEqual(report["source_inventory"]["source_count"], 16)
        self.assertTrue(report["source_inventory"]["coverage"]["source_files_present"])
        self.assertEqual(report["source_inventory"]["coverage"]["opentofu_variables_inventoried"], 182)
        self.assertGreater(report["source_inventory"]["scaffold"]["terraform_assignment_count"], 0)
        self.assertIn("a_records", report["source_inventory"]["scaffold"]["dns"]["top_level_keys"])
        self.assertIn("tf_vmid", report["source_inventory"]["ansible"]["inventory_fields"])
        self.assertEqual(report["source_inputs"]["input_count"], 387)
        self.assertEqual(report["source_inputs"]["unique_identities"], 387)
        self.assertEqual(
            set(report["source_inputs"]["disposition_counts"]),
            {"ansible-only", "deprecated", "unsupported"},
        )
        self.assertEqual(report["source_inputs"]["status"], "classification-complete-with-review-dispositions")
        self.assertEqual(report["mapping_matrix"]["row_count"], 212)
        self.assertEqual(report["mapping_matrix"]["status"], "semantic-coverage-incomplete")
        self.assertEqual(report["matrix_coverage"]["input_count"], 387)
        self.assertEqual(report["matrix_coverage"]["matched_count"] + report["matrix_coverage"]["unmatched_count"], 387)
        self.assertEqual(report["matrix_coverage"]["matched_count"], 224)
        self.assertEqual(report["matrix_coverage"]["unmatched_count"], 163)
        self.assertEqual(report["matrix_coverage"]["status"], "review-required")
        self.assertTrue(report["matrix_coverage"]["unmatched"])
        deferred = report["deferred_classification"]
        self.assertEqual(deferred["item_count"], 163)
        self.assertEqual(deferred["unclassified_count"], 0)
        self.assertEqual(
            set(deferred["counts"]),
            {
                "ambiguous-or-destructive",
                "behavior-without-typed-owner",
                "migration-only-or-unsupported",
                "secret-or-protected",
            },
        )
        self.assertEqual(sum(deferred["counts"].values()), 163)
        self.assertIn(
            {"source": "scripts/migrate-values.py", "key": "FORGEJO_VERSION", "canonical_path": "services.forgejo.release.version"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "onramp_host_datastore_id", "canonical_path": "resources.shared_hosts.onramp_host.storage.root.storage_id"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "forgejo_runner_mac_address", "canonical_path": "resources.guests.forgejo_runner.network.mac_address"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scripts/migrate-values.py", "key": "technitium_container_vmid", "canonical_path": "resources.guests.technitium.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "forgejo_container_vmid", "canonical_path": "resources.guests.forgejo.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "infisical_container_vmid", "canonical_path": "resources.guests.infisical.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "hermes_container_vmid", "canonical_path": "resources.guests.hermes.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "technitium_container_disk_gb", "canonical_path": "resources.guests.technitium.storage.root.size_gb"},
            report["matrix_coverage"]["matched"],
        )
        self.assertFalse(
            any(item["key"] in {"settings", "a_records", "zones", "cname_records"} for item in report["matrix_coverage"]["matched"]),
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "onramp_host_vmid", "canonical_path": "resources.shared_hosts.onramp_host.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "forgejo_runner_vmid", "canonical_path": "resources.guests.forgejo_runner.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "tailscale_client_vmid", "canonical_path": "resources.guests.tailscale_client.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        for key, canonical_path in (
            ("forgejo_runner_started", "resources.guests.forgejo_runner.runtime.started"),
            ("forgejo_runner_start_on_boot", "resources.guests.forgejo_runner.runtime.start_on_boot"),
            ("infisical_started", "resources.guests.infisical.runtime.started"),
            ("infisical_start_on_boot", "resources.guests.infisical.runtime.start_on_boot"),
            ("hermes_started", "resources.guests.hermes.runtime.started"),
            ("hermes_start_on_boot", "resources.guests.hermes.runtime.start_on_boot"),
            ("tailscale_client_started", "resources.guests.tailscale_client.runtime.started"),
            ("tailscale_client_start_on_boot", "resources.guests.tailscale_client.runtime.start_on_boot"),
            ("onramp_host_started", "resources.shared_hosts.onramp_host.runtime.started"),
            ("onramp_host_start_on_boot", "resources.shared_hosts.onramp_host.runtime.start_on_boot"),
        ):
            with self.subTest(key=key):
                self.assertIn(
                    {"source": "scaffold/terraform.tfvars", "key": key, "canonical_path": canonical_path},
                    report["matrix_coverage"]["matched"],
                )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "searxng_container_image", "canonical_path": "services.searxng_onramp.release"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/ansible/inventory/local.yml", "key": "technitium_vmid", "canonical_path": "resources.guests.technitium.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scaffold/ansible/inventory/local.yml", "key": "forgejo_vmid", "canonical_path": "resources.guests.forgejo.identity.vmid"},
            report["matrix_coverage"]["matched"],
        )
        for source, key, canonical_path in (
            ("scaffold/ansible/inventory/local.yml", "forgejo_domain", "services.forgejo.endpoints.public_names"),
            ("scripts/migrate-values.py", "FORGEJO_DOMAIN", "services.forgejo.endpoints.public_names"),
            ("scripts/migrate-values.py", "forgejo_domain", "services.forgejo.endpoints.public_names"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_ssh_port", "services.forgejo.endpoints.ports.ssh"),
            ("scripts/migrate-values.py", "FORGEJO_SSH_PORT", "services.forgejo.endpoints.ports.ssh"),
            ("scripts/migrate-values.py", "forgejo_ssh_port", "services.forgejo.endpoints.ports.ssh"),
        ):
            self.assertIn(
                {"source": source, "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        for source, key, canonical_path in (
            ("scaffold/ansible/inventory/local.yml", "infisical_domain", "services.infisical.endpoints.public_names"),
            ("scaffold/ansible/inventory/local.yml", "hermes_domain", "services.hermes.endpoints.public_names"),
        ):
            self.assertIn(
                {"source": source, "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        for key, canonical_path in (
            ("infisical_vmid", "resources.guests.infisical.identity.vmid"),
            ("hermes_vmid", "resources.guests.hermes.identity.vmid"),
        ):
            self.assertIn(
                {"source": "scaffold/ansible/inventory/local.yml", "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        for key in (
            "settings",
            "zones",
            "a_records",
            "cname_records",
        ):
            self.assertIn(
                {"source": "scaffold/dns-records.local.json", "key": key},
                [{"source": x["source"], "key": x["key"]} for x in report["matrix_coverage"]["unmatched"]],
            )
        for key, canonical_path in (
            ("technitium_discovery_version", "services.technitium.release.version"),
            ("technitium_portable_sha256", "services.technitium.release.checksum"),
        ):
            self.assertIn(
                {"source": "scaffold/ansible/inventory/local.yml", "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        for key, canonical_path in (
            ("onramp_host_password_authentication", "resources.shared_hosts.onramp_host.security.password_authentication"),
            ("onramp_host_permit_root_login", "resources.shared_hosts.onramp_host.security.permit_root_login"),
            ("onramp_host_deploy_user", "resources.shared_hosts.onramp_host.security.deploy_user"),
            ("onramp_host_deploy_dir", "resources.shared_hosts.onramp_host.security.deploy_dir"),
            ("onramp_host_allow_passwordless_sudo", "resources.shared_hosts.onramp_host.security.allow_passwordless_sudo"),
            ("onramp_host_allowed_ssh_cidrs", "resources.shared_hosts.onramp_host.security.allowed_ssh_cidrs"),
        ):
            self.assertIn(
                {"source": "scaffold/terraform.tfvars", "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "onramp_host_ssh_public_keys"},
            [{"source": x["source"], "key": x["key"]} for x in report["matrix_coverage"]["unmatched"]],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "searxng_container_port"},
            [{"source": x["source"], "key": x["key"]} for x in report["matrix_coverage"]["unmatched"]],
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "searxng_bind_address"},
            [{"source": x["source"], "key": x["key"]} for x in report["matrix_coverage"]["unmatched"]],
        )
        for key, canonical_path in (
            ("guest_vm_image_datastore_id", "platform.images.vm.guest.datastore_id"),
            ("guest_vm_image_url", "platform.images.vm.guest.url"),
            ("guest_vm_image_file_name", "platform.images.vm.guest.file_name"),
            ("guest_vm_image_checksum_algorithm", "platform.images.vm.guest.checksum.algorithm"),
            ("guest_vm_image_checksum", "platform.images.vm.guest.checksum.value"),
            ("onramp_host_image_datastore_id", "platform.images.vm.onramp_host.datastore_id"),
            ("onramp_host_image_url", "platform.images.vm.onramp_host.url"),
            ("onramp_host_image_file_name", "platform.images.vm.onramp_host.file_name"),
            ("onramp_host_image_checksum_algorithm", "platform.images.vm.onramp_host.checksum.algorithm"),
            ("onramp_host_image_checksum", "platform.images.vm.onramp_host.checksum.value"),
        ):
            self.assertIn(
                {"source": "scaffold/terraform.tfvars", "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        for key, canonical_path in (
            ("hermes_runtime_passwordless_sudo", "resources.guests.hermes.security.allow_passwordless_sudo"),
            ("hermes_dashboard_port", "services.hermes.endpoints.ports.dashboard"),
            ("forgejo_root_url", "services.forgejo.endpoints.public_url"),
        ):
            self.assertIn(
                {"source": "scaffold/ansible/inventory/local.yml", "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        self.assertIn(
            {
                "source": "scaffold/terraform.tfvars",
                "key": "tailscale_client_mac_address",
                "canonical_path": "resources.guests.tailscale_client.network.mac_address",
            },
            report["matrix_coverage"]["matched"],
        )

        for source, key in (
            ("scaffold/terraform.tfvars", "tailscale_client_enabled"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runtime"),
            ("scaffold/ansible/inventory/local.yml", "tailscale_client_enabled"),
        ):
            self.assertIn(
                {"source": source, "key": key},
                [{"source": x["source"], "key": x["key"]} for x in report["matrix_coverage"]["unmatched"]],
            )
        self.assertEqual(len(report["service_contracts"]), 9)
        self.assertTrue(report["consumer_contract"]["legacy_terraform_input_present"])
        self.assertTrue(report["consumer_contract"]["legacy_static_inventory_present"])
        self.assertEqual(report["classification"]["inventory_status"], "complete")
        self.assertEqual(report["classification"]["semantic_mapping_status"], "incomplete")
        self.assertEqual(report["classification"]["consumer_cutover_status"], "deferred")
        self.assertEqual(report["candidate_generation"]["status"], "blocked")
        aliases = report["legacy_alias_classification"]["ambiguous_resource_aliases"]
        self.assertEqual(len(aliases), 13)
        self.assertTrue(all(item["classification"] == "ambiguous" for item in aliases))
        provider_aliases = report["legacy_alias_classification"]["provider_secret_aliases"]
        self.assertEqual(len(provider_aliases), 2)
        self.assertEqual(
            {(item["source"], item["key"]) for item in provider_aliases},
            {
                ("scripts/migrate-values.py", "container_root_password"),
                ("scripts/migrate-values.py", "container_ssh_public_keys"),
            },
        )
        for item in provider_aliases:
            self.assertEqual(
                {item["classification"], item["scope"], item["canonical_owner"], item["reason"]},
                {
                    "secret-provider-input",
                    "provider-scoped",
                    "review-required",
                    "provider secret alias requires explicit delivery contract",
                },
            )
            self.assertNotIn("value", item)
        self.assertFalse(any(item["key"] == "container_vmid" for item in report["matrix_coverage"]["matched"]))
        self.assertFalse(report["candidate_generation"]["candidate_generation_allowed"])
        self.assertIn("matrix coverage is incomplete", report["candidate_generation"]["reasons"])

        families = {item["family"] for item in report["opentofu"]["variables"]}
        self.assertIn("provider", families)
        self.assertIn("shared_onramp_resource", families)
        self.assertIn("searxng_service", families)

    def test_consumer_cutover_remains_blocked_until_semantic_equivalence_is_ready(self) -> None:
        report = MODULE.build_report(ROOT)
        self.assertEqual(report["classification"]["semantic_mapping_status"], "incomplete")
        self.assertEqual(report["consumer_contract"]["cutover_status"], "deferred")
        self.assertTrue(report["consumer_contract"]["legacy_terraform_input_present"])
        self.assertTrue(report["consumer_contract"]["legacy_static_inventory_present"])
        self.assertFalse(report["consumer_contract"]["canonical_projection_authoritative"])
        self.assertTrue(report["matrix_coverage"]["unmatched"])
        self.assertGreater(report["matrix_coverage"]["unmatched_count"], 0)

        plan = (ROOT / "scripts" / "plan-infra.sh").read_text(encoding="utf-8")
        apply = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        boundary = plan + "\\n" + apply
        self.assertIn("terraform.tfvars", boundary)
        self.assertIn("ansible/inventory/local.yml", boundary)
        self.assertNotIn("plan_equivalence.py", boundary)

    def test_ambiguous_matrix_match_is_review_required(self) -> None:
        source_inputs = {"inputs": [{"source": "fixture.tfvars", "key": "shared_key"}]}
        matrix = {
            "rows": [
                {"Legacy source(s)": "`shared_key`", "Canonical path": "resources.one.value"},
                {"Legacy source(s)": "`shared_key`", "Canonical path": "resources.two.value"},
            ]
        }
        coverage = MODULE.reconcile_matrix_inputs(source_inputs, matrix)
        self.assertEqual(coverage["matched"], [])
        self.assertEqual(coverage["unmatched"], [{"source": "fixture.tfvars", "key": "shared_key"}])
        self.assertEqual(coverage["ambiguous_count"], 1)
        self.assertEqual(coverage["ambiguous"][0]["canonical_paths"], ["resources.one.value", "resources.two.value"])
        self.assertEqual(coverage["status"], "review-required")
        readiness = MODULE.candidate_generation_readiness(coverage)
        self.assertEqual(readiness["status"], "blocked")
        self.assertFalse(readiness["candidate_generation_allowed"])
        self.assertIn("matrix contains ambiguous source matches", readiness["reasons"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "inventory.json"
            MODULE.main(["--repo", str(ROOT), "--output", str(output)])
            report = json.loads(output.read_text(encoding="utf-8"))

        encoded = json.dumps(report)
        self.assertNotIn("values/", encoded)
        self.assertNotIn("REPLACE_WITH_A_LONG_RANDOM_PASSWORD", encoded)
        self.assertNotIn("ssh-ed25519 AAAA", encoded)
        self.assertEqual(report["schema"], 1)
        self.assertEqual(report["opentofu"]["variable_count"], 182)
        blockers = (ROOT / "docs" / "canonical-values-model-blockers.md").read_text(encoding="utf-8")
        for heading in (
            "## Secret or protected inputs",
            "## Behavior or configuration without a typed owner",
            "## Ambiguous or destructive inputs",
            "## Migration-only or unsupported inputs",
        ):
            self.assertIn(heading, blockers)
    def test_hermes_non_secret_inputs_have_canonical_matrix_rows(self) -> None:
        report = MODULE.build_report(ROOT)
        matched = report["matrix_coverage"]["matched"]
        expected = {
            "forgejo_version": "services.forgejo.release.version",
            "hermes_runtime_user": "services.hermes.configuration.runtime_user",
            "hermes_repo_path": "services.hermes.configuration.repository_path",
            "hermes_control_enabled": "services.hermes.configuration.control.enabled",
            "hermes_control_domain": "services.hermes.configuration.control.domain",
            "hermes_control_source_url": "services.hermes.configuration.control.source_url",
            "hermes_control_source_ref": "services.hermes.configuration.control.source_ref",
            "hermes_control_api_token": "services.hermes.secrets.control_api_token",
            "hermes_control_bridge_token": "services.hermes.secrets.control_bridge_token",
            "hermes_dashboard_basic_auth_password_hash": "services.hermes.secrets.dashboard_basic_auth_password_hash",
            "hermes_dashboard_basic_auth_secret": "services.hermes.secrets.dashboard_basic_auth_secret",
            "HERMES_CONTROL_API_TOKEN": "services.hermes.secrets.control_api_token",
            "HERMES_CONTROL_BRIDGE_TOKEN": "services.hermes.secrets.control_bridge_token",
            "HERMES_CONTROL_SOURCE_REF": "services.hermes.configuration.control.source_ref",
            "HERMES_CONTROL_SOURCE_URL": "services.hermes.configuration.control.source_url",
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH": "services.hermes.secrets.dashboard_basic_auth_password_hash",
            "HERMES_DASHBOARD_BASIC_AUTH_SECRET": "services.hermes.secrets.dashboard_basic_auth_secret",
            "hermes_runtime_passwordless_sudo": "resources.guests.hermes.security.allow_passwordless_sudo",
            "hermes_allow_legacy_runtime": "services.hermes.configuration.allow_legacy_runtime",
            "hermes_compression_threshold": "services.hermes.configuration.tuning.compression_threshold",
            "hermes_max_concurrent_children": "services.hermes.configuration.tuning.max_concurrent_children",
            "hermes_max_spawn_depth": "services.hermes.configuration.tuning.max_spawn_depth",
            "hermes_discovery_version": "services.hermes.release.version",
            "hermes_discovery_tag": "services.hermes.release.tag",
            "hermes_discovery_commit": "services.hermes.release.commit",
            "hermes_discovery_wheel_sha256": "services.hermes.release.checksum",
            "hermes_node_version": "services.hermes.configuration.node.version",
            "hermes_node_sha256_amd64": "services.hermes.configuration.node.checksums.amd64",
            "hermes_node_sha256_arm64": "services.hermes.configuration.node.checksums.arm64",
            "hermes_dashboard_enabled": "services.hermes.configuration.dashboard.enabled",
            "hermes_dashboard_port": "services.hermes.endpoints.ports.dashboard",
            "hermes_dashboard_host": "services.hermes.configuration.dashboard.host",
            "hermes_dashboard_basic_auth_username": "services.hermes.configuration.dashboard.auth_username",
            "hermes_web_searxng_url": "services.hermes.configuration.web.searxng_url",
            "HERMES_WEB_SEARXNG_URL": "services.hermes.configuration.web.searxng_url",
        }
        for key, canonical_path in expected.items():
            with self.subTest(key=key):
                self.assertIn(
                    {"source": "scaffold/terraform.tfvars", "key": key, "canonical_path": canonical_path}
                    if key == "hermes_runtime_user"
                    else {"source": "scaffold/ansible/inventory/local.yml", "key": key, "canonical_path": canonical_path}
                    if not key.startswith("HERMES_")
                    else {"source": "scripts/parse-env.py", "key": key, "canonical_path": canonical_path},
                    matched,
                )
        unmatched = report["matrix_coverage"]["unmatched"]
        self.assertEqual(
            [item for item in unmatched if item["key"] == "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"],
            [
                {"source": "scripts/migrate-values.py", "key": "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"},
                {"source": "scripts/parse-env.py", "key": "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"},
            ],
        )


if __name__ == "__main__":
    unittest.main()

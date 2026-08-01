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

        self.assertEqual(report["opentofu"]["variable_count"], 184)
        self.assertEqual(len(report["opentofu"]["variables"]), 184)
        self.assertEqual(report["classification"]["unclassified_variables"], [])
        self.assertEqual(len(report["service_catalog"]["services"]), 9)
        self.assertEqual(report["canonical_path_coverage"]["checked_count"], 71)
        self.assertEqual(report["canonical_path_coverage"]["valid_count"], 71)
        self.assertEqual(report["canonical_path_coverage"]["invalid_count"], 0)
        self.assertEqual(report["canonical_path_coverage"]["status"], "complete")
        self.assertEqual(report["matrix_path_coverage"]["checked_count"], 248)
        self.assertEqual(report["matrix_path_coverage"]["valid_count"], 248)
        self.assertEqual(report["matrix_path_coverage"]["invalid_count"], 0)
        self.assertEqual(report["matrix_path_coverage"]["excluded_count"], 61)
        self.assertEqual(report["matrix_path_coverage"]["status"], "complete")
        self.assertEqual(report["matrix_classification_coverage"]["checked_count"], 309)
        self.assertEqual(report["matrix_classification_coverage"]["valid_count"], 309)
        self.assertEqual(report["matrix_classification_coverage"]["invalid_count"], 0)
        self.assertEqual(report["matrix_classification_coverage"]["status"], "complete")
        self.assertEqual(report["consumer_evidence"]["token_count"], 251)
        self.assertEqual(report["consumer_evidence"]["exact_evidence_count"], 203)
        self.assertEqual(report["consumer_evidence"]["dynamic_evidence_count"], 48)
        self.assertEqual(report["consumer_evidence"]["missing_exact_evidence_count"], 0)
        self.assertEqual(report["consumer_evidence"]["status"], "complete")
        self.assertEqual(report["consumer_evidence"]["row_count"], 246)
        self.assertEqual(report["consumer_evidence"]["evidenced_row_count"], 246)
        self.assertEqual(report["consumer_evidence"]["rows_without_evidence"], [])
        self.assertEqual(report["consumer_evidence"]["semantic_status"], "complete")
        first_evidence = report["consumer_evidence"]["row_evidence"][0]
        self.assertEqual(first_evidence["status"], "complete")
        self.assertTrue(first_evidence["exact"][0]["references"])
        self.assertTrue(all(reference["file"] and reference["lines"] for reference in first_evidence["exact"][0]["references"]))
        self.assertEqual(report["source_reconciliation"]["source_identity_count"], 374)
        self.assertEqual(report["source_reconciliation"]["accounted_identity_count"], 374)
        self.assertEqual(report["source_reconciliation"]["missing"], [])
        self.assertEqual(report["source_reconciliation"]["unexpected"], [])
        self.assertEqual(report["source_reconciliation"]["reasons"], [])
        self.assertEqual(report["source_reconciliation"]["status"], "complete")
        self.assertEqual(report["source_inventory"]["source_count"], 16)
        self.assertTrue(report["source_inventory"]["coverage"]["source_files_present"])
        self.assertEqual(report["source_inventory"]["coverage"]["opentofu_variables_inventoried"], 184)
        self.assertGreater(report["source_inventory"]["scaffold"]["terraform_assignment_count"], 0)
        self.assertIn("a_records", report["source_inventory"]["scaffold"]["dns"]["top_level_keys"])
        self.assertIn("tf_vmid", report["source_inventory"]["ansible"]["inventory_fields"])
        self.assertEqual(report["source_inputs"]["input_count"], 374)
        self.assertEqual(report["source_inputs"]["unique_identities"], 374)
        self.assertEqual(
            set(report["source_inputs"]["disposition_counts"]),
            {"ansible-only", "deprecated", "generated-projection", "operational-artifact", "retired-input", "unsupported"},
        )
        self.assertEqual(report["source_inputs"]["status"], "classification-complete-with-review-dispositions")
        self.assertEqual(report["mapping_matrix"]["row_count"], 309)
        self.assertEqual(report["mapping_matrix"]["status"], "semantic-coverage-complete")
        self.assertEqual(report["matrix_coverage"]["input_count"], 361)
        self.assertEqual(report["matrix_coverage"]["source_input_count"], 374)
        self.assertEqual(report["matrix_coverage"]["excluded_count"], 13)
        self.assertEqual(report["matrix_coverage"]["matched_count"] + report["matrix_coverage"]["unmatched_count"], 361)
        self.assertEqual(report["matrix_coverage"]["matched_count"], 361)
        self.assertEqual(report["matrix_coverage"]["unmatched_count"], 0)
        self.assertEqual(report["matrix_coverage"]["status"], "complete")
        self.assertFalse(report["matrix_coverage"]["unmatched"])
        deferred = report["deferred_classification"]
        self.assertEqual(deferred["item_count"], 0)
        self.assertEqual(deferred["classified_count"], 0)
        self.assertEqual(deferred["unclassified_count"], 0)
        self.assertEqual(
            set(deferred["counts"]),
            set(),
        )
        self.assertEqual(sum(deferred["counts"].values()), 0)
        self.assertEqual(
            deferred["counts"],
            {},
        )
        expected_deferred = set()
        self.assertEqual(
            {(item["source"], item["key"], item["classification"]) for item in deferred["items"]},
            expected_deferred,
        )
        self.assertIn(
            {"source": "scaffold/terraform.tfvars", "key": "onramp_host_datastore_id", "canonical_path": "resources.shared_hosts.onramp_host.storage.root.storage_id"},
            report["matrix_coverage"]["matched"],
        )
        self.assertIn(
            {"source": "scripts/parse-env.py", "key": "PROXMOX_VE_ENDPOINT", "canonical_path": "platform.proxmox.endpoint"},
            report["matrix_coverage"]["matched"],
        )
        self.assertEqual(
            report["protected_secret_contracts"],
            [{
                "canonical_path": "secrets.bootstrap.root_password",
                "owner": "bootstrap.root_password",
                "provider": "sops-age",
                "delivery": "ansible-bootstrap-memory",
                "state_exposure": "forbidden",
                "public_projection": "forbidden",
                "legacy_alias_policy": "retired-root-password-aliases; reject-unscoped-ssh",
            }],
        )
        for source, key, canonical_path in (
            ("scaffold/terraform.tfvars", "lxc_template_download_timeout_seconds", "platform.lxc_template_download_timeout_seconds"),
            ("scaffold/terraform.tfvars", "guest_vm_cloud_init_user", "platform.vm_cloud_init_user"),
            ("scaffold/terraform.tfvars", "onramp_host_cloud_init_user", "resources.shared_hosts.onramp_host.runtime.cloud_init_user"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runtime", "resources.guests.forgejo.type"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_enable_caddy", "services.forgejo.configuration.enable_caddy"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_configure_system_ssh", "services.forgejo.configuration.configure_system_ssh"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_write_initial_config", "services.forgejo.configuration.write_initial_config"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_bootstrap_enabled", "services.forgejo.configuration.bootstrap_enabled"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_bootstrap_admin_username", "services.forgejo.configuration.bootstrap_admin_username"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_bootstrap_admin_email", "services.forgejo.configuration.bootstrap_admin_email"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_bootstrap_owner_email", "services.forgejo.configuration.bootstrap_owner_email"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_actions_enabled", "services.forgejo.configuration.actions_enabled"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_actions_default_url", "services.forgejo.configuration.actions_default_url"),
            ("scaffold/ansible/inventory/local.yml", "infisical_data_dir", "services.infisical.configuration.data_dir"),
            ("scaffold/ansible/inventory/local.yml", "infisical_postgres_user", "services.infisical.configuration.postgres_user"),
            ("scaffold/ansible/inventory/local.yml", "infisical_postgres_db", "services.infisical.configuration.postgres_db"),
            ("scaffold/ansible/inventory/local.yml", "tailscale_client_restore_backup", "services.tailscale_client.configuration.restore_backup"),
            ("scaffold/ansible/inventory/local.yml", "tailscale_client_backup_archive", "services.tailscale_client.configuration.backup_archive"),
            ("scaffold/ansible/inventory/local.yml", "tailscale_client_enable_ip_forwarding", "services.tailscale_client.configuration.enable_ip_forwarding"),
            ("scaffold/ansible/inventory/local.yml", "tailscale_client_up_args", "services.tailscale_client.configuration.up_args"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runner_url", "services.forgejo_runner.configuration.url"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runner_name", "services.forgejo_runner.configuration.name"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runner_scope", "services.forgejo_runner.configuration.scope"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runner_label", "services.forgejo_runner.configuration.label"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runner_labels", "services.forgejo_runner.configuration.labels"),
            ("scaffold/ansible/inventory/local.yml", "forgejo_runner_hosts", "services.forgejo_runner.configuration.hosts"),
            ("scaffold/terraform.tfvars", "searxng_container_port", "services.searxng_onramp.configuration.container_port"),
            ("scaffold/terraform.tfvars", "searxng_bind_address", "services.searxng_onramp.configuration.bind_address"),
            ("scaffold/terraform.tfvars", "searxng_instance_name", "services.searxng_onramp.configuration.instance_name"),
            ("scaffold/terraform.tfvars", "searxng_enable_public_url", "services.searxng_onramp.configuration.enable_public_url"),
            ("scripts/migrate-values.py", "TECHNITIUM_API_URL", "services.technitium.configuration.api_url"),
            ("scripts/parse-env.py", "TECHNITIUM_API_URL", "services.technitium.configuration.api_url"),
            ("scripts/parse-env.py", "TECHNITIUM_ADMIN_USER", "services.technitium.configuration.admin_user"),
        ):
            with self.subTest(source=source, key=key):
                self.assertIn(
                    {"source": source, "key": key, "canonical_path": canonical_path},
                    report["matrix_coverage"]["matched"],
                )
        for key, canonical_path in (
            ("service_runtime.forgejo.type", "resources.guests.forgejo.type"),
            ("forgejo_database.type", "services.forgejo.configuration.database.type"),
            ("service_storage.forgejo.data.type", "resources.guests.forgejo.storage.volumes.data.type"),
            ("service_storage.forgejo.data.storage_id", "resources.guests.forgejo.storage.volumes.data.storage_id"),
            ("service_storage.forgejo.data.size_gb", "resources.guests.forgejo.storage.volumes.data.size_gb"),
            ("service_storage.forgejo.data.target", "resources.guests.forgejo.storage.volumes.data.target"),
            ("service_storage.forgejo.data.backup", "resources.guests.forgejo.storage.volumes.data.backup"),
            ("service_storage.forgejo.data.read_only", "resources.guests.forgejo.storage.volumes.data.read_only"),
        ):
            self.assertIn(
                {"source": "scaffold/terraform.tfvars", "key": key, "canonical_path": canonical_path},
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
        for key, canonical_path in {
            "settings": "platform.dns.settings",
            "zones": "platform.dns.zones",
            "a_records": "platform.dns.a_records",
            "cname_records": "platform.dns.cname_records",
        }.items():
            self.assertIn(
                {"source": "scaffold/dns-records.local.json", "key": key, "canonical_path": canonical_path},
                report["matrix_coverage"]["matched"],
            )
        for source, key in (
            ("scaffold/ansible/inventory/local.yml", "forgejo_version"),
            ("scripts/migrate-values.py", "forgejo_version"),
            ("scripts/migrate-values.py", "FORGEJO_VERSION"),
        ):
            self.assertIn(
                {"source": source, "key": key, "canonical_path": "services.forgejo.release.version"},
                report["matrix_coverage"]["matched"],
            )
        self.assertIn(
            {"source": "scripts/migrate-values.py", "key": "FORGEJO_UPSTREAM", "disposition": "retired-input"},
            report["matrix_coverage"]["excluded"],
        )
        self.assertIn(
            {"source": "scripts/migrate-values.py", "key": "ascii", "disposition": "retired-input"},
            report["matrix_coverage"]["excluded"],
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
            ("scripts/migrate-values.py", "FORGEJO_SERVER_NAME", "services.forgejo.endpoints.public_names"),
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
            self.assertNotIn(
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
        self.assertIn(
            {
                "source": "scaffold/ansible/inventory/local.yml",
                "key": "forgejo_runner_version",
                "canonical_path": "services.forgejo_runner.release.version",
            },
            report["matrix_coverage"]["matched"],
        )

        for source, key in (
            ("scaffold/terraform.tfvars", "tailscale_client_enabled"),
            ("scaffold/ansible/inventory/local.yml", "tailscale_client_enabled"),
        ):
            self.assertIn(
                {"source": source, "key": key, "canonical_path": "services.tailscale_client.enabled"},
                report["matrix_coverage"]["matched"],
            )
        self.assertIn(
            {
                "source": "scaffold/ansible/inventory/local.yml",
                "key": "infisical_version",
                "canonical_path": "services.infisical.release",
            },
            report["matrix_coverage"]["matched"],
        )
        self.assertEqual(len(report["service_contracts"]), 9)
        self.assertTrue(report["consumer_contract"]["legacy_terraform_input_present"])
        self.assertTrue(report["consumer_contract"]["legacy_static_inventory_present"])
        self.assertEqual(report["classification"]["inventory_status"], "complete")
        self.assertEqual(report["classification"]["semantic_mapping_status"], "semantic-coverage-complete")
        self.assertEqual(report["classification"]["consumer_cutover_status"], "canonical-site-authoritative-with-legacy-compatibility")
        self.assertEqual(report["candidate_generation"]["status"], "blocked")
        self.assertFalse(report["candidate_generation"]["candidate_generation_allowed"])
        self.assertIn("selected-source runtime admission must pass without conflicts", report["candidate_generation"]["reasons"])
        self.assertEqual(report["candidate_projection"], {"status": "blocked", "row_count": 0, "source_reference_count": 0, "rows": []})
        aliases = report["legacy_alias_classification"]["ambiguous_resource_aliases"]
        self.assertEqual(len(aliases), 0)
        self.assertTrue(all(item["classification"] == "ambiguous" for item in aliases))
        provider_aliases = report["legacy_alias_classification"]["provider_secret_aliases"]
        self.assertEqual(provider_aliases, [])
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
        self.assertIn(
            {
                "source": "scripts/migrate-values.py",
                "key": "container_vmid",
                "canonical_path": "resources.guests.<services.technitium.resource>.identity.vmid",
            },
            [
                {"source": item["source"], "key": item["key"], "canonical_path": item["canonical_path"]}
                for item in report["matrix_coverage"]["matched"]
            ],
        )
        self.assertFalse(report["candidate_generation"]["candidate_generation_allowed"])
        self.assertIn("selected-source runtime admission must pass without conflicts", report["candidate_generation"]["reasons"])

        families = {item["family"] for item in report["opentofu"]["variables"]}
        self.assertIn("provider", families)
        self.assertIn("shared_onramp_resource", families)
        self.assertIn("searxng_service", families)

    def test_consumer_cutover_is_canonical_for_selected_sites_with_legacy_compatibility(self) -> None:
        report = MODULE.build_report(ROOT)
        self.assertEqual(report["classification"]["semantic_mapping_status"], "semantic-coverage-complete")
        self.assertEqual(report["consumer_contract"]["cutover_status"], "canonical-site-authoritative-with-legacy-compatibility")
        self.assertTrue(report["consumer_contract"]["legacy_terraform_input_present"])
        self.assertTrue(report["consumer_contract"]["legacy_static_inventory_present"])
        self.assertTrue(report["consumer_contract"]["canonical_projection_authoritative"])
        self.assertFalse(report["matrix_coverage"]["unmatched"])
        self.assertEqual(report["matrix_coverage"]["unmatched_count"], 0)

        plan = (ROOT / "scripts" / "plan-infra.sh").read_text(encoding="utf-8")
        apply = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        boundary = plan + "\\n" + apply
        self.assertIn("terraform.tfvars", boundary)
        self.assertIn("ansible/inventory/local.yml", boundary)
        self.assertNotIn("plan_equivalence.py", boundary)

    def test_matrix_classification_gate_rejects_unknown_and_incoherent_rows(self) -> None:
        coverage = MODULE.matrix_classification_coverage(
            {
                "rows": [
                    {"Canonical path": "services.example.value", "Class": "new-class", "Secret class": "public"},
                    {"Canonical path": "secrets.example.value", "Class": "canonical/derived", "Secret class": "secret"},
                    {"Canonical path": "services.example.protected", "Class": "protected", "Secret class": "public"},
                ]
            }
        )
        self.assertEqual(coverage["checked_count"], 3)
        self.assertEqual(coverage["valid_count"], 0)
        self.assertEqual(coverage["invalid_count"], 3)
        self.assertEqual(coverage["status"], "review-required")
        self.assertEqual(
            coverage["invalid"],
            [
                {"canonical_path": "services.example.value", "reasons": ["unknown matrix class"]},
                {"canonical_path": "secrets.example.value", "reasons": ["secret path lacks secret/protected row class"]},
                {"canonical_path": "services.example.protected", "reasons": ["secret/protected row is marked public"]},
            ],
        )

    def test_source_reconciliation_gate_fails_closed_for_missing_and_unexpected_inputs(self) -> None:
        source_inputs = {
            "inputs": [
                {"source": "fixture.tfvars", "key": "present"},
                {"source": "fixture.tfvars", "key": "missing"},
            ]
        }
        coverage = {
            "matched": [{"source": "fixture.tfvars", "key": "present", "canonical_path": "platform.value"}],
            "excluded": [{"source": "other.tfvars", "key": "unexpected", "disposition": "operational-artifact"}],
            "ambiguous_count": 0,
        }
        gate = MODULE.source_reconciliation_gate(source_inputs, coverage)
        self.assertEqual(gate["source_identity_count"], 2)
        self.assertEqual(gate["accounted_identity_count"], 2)
        self.assertEqual(gate["missing"], [{"source": "fixture.tfvars", "key": "missing"}])
        self.assertEqual(gate["unexpected"], [{"source": "other.tfvars", "key": "unexpected"}])
        self.assertEqual(
            gate["reasons"],
            ["source identity lacks a matrix disposition", "matrix disposition references an unknown source identity"],
        )
        self.assertEqual(gate["status"], "review-required")

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
        self.assertEqual(report["opentofu"]["variable_count"], 184)
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
            [],
        )


if __name__ == "__main__":
    unittest.main()

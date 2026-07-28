# Canonical Values Mapping Matrix — Version 1 Working Draft

**Status:** Incomplete — implementation tracker W3 remains partial
**PRD:** [`../.hermes/plans/canonical-values-model-prd.md`](../.hermes/plans/canonical-values-model-prd.md)
**Implementation tracker:** [`../.hermes/plans/canonical-values-model-implementation.md`](../.hermes/plans/canonical-values-model-implementation.md)

This is the versioned mapping contract for the canonical-values migration. A row is implementation-ready only when its canonical path, type, condition, all legacy sources, generated consumer fields, normalization/default/conflict behavior, secret class, and destructive impact are specified.

## Classification

- **canonical:** operator-owned in `site.yaml` or `secrets.sops.yaml`.
- **derived:** generated from canonical values; never edited.
- **Ansible-only:** intentionally retained for Ansible implementation details.
- **OpenTofu-only:** compatibility boundary name, generated from canonical values.
- **deprecated:** accepted only by importer/compatibility wrapper during the window.
- **unsupported:** rejected or retained in a review report; never silently ignored.

## Ownership rules

| Canonical domain | Authoritative ownership | Consumer projections |
| --- | --- | --- |
| `site` | identity, class, lifecycle, apply/destroy policy, schema version | plan/apply metadata and safety gates |
| `platform` | Proxmox, network, storage, image/template defaults | OpenTofu variables and Ansible defaults |
| `resources` | guest/shared-host identity, network, compute, storage, runtime | OpenTofu resources and Ansible inventory |
| `services` | enablement, placement, dependencies, endpoints, release, state, behavior | OpenTofu compatibility variables, Ansible vars, DNS, runtime |
| `secrets.sops.yaml` | logical secret values and secret identity | protected provider/Ansible/runtime inputs only |

A logical service references exactly one resource. VMID, hostname, address, compute, storage, and runtime facts must not be repeated under a service.

## Initial canonical-to-consumer rows

| Canonical path | Type/condition | Legacy source(s) | Generated consumer field(s) | Class | Normalization/default | Conflict behavior | Secret class | Destructive impact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `schema_version` | required integer = `1` | none | plan metadata | canonical | no default | fail closed | public | none |
| `site.name` | DNS-safe identifier; equals directory and `VALUES_SITE` | `site.json.name`, `VALUES_SITE` | plan metadata, projection identity | canonical | lowercase identifier | mismatch fails | public | site identity |
| `site.class` | `development`, `staging`, `production` | `site.json.class` | policy checks | canonical | none | invalid enum fails | public | policy |
| `site.lifecycle` | `disposable`, `persistent`, `protected` | `site.json.lifecycle` | policy checks | canonical | none | production/disposable and protected mutation policies fail | public | lifecycle |
| `site.allow_apply` | boolean | `site.json.allow_apply` | apply gate | canonical | required | missing/type mismatch fails | public | mutation gate |
| `site.allow_destroy` | boolean | `site.json.allow_destroy` | destructive apply gate | canonical | required; production must be false | unsafe policy fails | public | destructive |
| `platform.proxmox.endpoint` | URL | `proxmox_endpoint` | `proxmox_endpoint` | OpenTofu-only | preserve URL form | normalized URL conflicts fail | provider | provider/state exposure review |
| `platform.proxmox.node` | identifier | `proxmox_node_name` | `proxmox_node_name` | OpenTofu-only | none | conflict fails | public | resource placement |
| `platform.proxmox.insecure` | boolean | `proxmox_insecure` | `proxmox_insecure` | OpenTofu-only | strict boolean | conflict fails | public | connectivity |
| `platform.network.default_bridge` | string | `*_container_bridge`, inventory defaults | resource bridge vars/inventory | canonical/derived | resource override wins | normalized values must agree | public | network |
| `platform.network.default_gateway` | address | inventory/defaults | resource gateway vars | canonical/derived | CIDR/address normalization | conflict fails | public | network |
| `platform.network.default_dns_servers` | list of addresses | `*_dns_servers`, inventory defaults | resource DNS vars | canonical/derived | list order preserved; no implicit merge | conflicting explicit lists fail | public | network |
| `platform.storage.rootfs_datastore` | non-empty string | `rootfs_datastore_id` | `rootfs_datastore_id` | OpenTofu-only | none | conflict fails | public | storage |
| `platform.storage.template_datastore` | non-empty string | `template_datastore_id` | `template_datastore_id` | OpenTofu-only | none | conflict fails | public | image/storage |
| `platform.images.lxc.*` | typed image + checksum | `debian_template_*` | template URL/file/checksum vars | canonical/derived | checksum lowercase; URL stable | checksum/URL conflicts fail | public | replacement/download |
| `platform.images.vm.*` | typed image + checksum | `guest_vm_image_*`, `onramp_host_image_*` | image vars | canonical/derived | checksum lowercase; URL stable | conflicts fail | public | replacement/download |
| `resources.guests.<id>.identity.vmid` | positive unique integer | `<service>_container_vmid`, `<service>_vmid` | current VMID vars/inventory | canonical | numeric normalization | differing integers fail | public | identity/replacement |
| `resources.guests.<id>.identity.hostname` | hostname | `<service>_container_hostname` | current hostname vars/inventory | canonical | lowercase, strip trailing dot | normalized mismatch fails | public | disruptive |
| `resources.guests.<id>.network.address` | `dhcp` or static CIDR | `<service>_container_ipv4_address` | address vars/inventory | canonical | CIDR normalization | conflicting address fails | public | network/DNS |
| `resources.guests.<id>.network.expected_address` | IPv4; DHCP only | `<service>_lan_ip`, DNS JSON target | inventory/DNS projection | derived/canonical | bare IPv4 | conflict fails; required for DNS publication from DHCP | public | DNS |
| `resources.guests.<id>.compute.*` | positive resource values | `<service>_container_{cores,memory_mb,swap_mb,disk_gb}` | current resource vars | canonical/derived | strict numeric types | differing values fail | public | resize/storage |
| `resources.guests.<id>.storage.*` | typed volume map | `service_storage`, per-service storage vars | OpenTofu/Ansible storage inputs | canonical/derived | named volumes; no shrink | conflict fails; shrink destructive | public | storage |
| `resources.shared_hosts.<id>` | shared resource shape | `onramp_host_*` | OpenTofu/inventory host vars | canonical/derived | VM runtime fields only | identity/network conflicts fail | public | replacement |
| `services.<name>.enabled` | boolean | `settings.local.json.services`, `enabled_services`, `<service>_enabled` | `enabled_services` | canonical/derived | service map is sole authority | conflicts fail | public | stateful disable warning |
| `services.<name>.resource` | resource reference | inferred from legacy service/resource names | inventory and resource vars | canonical/derived | must resolve exactly once | unresolved/duplicate fails | public | placement |
| `services.<name>.endpoints.public_names` | list of hostnames | `<service>_server_name`, `<service>_domain`, `SERVER_NAME` (Technitium), DNS JSON | Ansible/Caddy/DNS projection | canonical/derived | lowercase, strip trailing dot | normalized conflict fails | public | DNS/proxy |
| `services.<name>.endpoints.public_url` | URL | `<service>_public_url`, runtime env | Ansible/runtime projection | canonical/derived | normalized URL | mismatch fails | public | endpoint |
| `services.<name>.release.*` | typed release pin | service version/image/checksum vars | Ansible/runtime/OpenTofu boundary | canonical/derived | immutable digest/checksum required by source | conflicts fail | public | service update |
| `services.<name>.state.*` | state policy | `infra/services.json`, service-state settings | backup/restore plan | canonical/derived | catalog capability constrains model | state-capability mismatch fails | public | disable/destroy |
| `services.<name>.configuration.*` | catalog schema | service-specific tfvars/env/inventory | Ansible vars/runtime | canonical/derived | strict schema | unknown/conflict fails | public | service behavior |
| `services.<name>.overrides.<consumer>` | allow-listed map | selected legacy consumer knobs | consumer-specific projection | Ansible-only/OpenTofu-only | catalog allow-list only | arbitrary maps rejected | public | review required |
| `platform.proxmox.api_token` | required when provider needs it | `PROXMOX_VE_API_TOKEN`, provider env | protected provider env | secret | never render to service files | missing/conflict fails | provider | state exposure review |
| `services.<name>.<logical_secret>` | required by catalog condition | legacy `.env`/inventory secret key | protected task/runtime input | secret | logical path only | missing/conflict fails | bootstrap/runtime/provider | secret-dependent |

## Normalization contract

- Hostnames are lowercase with trailing dots removed.
- Static IPv4 values are represented as CIDR in resources and bare IPv4 in DNS targets.
- `dhcp` is a literal resource address mode; `expected_address` is not a static address declaration.
- HCL quoted strings, JSON strings, YAML strings, and dotenv scalar values normalize to the same logical string.
- Boolean and numeric values are parsed strictly; no truthy-string or numeric-string coercion is allowed in canonical input.
- `null` has schema-defined meaning and is not silently converted to an empty string.
- Lists replace rather than concatenate unless a schema row explicitly declares otherwise.
- Checksums normalize to lowercase hexadecimal and must match their declared algorithm length.
- Comments, whitespace, key ordering, and line endings do not affect canonical identity.

## Current-input inventory and review status

The matrix must be checked against these sources before W3 can close:

- `infra/opentofu/variables.tf` — current OpenTofu variable declarations (182 declarations at initial inventory).
- `infra/services.json` — service capability, dependency, state, playbook, inventory, and OpenTofu address registry.
- `infra/ansible/inventory/tfvars.py` — dynamic inventory and legacy variable promotion.
- `scripts/migrate-values.py` — legacy dotenv/tfvars names, generated secrets, normalization, and migration defaults.
- `scripts/migrate-site-values.py` — site layout movement and metadata contract.
- `scaffold/terraform.tfvars`, `scaffold/dns-records.local.json`, and scaffold inventory — public-safe legacy starter contract.
- `scripts/parse-env.py`, `scripts/envfile.py`, and `scripts/run-infra.sh` — dotenv keys and transport behavior.

Unmapped fields must be written to a migration review report with source path, value classification, proposed canonical owner, and disposition. They must not be dropped by an importer or renderer.

## Review log

| Date | Review | Result |
| --- | --- | --- |
| 2026-07-27 | Initial canonical loader/projection slice | Common site/resource/service fields and initial OpenTofu, Ansible, and DNS projections implemented and tested; full matrix remains open. |

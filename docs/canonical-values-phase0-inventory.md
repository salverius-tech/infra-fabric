# Canonical Values Phase 0 Inventory and Design Decisions

**Status:** Phase 0 evidence baseline
**Branch:** `feat/canonical-values-model`
**Plan:** [Canonical Site Values Model implementation plan](../.hermes/plans/canonical-values-model-implementation.md)
**Scope:** public repository contracts only; private `values/`, state, credentials, and live topology are excluded.

This document records the Phase 0 repository inventory and the implementation decisions required before completing the schema, service-catalog, mapping, importer, and consumer workstreams. It is an inventory and design boundary, not evidence of canonical consumer cutover.

## 1. Current values-context contract

| Contract | Source | Current behavior | Canonical implication |
| --- | --- | --- | --- |
| Repository root | `scripts/values_context.py:83-98` | Derived from the script location unless an explicit repository path is supplied. | Reuse this resolver; do not add a competing repository-root convention. |
| Values root | `VALUES_DIR`, default `repo/values` | Relative paths are resolved beneath the repository. | Canonical sites remain beneath the selected private values root. |
| Site selection | `VALUES_SITE` | Validated as a simple identifier, then resolved from `<values>/sites/<site>` or `<values>/<site>`; the legacy site-root shape is retained for compatibility. | Site-scoped commands must use the selected site and reject traversal or identity mismatch. |
| Selected directory | `ValuesContext.values_dir` | Root layout when no site is selected; selected site directory otherwise. | All site-local canonical, generated, state, plan, and backup paths derive from this object. |
| Path containment | `ValuesContext.path()` and `generated_path()` | Resolved paths must remain inside the selected values directory; generated names reject absolute and `..` components. | Keep one path authority for `site.yaml`, `secrets.sops.yaml`, `generated/`, `state/`, and `backups/`. |
| Canonical detection | `canonical_site_path` | Returns `site.yaml` only for a selected site and only when it is a regular file. | Missing canonical input preserves the legacy compatibility path during the window. |
| Legacy metadata | `metadata_path`, `load_metadata()` | Looks for `site.json`, `settings.json`, or `settings.local.json`; validates the declared name against `VALUES_SITE`. | Site metadata is transitional input; canonical `site.yaml` owns site identity after cutover. |
| Shell context | `scripts/site-context.sh` | Exposes `INFRA_VALUES_DIR`, `VALUES_SITE`, and selected site path helpers. | Shell wrappers must call the existing context functions and pass selected paths explicitly. |

## 2. Migration and legacy contracts

| Surface | Source | Current behavior | Boundary for Phase 0 |
| --- | --- | --- | --- |
| Legacy normalization | `scripts/migrate-values.py` | Large mutating migration routine: dotenv/tfvars parsing, renames, defaults, generated secrets, inventory changes, DNS normalization, and service-specific repairs. | Discovery may reuse only proven pure parsers; it must not call mutating migration helpers. |
| Site-layout move | `scripts/migrate-site-values.py` | Dry-run by default; moves selected legacy files into `values/sites/<site>`, writes `site.json`, removes root service selection on apply, and rolls back moved files/settings on failure. | Keep file relocation separate from canonical candidate generation. Candidate generation, SOPS creation, and secret generation remain later work. |
| Legacy root inputs | `migrate-site-values.py:MIGRATED_FILES` and state glob | `.env`, `terraform.tfvars`, DNS JSON, static inventory, known hosts, state files, and `service-backups/`. | Every source must be inventoried and classified before importer apply is enabled. |
| Site-aware inputs | `docs/canonical-values-mapping-v1.md` and migration plan | Existing site-aware trees may contain `site.json`, site dotenv/tfvars, inventory, known hosts, DNS JSON, state, plans, backups, and artifacts. | Importer must preserve or explicitly account for each item; it must not copy production material into another site. |
| Discovery | `scripts/legacy_values_discovery.py` and CLI wrapper | Read-only, redacted report; mapped conflicts fail closed; unknown/unsupported observations suppress candidate generation. | This remains the compatibility-window review path until the matrix and schemas are complete. |
| Root operator settings | `settings.local.json` | Repository/operator metadata currently also contains service selection in legacy layouts. | Service selection moves into `site.yaml`; root settings retains only repository/operator metadata. |

## 3. OpenTofu contract inventory

`infra/opentofu/variables.tf` currently declares **182 variables**. The complete declaration inventory is the authoritative source for the W3 matrix coverage check.

| Variable family | Representative fields | Intended classification |
| --- | --- | --- |
| Provider/platform | `proxmox_endpoint`, `proxmox_insecure`, `proxmox_username`, `proxmox_password`, `proxmox_api_token`, `proxmox_node_name` | Canonical platform intent or protected provider delivery; credentials are secret/provider class. |
| Global storage/template | `rootfs_datastore_id`, `template_datastore_id`, `debian_template_*`, `lxc_template_download_timeout_seconds` | Canonical platform/image intent, with derived compatibility names at the renderer boundary. |
| Technitium guest | `technitium_container_*` | Resource identity/network/compute/storage/runtime plus service-owned endpoint fields. |
| Forgejo guest | `forgejo_container_*`, `forgejo_lan_ip`, `forgejo_server_name`, `forgejo_database`, `forgejo_storage`, startup fields | Resource fields, service endpoint/configuration, and derived OpenTofu names. |
| Forgejo runner | `forgejo_runner_*` | Resource/runtime fields for the runner; service dependency on Forgejo is catalog-owned. |
| Infisical guest | `infisical_container_*`, `infisical_lan_ip`, `infisical_server_name`, startup fields | Resource fields and service endpoint/state fields. |
| Hermes guest | `hermes_container_*`, `hermes_lan_ip`, `hermes_server_name`, runtime/startup fields | Resource fields, service endpoint, and runtime configuration. |
| Shared onramp host | `onramp_host_*` | `resources.shared_hosts.onramp_host`; shared services reference this resource and must not duplicate its identity. |
| Tailscale guest | `tailscale_client_*` | Resource/runtime fields plus service enablement. |
| SearXNG onramp | `searxng_*` | Service configuration/endpoint/release projection on the shared onramp resource. |
| Selection/runtime glue | `enabled_services`, `service_runtime`, `forgejo_runtime`, startup variables | Derived from canonical service/resource state; compatibility-only at the OpenTofu boundary. |

The full variable-name list is retained by the Phase 0 inventory command and must be checked against `infra/services.json`, `infra/ansible/inventory/tfvars.py`, migration parsers, and scaffold inputs before W3 closes. No variable is permitted to disappear merely because it has no canonical owner yet; unsupported values remain in the redacted migration report.

## 4. Ansible and execution-path inventory

| Path | Current role | Canonical migration boundary |
| --- | --- | --- |
| `infra/ansible/inventory/tfvars.py` | Parses legacy `terraform.tfvars`, promotes environment fallbacks, builds groups/hosts/hostvars, and maps service-specific variables. | First becomes a compatibility adapter over an identity-verified canonical snapshot; it is not replaced until role-variable parity is mapped. |
| `values/.../ansible/inventory/local.yml` | Static private inventory and connection/override input. | Remains active during compatibility; later reduced to genuine Ansible-only overrides. |
| `scripts/apply-ansible-services.py` | Loads dotenv/root-password compatibility inputs, computes dependency waves, selects playbooks, and runs Ansible sequentially or in parallel. | Must consume the same normalized snapshot and verified projection identity as OpenTofu; secrets are injected only at the task boundary. |
| `scripts/plan-infra.sh` | Runs preflight, settings summary, canonical projection refresh, Ansible preflight, OpenTofu init/plan/show, and metadata creation. Currently passes legacy `terraform.tfvars`. | Projection refresh is an established safety boundary; changing the `-var-file` and inventory arguments is a later cutover slice. |
| `scripts/apply-infra.sh` | Verifies saved plan metadata, applies OpenTofu, then runs Ansible and re-verifies identity before service mutation. | Preserve legacy-only behavior; canonical execution must verify the same site/model/secret/projection identities before each mutation boundary. |
| `scripts/run-infra.sh` | Container execution boundary; resolves values and optionally transports SSH/SOPS key material. | Remains the only supported container transport boundary; canonical secret files never enter ordinary command-line arguments. |

## 5. Service catalog inventory

`infra/services.json` currently contains **9 service/resource registry entries**:

| Entry | Stateful | Dependencies | Runtime/resource implication |
| --- | ---: | --- | --- |
| `technitium` | yes | none | Dedicated service resource; LXC/VM Terraform addresses and three Ansible playbooks. |
| `forgejo` | yes | none | Dedicated service resource; endpoint/domain, database, user, storage, and release mappings. |
| `tailscale_client` | no | none | Dedicated optional guest with runtime enablement. |
| `forgejo_runner` | no | `forgejo` | Dedicated runner resource dependent on Forgejo. |
| `infisical` | yes | none | Dedicated service resource with endpoint/domain mapping. |
| `infisical_onramp` | yes | `onramp_host` | Logical service hosted on the shared onramp resource. |
| `hermes` | yes | none | Dedicated service resource with runtime user and SSH-key-related inputs. |
| `onramp_host` | yes | none | Shared VM resource; owns host identity, cloud-init, deployment, and SSH policy. |
| `searxng_onramp` | yes | `onramp_host` | Logical service hosted on the shared onramp resource with image, port, bind, and URL configuration. |

The existing catalog records state capability, state order, Terraform address patterns, replacement addresses, playbooks, dependencies, and inventory-name mappings. It does **not yet** fully record canonical required fields, required logical secrets, configuration schemas, release forms, or allowed overrides. Those additions are W1/W3 work, but this inventory establishes the current registry boundary.

## 6. Command and artifact contracts

| Operation | Current public entry point | Current authoritative inputs | Phase 0 decision |
| --- | --- | --- | --- |
| Setup | `just setup` | Values repository, legacy files, migration helper, preflight | Keep command name; canonical setup becomes additive until importer/cutover is proven. |
| Validate | `just validate`, `scripts/validate-values.sh` | Public source plus private legacy values | Run canonical validation and legacy discovery as independent gates. Neither implies parity. |
| Plan | `just plan`, `scripts/plan-infra.sh` | Legacy tfvars, legacy inventory, DNS/runtime helpers, selected site context | Canonical projections may be staged and identity-bound first; consumer argument cutover is later. |
| Apply | `just apply`, `scripts/apply-infra.sh` | Reviewed legacy plan, legacy inventory, service inputs | No canonical apply cutover until identity, secret delivery, and plan-equivalence gates pass. |
| Backup | `scripts/migration-backup.py` and related helpers | Explicitly selected private paths | Keep manifests content-free, deterministic, regular-file-only, symlink-safe, and mode `0600`. |
| Restore | Existing site/state migration and operator procedures | Site-local private backup/state | Requires site identity, verified manifest, and explicit recovery procedure. |
| Update | `just update` | Managed public pins and private values context | Preserve command and route canonical release pins only after release mapping is complete. |
| Generated artifacts | `values/sites/<site>/generated/` | Canonical projection renderer | Site-local, ignored, mode `0700`; render to a temporary sibling and atomically replace only after successful verification. |
| State/plans | Existing site-aware state/plan paths | Selected site context | Never shared across sites; plan metadata binds site/model/secret/projection/tool identities. |

## 7. Phase 0 implementation decisions

These decisions close the currently open design records without enabling consumer or infrastructure mutation:

| ID | Decision | Rationale / affected workstreams |
| --- | --- | --- |
| D1 | Keep the loader in importable modules under `scripts/` for the current repository, with thin hyphenated CLI wrappers. | Matches the existing Python boundary, avoids competing package installation, and keeps shell entry points stable. A later package extraction must preserve imports. Affects W1/W3. |
| D2 | Use strict Pydantic models with catalog-referenced per-service schemas. Common resource/endpoint/release/state models remain shared; arbitrary service configuration and overrides remain rejected or report-only until a catalog schema exists. | Prevents a permissive map from becoming a second source of truth. Affects W1/W3/W5. |
| D3 | Maintain `docs/canonical-values-mapping-v1.md` as the human contract and add an automated inventory/coverage check over variables, catalog mappings, parser keys, scaffold inputs, DNS keys, dotenv keys, and inventory promotions. | Human rows capture semantics; generated inventory prevents silent omissions. Affects W3/W4. |
| D4 | SOPS/age uses an external key file, metadata-only availability checks before decryption, fixed in-container path `/run/secrets/sops-age-key`, and explicit recipient-policy verification. Missing or ambiguous activated policy fails closed; no bundle means legacy compatibility remains unchanged until required-secret policy activates it. | Separates provider availability from secret delivery and avoids invented operational recipients. Affects W2/W5. |
| D5 | Non-secret projections live under selected-site `generated/`; secret-bearing projections are temporary only. Rendering stages in a mode-`0700` temporary sibling, files use restrictive modes, replacement is atomic, and the prior set remains restorable until installation succeeds. | Matches current transactional renderer and prevents partial persistent output. Affects W2/W5/W6. |
| D6 | Secret inventory is catalog-owned and classified as `bootstrap`, `runtime`, `provider`, `recovery`, or `generated`; values remain in memory and are delivered only through a consumer-specific protected boundary. Any OpenTofu-state secret requires an explicit state-protection decision before wiring. | Avoids accidental plaintext persistence and keeps provider/service secret paths separate. Affects W2/W5. |
| D7 | During compatibility, `tfvars.py` and static inventory remain active inputs. The first adapter must produce the existing role contract from the normalized snapshot and must be verified at the actual `apply-ansible-services.py` boundary before replacing arguments. | A projection shape test is not Ansible cutover evidence. Affects W5/W6/W7. |
| D8 | Overrides are namespaced by consumer and allow-listed in `infra/services.json`; no unrestricted `extra_vars`, `terraform`, or `ansible` maps are transported. | Preserves catalog ownership and blocks opaque secret-bearing maps. Affects W3/W5. |
| D9 | Version one keeps site-local state with restrictive filesystem permissions and encrypted private backups; state is resolved by `VALUES_SITE` and never enters the public repository. Remote backend work is deferred. | Establishes a bounded recovery contract without inventing remote infrastructure. Affects W4/W7. |
| D10 | Compatibility warnings are emitted by the canonical workflow when legacy files are directly consumed; they remain for one release cycle after cutover, with removal only after representative migration, equivalence, rollback, repeat-plan, and operational evidence. | Makes removal criteria evidence-based rather than time-only. Affects W7/W8. |

## 8. Phase 0 exit conditions and remaining dependent work

Phase 0 is complete when this inventory and the mapping document are kept together with the following evidence:

- all named source surfaces have been inventoried;
- every current input has an initial classification or an explicit `unsupported/review` disposition;
- D1–D10 are recorded and no W1–W3 implementation ambiguity remains;
- the automated coverage check is implemented before W3 is marked complete;
- the complete per-service schema/mapping rows and fixtures remain tracked as W1/W3 deliverables;
- no consumer cutover, secret delivery, migration apply, or infrastructure apply is implied by this document.

The next implementation order after this baseline is:

1. turn the source inventories into an automated mapping-coverage check;
2. complete catalog metadata and per-service schema/fixture contracts;
3. finish the provider cleanup/delivery contract;
4. implement importer candidate generation only after the matrix is complete enough to fail closed safely;
5. wire projections into consumers only after identity and equivalence gates are executable.

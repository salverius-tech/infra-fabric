# Canonical Cutover Audit Report

**Scope:** Read-only audit of the selected canonical development site and tracked public workflow code.

**Safety boundary:** This report intentionally contains no values, recipients, private-key material, addresses, domains, hostnames, token/password data, ciphertext, state contents, or plan contents. Private values were inspected only for file presence, permissions, structural metadata, enabled public service IDs, and legacy Git-HEAD file/key-class provenance. No private file, SOPS ciphertext, generated projection, state, Git branch, host, or service was modified. No plan or apply was run.

**Conclusion:** The non-secret canonical model and projection boundary is substantially implemented. The secret-consumer cutover is not coherent: the catalog defines only Hermes runtime paths, `secret_delivery.py` independently defines a different service namespace for all runtime delivery, and canonical `apply` invokes that independent delivery after a preflight that validates only catalog paths. This allows `just validate`/plan preflight to pass while Ansible service convergence subsequently fails. Legacy private inputs remain recoverable from Git `HEAD`, but the normal migration command skips every legacy import whenever `site.yaml` exists.

## Evidence boundary and source inventory

- Public repository: `feat/canonical-values-model`, ahead of its upstream with substantial pre-existing uncommitted work. This audit adds only this report.
- Nested private repository: `feat/canonical-values-cutover` with pre-existing deletions/modifications/untracked artifacts. It remains untouched.
- Selected canonical site parsed successfully without reporting its topology values. It has seven enabled public service IDs, six guest resources, and one shared-host resource.
- Current selected-site canonical inputs are `site.yaml`, `.sops.yaml`, `secrets.sops.yaml`, and `migration-manifest.json`; all observed at mode `0600`.
- `generated/` contains the four expected non-secret projections plus a manifest, all derived artifacts at mode `0600`.
- The manifest identifies this as an adoption of an existing canonical site with zero legacy move operations and excludes secret values.
- Private Git `HEAD` retains recoverable deleted legacy `.env`, `terraform.tfvars`, static inventory, `site.json`, and DNS JSON sources. Their key inventories were summarized by class only; no values were emitted.
- SOPS and age executables are installed, but no external age-key file was exported/discovered in this audit environment. Therefore no bundle decryption or logical-path enumeration was attempted. The current Hermes-path presence stated in the audit request is treated as prior verified evidence, not re-proven here.

## Table 1 — Canonical non-secret configuration families

Classification normalization: every row has exactly one classification from the
requested vocabulary. Where a compact table cell uses prose (for example,
"canonical-only delivery contract"), the following mapping is authoritative:

+--------------------------------+----------------------------+
| row                            | classification             |
+--------------------------------+----------------------------+
| Site/lifecycle                 | canonical-only             |
| Platform/resources/service     | canonical-only             |
| DNS records                    | canonical-only             |
| Canonical projections          | generated derived artifact |
| Bootstrap root password        | canonical-only             |
| Operator password              | canonical-only             |
| Provider credential            | canonical-only             |
| Hermes runtime credentials     | canonical path mismatch    |
| Non-Hermes runtime credentials | missing migration          |
| Technitium/DNS credentials     | dual-read                  |
| Legacy dotenv values           | missing migration          |
| Legacy tfvars and inventory    | orphaned legacy            |
| Legacy DNS JSON                | orphaned legacy            |
| Site adoption metadata         | intentionally deferred     |
| Setup                          | dual-write                 |
| Validate                       | canonical-only             |
| Plan                           | dual-write                 |
| Apply provider                 | canonical-only             |
| Apply service roles            | canonical path mismatch    |
+--------------------------------+----------------------------+

+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| canonical domain     | source locations         | canonical target          | actual consumer paths         | writer/generator     | lifecycle                | status/classification       | remediation action         | regression test              |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Site/lifecycle       | site.yaml;               | site.*                    | settings.py policy;           | canonical-render.py  | setup validates;         | canonical-only              | Keep site.yaml as sole      | selected-site policy tests; |
|                      | migration manifest       |                           | plan-infra.sh; apply-infra.sh |                      | plan/apply consume       |                             | lifecycle authority.        | no legacy policy fallback.  |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Platform/resources   | site.yaml; legacy        | platform.*, resources.*   | generated terraform vars;     | canonical-render.py  | validate renders;        | canonical-only for selected | Retain explicit legacy-only | projection key-set parity;  |
| and service shape    | tfvars/inventory in HEAD |                           | inventory; ansible vars; DNS  |                      | plan/apply verify/use    | canonical execution branch  | compatibility branch only.  | consumer binding tests.     |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| DNS records          | site.yaml platform DNS;  | platform.dns; derived     | generated/dns-records.json;   | canonical-render.py  | validate and canonical   | canonical-only              | Keep generated DNS file;    | canonical DNS check uses    |
|                      | legacy DNS JSON in HEAD  | service endpoint records  | DNS sync environment          |                      | Ansible transport        |                             | remove legacy only after    | generated projection only.  |
|                      |                          |                           |                               |                      |                          |                             | completeness acceptance.    |                              |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Canonical projections| site.yaml + catalog      | generated/*.json +        | plan/apply, canonical Ansible | canonical-render.py; | plan refreshes;          | generated derived artifact  | Do not treat generated data | stale/tampered/mixed        |
|                      |                          | manifest                  | transport                     | workspace-preflight  | apply verifies           |                             | as authority. Verify before | projection rejection tests. |
|                      |                          |                           |                               |                      |                          |                             | every side effect.          |                              |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+

Evidence: `scripts/canonical_projections.py`, `scripts/workspace-preflight.py:139-175`, `scripts/plan-infra.sh:45-88`, `scripts/apply-infra.sh:70-96`, and `scripts/apply-ansible-services.py:131-176,356-405` implement the canonical model/projection verification path. `scripts/site-context.sh:5-36` requires selected canonical authority unless the explicit legacy compatibility flag is set.

## Table 2 — Secret and credential contract families

+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| canonical domain     | source locations         | canonical target          | actual consumer paths         | writer/generator     | lifecycle                | status/classification       | remediation action         | regression test              |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Bootstrap root       | SOPS bundle; legacy      | secrets.bootstrap.*       | ansible-bootstrap;            | explicit setup or    | apply host bootstrap/    | canonical-only delivery     | Preserve inherited/default  | per-resource override,      |
| password             | dotenv aliases in HEAD   |                           | ansible-host-identity         | approved migration   | identity only            | contract                    | plus resource overrides.    | ambiguity and cleanup tests.|
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Operator password    | SOPS bundle; legacy      | secrets.operator.password | ansible-host-identity         | migrate-secret-      | apply host identity      | canonical-only delivery     | Keep identity-neutral path; | old/new equal/conflict;     |
|                      | identity-named alias     |                           |                               | bundle.py            |                          | contract                    | migrate old alias safely.   | no plaintext/rollback tests.|
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Provider credential  | SOPS bundle; legacy      | secrets.providers.        | canonical-provider-env.py ->  | approved SOPS setup  | plan/apply provider      | canonical-only              | Keep one transient provider | provider preflight and      |
|                      | provider env in HEAD     | proxmox.api_token         | OpenTofu environment          |                      | boundary                 |                             | environment contract.       | environment isolation tests.|
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Hermes runtime       | SOPS bundle (prior       | services.hermes.secrets.* | catalog declares same paths;  | no complete importer | apply Ansible service    | canonical path mismatch     | Make catalog and delivery   | catalog-to-delivery exact   |
| credentials          | evidence); legacy env    |                           | delivery instead asks         | for legacy import    | boundary                 |                             | derive one contract from    | equality + conditional      |
|                      | keys in HEAD             |                           | secrets.services.hermes.*     |                      |                          |                             | catalog, not a hard-coded   | requirement tests.          |
|                      |                          |                           |                               |                      |                          |                             | second namespace.           |                              |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Non-Hermes runtime   | recoverable legacy       | no agreed catalog paths   | secret_delivery.py asks for   | no canonical importer| apply Ansible service    | missing migration           | Define catalog-owned paths, | enabled-service bundle      |
| credentials          | dotenv/inventory inputs  | for selected enabled      | independent secrets.services. |                      | boundary only            |                             | map legacy keys to them,    | completeness, migration     |
|                      | in HEAD                  | services                  | <service>.* paths             |                      |                          |                             | then import without rotate. | preservation, no generation.|
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Technitium/DNS       | recoverable legacy env;  | no catalog requirement or | legacy token bootstrap reads  | legacy bootstrap only| legacy service path;     | dual-read / intentionally   | Decide a catalog path and   | canonical DNS secret        |
| credentials          | SOPS status not exposed  | delivery contract         | .env; canonical DNS transport |                      | canonical projection     | deferred                    | transient consumer contract | availability + no legacy    |
|                      |                          |                           | supplies only records file    |                      | does not supply token    |                             | before runtime cutover.     | env in canonical mode.      |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+

Evidence:
- `infra/services.json:261-281` declares only Hermes runtime paths, under `services.hermes.secrets.*`, including conditional requirements.
- `scripts/secret_delivery.py:66-96` creates every service requirement beneath `secrets.services.<service>.*`; this conflicts with the catalog’s Hermes namespace and has no catalog declaration for the other enabled runtime consumers.
- `docs/canonical-values-mapping-v1.md:268-290` documents a third, older `secrets.<service>.<key>` convention. The mapping is explicitly incomplete, but its rows must be reclassified as deferred or migrated rather than left as a competing apparent authority.
- `scripts/service_catalog.py:118-168` can derive value-free model-aware required paths, but `scripts/secret_delivery.py:145-148` does not consume that catalog.
- `scripts/workspace-preflight.py:178-208` verifies catalog-required service paths plus bootstrap-SSH and provider paths, not the hard-coded delivery requirements.
- `scripts/apply-ansible-services.py:651-655` creates delivery environments from the independent delivery requirement list after preflight/host phases.
- `scripts/apply-ansible-services.py:408-416,471-478` retains the Technitium token bootstrap and legacy env-file refresh path for DNS execution.
- `scripts/secret_delivery.py:219-240` also resolves every Hermes delivery requirement unconditionally, while the catalog makes individual Hermes credentials conditional on feature flags (`infra/services.json:273-282`; `scripts/service_catalog.py:134-145`). Disabled subfeatures can therefore require credentials contrary to the catalog contract.
- The public ingress/provider reference convention (`scripts/canonical_values.py:166-175` and mapping line 281) disagrees with the `caddy` service-style delivery row at `scripts/secret_delivery.py:95`. Caddy is not a catalog service, so this must become an ingress/provider requirement tied to its canonical reference, not a catalog-external service delivery bypass.
- The documented public contract explicitly says provider/runtime/recovery/generated secret authority for all live consumers remains deferred: `docs/canonical-values-secret-operations.md:164-173`.

## Table 3 — Legacy-source and migration families

+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| canonical domain     | source locations         | canonical target          | actual consumer paths         | writer/generator     | lifecycle                | status/classification       | remediation action         | regression test              |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Legacy dotenv        | deleted site `.env`      | mixed: non-secret model,  | legacy run-infra env file;    | migrate-values.py    | setup/plan/apply invoke  | orphaned legacy / missing   | Build canonical-site import | existing site plus legacy    |
| values               | recoverable from HEAD    | SOPS logical secrets      | legacy Ansible token paths    |                      | migration helper         | migration                   | that reads only approved    | sources imports values once |
|                      |                          |                           |                               |                      |                          |                             | recoverable sources.        | without generating values.  |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Legacy tfvars        | deleted terraform.tfvars | site.yaml + generated     | legacy OpenTofu vars only;    | migrate-values.py;   | setup/plan/apply invoke  | orphaned legacy /           | Retain only migration input | existing canonical site can |
| and inventory        | and static inventory in  | compatibility projections | canonical branch uses         | canonical-render.py  | migration helper         | generated derived artifact  | until model/projection      | import then verify no       |
|                      | HEAD                     |                           | generated projections         |                      |                          |                             | completeness is proven.     | legacy consumer remains.    |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Legacy DNS JSON      | deleted DNS JSON in HEAD | platform.dns + generated  | canonical DNS records file;   | canonical-render.py  | validation/canonical     | orphaned legacy /           | Import non-secret records   | canonical render equivalence|
|                      |                          | DNS projection            | legacy .env file path         |                      | service transport        | generated derived artifact  | only when absent; preserve  | and legacy-input retention  |
|                      |                          |                           |                               |                      |                          |                             | legacy until verified.      | test.                       |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Site adoption        | site.yaml + migration    | adopted canonical site    | policy and projection tools   | adoption workflow    | audit/migration          | intentionally deferred      | Extend adoption/import path | adoption with legacy source |
| metadata             | manifest                 | metadata                 |                               |                      |                          |                             | rather than treating        | has dry-run, backup,        |
|                      |                          |                           |                               |                      |                          |                             | `site.yaml` as import proof.| rollback, idempotence tests.|
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+

Evidence:
- `scripts/migrate-values.py:860-1010` is a legacy-file mutator and includes generated-secret behavior (`893-899`), so it cannot be reused unmodified for a preserve-first canonical import.
- `scripts/migrate-values.py:1051-1067` returns success and skips all migration when `site.yaml` exists.
- `tests/test_migrate_values.py:21-29` locks that skip in as expected behavior, explaining why legacy sources were not imported after adoption.
- `justfile:114-126` invokes this skip before both plan and apply, so current normal workflow cannot repair canonical bundle completeness.

## Table 4 — Lifecycle and execution matrix

+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| canonical domain     | source locations         | canonical target          | actual consumer paths         | writer/generator     | lifecycle                | status/classification       | remediation action         | regression test              |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Setup                | scaffold/site.yaml; SOPS | canonical model, bootstrap| values.sh; ssh-initialize;    | setup recipes;       | may create bootstrap key | dual-write / intentionally  | Split initialization from   | noninteractive setup does   |
|                      | bundle                   | SSH identity              | optional provider bootstrap   | ssh-initialize.py    | and may mutate secrets   | deferred                    | legacy migration/import.    | not mutate; idempotence.    |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Validate             | selected site + bundle   | model, projections,       | workspace-preflight;          | read-only preflight  | validates model/project. | canonical-only but          | Validate the exact delivery | delivery requirements equal |
|                      |                          | catalog-required secrets  | validate-values.sh            |                      | and catalog paths        | incomplete secret boundary  | requirements for every      | catalog and bundle before   |
|                      |                          |                           |                               |                      |                          |                             | enabled service.            | a live operation.           |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Plan                 | generated projections +  | provider child env +      | plan-infra.sh; provider env;  | plan-infra.sh         | currently refreshes       | dual-write generated        | Move projection refresh to  | failed preflight preserves  |
|                      | SOPS bundle              | saved plan                | OpenTofu                      |                      | projections before plan   | artifact / canonical input  | explicit render/setup or    | saved plan and generated    |
|                      |                          |                           |                               |                      |                          |                             | document as intentional.    | bundle ordering.            |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Apply provider       | verified saved plan +    | OpenTofu provider token   | apply-infra.sh ->             | apply-infra.sh        | validates all current     | canonical-only              | Keep separate from Ansible  | provider success and        |
|                      | SOPS bundle              |                           | canonical-provider-env.py     |                      | catalog required paths    |                             | result; never infer service | later service failure are   |
|                      |                          |                           |                               |                      |                          |                             | success from provider exit. | reported independently.     |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+
| Apply service roles  | verified projection,     | transient service env     | apply-ansible-services.py ->  | apply-ansible-        | decrypts/delivers after   | canonical path mismatch /   | Add a pre-service, catalog- | missing required runtime    |
|                      | SOPS bundle              |                           | Ansible playbooks             | services.py           | host identity/readiness   | missing migration           | derived bundle-completeness | path fails before hosts or  |
|                      |                          |                           |                               |                      | phases                    |                             | gate before any host action.| provider mutation.          |
+----------------------+--------------------------+---------------------------+-------------------------------+----------------------+--------------------------+-----------------------------+----------------------------+------------------------------+

Important ordering observations:

1. `plan-infra.sh:22-26` runs secret preflight and then deletes saved plan artifacts. It then refreshes generated projections (`45-71`), so planning is not purely read-only with respect to derived private artifacts.
2. `apply-infra.sh:27-33` performs `--require-secrets` preflight before saved-plan checks, then applies OpenTofu at `120-134`; only afterward does it enter service convergence at `143-157`.
3. In canonical mode, `apply-ansible-services.py:623-655` completes direct-access/host-identity phases before constructing service secret environments. Thus an absent runtime path can surface after live provider mutation and host-facing activity rather than at validation.
4. `run-infra.sh:34-39` deliberately parses `.env` only in non-canonical mode; that is correct isolation, but makes legacy secret import a prerequisite rather than a fallback option.
5. The prior saved plan/metadata is deleted before projection render/verification, guest-mount preflight, and `tofu init` (`scripts/plan-infra.sh:22-26,45-117`). Any later prerequisite failure destroys the reviewed operator artifact. Move deletion immediately before `tofu plan -out` and regression-test failed render, Ansible preflight, and `tofu init` preservation.
6. Canonical `just setup` initializes only `site.yaml` (`scripts/values.sh:71-77`) but immediately invokes SSH initialization (`justfile:26`), which requires both a selected-site SOPS policy and a readable external age key (`scripts/ssh-initialize.py:59-89,157-160`). The fresh-site contract must either scaffold/preflight those prerequisites or defer initialization with an actionable message.

## Why tests and validation allowed an incomplete cutover

1. `tests/test_secret_delivery.py` tests the delivery helper’s independent `secrets.services.*` contract, but has no assertion that its requirements equal `infra/services.json` required paths.
2. `tests/test_secret_delivery.py:158-161` treats a service with no hard-coded delivery requirement as valid bootstrap-only delivery. Catalog completeness is not part of that test.
3. `tests/test_workspace_preflight.py` checks SOPS metadata/path transport but does not construct an enabled canonical model plus delivery requirements and assert the bundle covers the same path set.
4. `tests/test_apply_ansible_services.py` mocks `SopsAgeProvider`/`deliver` for bootstrap and transient environments. It does not exercise the order `preflight -> provider apply -> service environment construction` with a missing runtime requirement.
5. `tests/test_operational_cutover.py:23-31` checks script substrings (canonical variables, inventory, provider wrapper), not complete live-operation preconditions or catalog/delivery parity.
6. `tests/test_migrate_values.py:21-29` asserts that canonical-site migration skips legacy inputs. There is no alternate adoption/import test for an existing `site.yaml` plus recoverable legacy sources.
7. Documentation correctly labels broad runtime consumer authority as deferred (`docs/canonical-values-secret-operations.md:164-173`), but current `apply-ansible-services.py:651-655` has already crossed into runtime delivery. The documented scope and executed behavior differ.
8. No direct test exercises `canonical-provider-env.py` command parsing, canonical-site rejection, transient environment scoping, sanitized failure, or exec handoff; `tests/test_operational_cutover.py:23-31` only checks references in shell source.
9. No cross-contract test asserts: evaluated catalog paths equal delivery paths; classification/consumer/environment binding parity; disabled Hermes subfeatures do not resolve credentials; the ingress provider uses its canonical secret reference; or no noncatalog service can bypass selected-service validation.

## Recommended remediation design (not implemented)

### Decision 1 — Canonical namespace

Adopt the catalog as the sole authority for every logical secret path, classification, consumer, and conditional requirement. Preserve the established service namespace already used by the Hermes catalog and current bundle evidence: `services.<service>.secrets.<key>`. Do not retain a second `secrets.services.<service>.<key>` namespace.

Implementation shape:
- Add every enabled service’s logical runtime requirements to `infra/services.json` with classifications and conditional rules.
- Replace hard-coded `SERVICE_REQUIREMENTS` paths in `scripts/secret_delivery.py` with a catalog-derived requirement builder that maps catalog paths to explicit environment names in one reviewed table. Feed it the loaded canonical model so conditional feature requirements are evaluated once, before delivery.
- Make `workspace-preflight.py` validate the exact derived delivery set needed by the selected canonical model, plus host/bootstrap/provider contracts as appropriate for the requested lifecycle.
- Ensure a service with no secret requirements remains valid, but only because the catalog explicitly has none.
- Keep bootstrap/operator/provider requirements in an explicit non-service registry if they are intentionally outside the service catalog. Model Caddy/Cloudflare as an ingress-provider requirement bound to its canonical `secret_ref`, not as a noncatalog service.

### Decision 2 — Preserve recoverable legacy values

Do not generate replacement credentials. Implement an explicit canonical-site import mode that reads only allow-listed legacy sources and writes only an approved encrypted bundle through SOPS. It must:

1. require an explicit migration/apply flag after a default dry-run;
2. validate source-key presence and target logical-path ownership without printing values;
3. fail if target and source differ; allow idempotent duplicate values;
4. preserve unrelated bundle namespaces and recipients;
5. create a ciphertext-only backup and value-free migration manifest;
6. atomically replace the encrypted bundle only after schema/path validation; and
7. leave legacy files untouched until post-import bundle-completeness verification succeeds.

### Decision 3 — Existing canonical-site adoption/import

Replace the unconditional `site.yaml` skip with two explicit paths:

- legacy-only layout: existing compatibility migration;
- canonical site with legacy source files or a recoverable Git-HEAD source: report/import mode that validates the existing model and imports only missing approved canonical paths.

The importer must never infer absence merely because `site.yaml` exists. It should report source class, target path, presence state, conflict state, and whether it would write—without values.

### Decision 4 — Safe legacy deletion sequence

1. Preserve private working-tree status and create a ciphertext-only backup before any private mutation.
2. Restore a legacy file only into a restricted temporary migration workspace when a working-tree copy is absent but HEAD provenance confirms recoverability; do not restore it into the private worktree merely for inspection.
3. Import/reconcile allow-listed values into the canonical bundle.
4. Validate catalog/delivery/bundle completeness and render/verify non-secret projections.
5. Run full unit/public validation and a separately authorized non-mutating plan.
6. Remove legacy sources only after all canonical consumer contracts prove they no longer read them. Keep an explicit legacy-only compatibility branch for unreconciled sites.

### Decision 5 — Fail closed before live operations

Create one common pre-service gate, invoked by canonical plan/apply according to lifecycle need, that:

- loads selected site plus catalog;
- derives enabled services and conditional requirements from the model;
- derives delivery contracts from the same catalog;
- rejects catalog paths without delivery environment bindings;
- rejects delivery bindings without catalog ownership;
- validates all required SOPS logical paths without outputting values;
- executes before saved-plan deletion, OpenTofu apply, direct-access readiness, host identity, and Ansible service roles.

Provider-only plan can require only provider/bootstrap prerequisites if it never runs host/service consumers. Combined `apply` must require the full service-delivery set before the provider phase.

### Decision 6 — Backup, rollback, and validation

- Use the established SOPS policy and recipient-preservation checks; never print recipient values.
- Use mode-restricted temporary directories, atomic replacement, ciphertext hash/size metadata, and a refusal to overwrite a prior migration backup.
- On any failure, restore the original ciphertext and leave legacy sources unchanged.
- Add focused tests for: catalog/delivery parity; conditionally enabled paths; missing bundle path before provider/host actions; source-only import; identical duplicate; conflict; no generated replacement; recipient preservation seam; rollback; idempotent rerun; temporary workspace cleanup; canonical-only rejection of legacy env reads.
- Move saved-plan deletion in `plan-infra.sh` until all render/verification/Ansible/initialization prerequisites pass; test that each prerequisite failure preserves existing plan artifacts.
- Repair the canonical setup boundary: either scaffold/preflight selected-site SOPS policy plus external key before `ssh-initialize`, or defer initialization with an actionable prerequisite message. Test the public recipe ordering with a fake SOPS/key boundary.

## Required follow-up verification after separately authorized remediation

1. Focused unit tests for catalog-to-delivery parity and encrypted-bundle importer transformations.
2. Complete unit suite and `just validate` with explicit selected canonical site context.
3. Read-only SOPS path-completeness preflight that reports path status only.
4. A non-mutating canonical plan with reviewed action counts; no apply in this step.
5. Only after explicit approval: apply, with provider result, host-identity result, and each service result reported separately.
6. Fresh no-drift plan after successful service convergence.

## Audit limitations

- This audit did not decrypt the selected SOPS bundle because no external age identity was available in the audit environment. The report relies on catalog/code contract inspection and the request’s prior Hermes bundle-path evidence; real private bundle completeness remains a separate, operator-gated check.
- No Hermes-container repository was inspected.
- No private value/state content, live endpoint, plan content, or service state was inspected.

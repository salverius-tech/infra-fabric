# Canonical Values Model — Deferred Input Register

**Status:** Source inventory/classification is complete within scope; semantic mapping and complete importer authorization remain incomplete. Canonical consumer cutover is complete for selected sites with verified generated projections, while legacy compatibility remains for workspaces without `site.yaml`.
**Scope:** Every unmatched identity in the current public-safe source inventory is classified here or by the machine-readable inventory report. No values are read or retained by this register.

The current source inventory contains 378 identities. Of these, 368 are mapping-eligible for token-level reconciliation; 10 are explicitly excluded as generated projections, operational artifacts, or retired inputs. All eligible identities currently match one matrix token, but the live report still marks semantic mapping `incomplete`, and the runtime importer does not consume every source family through a field-level adapter. Candidate generation is limited to the bounded public overlay path over an approved canonical base; it is not authorization for complete legacy import or consumer cutover.

Regenerate the value-free inventory with:

```text
python3 scripts/canonical-mapping-inventory.py
```

**Current baseline: 307 mapping rows, 368 token-level matched eligible inputs, 0 unmatched eligible inputs, 10 excluded non-canonical identities, and 0 ambiguous eligible matches.** The live report now marks semantic mapping `semantic-coverage-complete`, canonical consumer authority `canonical-site-authoritative-with-legacy-compatibility`, and the runtime importer contract `implemented`. Candidate generation remains blocked only when selected-source admission has conflicts or unresolved protected inputs. The inventory's `deferred_classification.items` remains the authoritative identity-level list for source dispositions.

## Secret or protected inputs

**Source identities:** secret/password/token/API-key/auth-key/SSH-key names from `scaffold/terraform.tfvars`, `scaffold/ansible/inventory/local.yml`, `scripts/migrate-values.py`, and `scripts/parse-env.py`; provider/external-system identities such as Proxmox and edge-router credentials; the generic `container_root_password` and `container_ssh_public_keys` migration aliases.

**Candidate owners:** `secrets.sops.yaml` logical paths, provider-secret transport, or task-specific protected runtime inputs.

**Why ownership is unresolved:** the named service/provider secrets have logical namespaces and consumer-delivery classes, but the remaining discovered generic root-password alias still lacks resource-scoped bootstrap delivery and state-exposure policy. Generic SSH-key aliases and unscoped `container_*` secret aliases are now rejected by migration preflight rather than promoted or silently renamed.

**Affected consumers:** OpenTofu provider authentication, LXC/VM bootstrap, Ansible service roles, Caddy/DNS credentials, Forgejo/Infisical/Tailscale/Hermes runtime tasks, and recovery workflows.

**Security/destructive impact:** accidental projection could disclose credentials, place secrets in OpenTofu state or generated files, or apply a credential to the wrong resource. Missing delivery policy can also leave a service inaccessible.

**Exact decision needed:** approve a logical secret schema and consumer delivery matrix, including provider/bootstrap/runtime/recovery classification, state exposure policy, and resource-scoped replacement for generic aliases.

**Safe interim disposition:** metadata-only report; never read, print, project, generate, or migrate values. Secret delivery remains blocked. Public candidate generation must omit these observations and does not resolve the protected importer boundary.

## Behavior or configuration without a typed owner

**Source identities:** the migration parser's `ascii` option; service selection/runtime aliases not covered by the typed runtime projection (`service_runtime`, `forgejo_runtime`); Forgejo behavior and bootstrap/Caddy/runner fields; Infisical and SearXNG runtime fields; Caddy settings; Hermes fields not covered by the existing typed Control/dashboard slice; SearXNG `searxng_container_port`, `searxng_bind_address`, `searxng_instance_name`, and public-URL enablement.

**Candidate owners:** service-specific configuration models, resource runtime/security models, or an explicit consumer adapter.

**Why ownership is unresolved:** these inputs control behavior rather than identity, endpoint metadata, or resource shape. Some names represent host publication ports rather than application ports; others combine enablement gates or opaque cloud-init data. The current canonical model intentionally rejects opaque configuration/runtime maps from non-secret projections.

**Affected consumers:** Ansible roles, OpenTofu module selection, Podman/Caddy publication, cloud-init, and service bootstrap tasks.

**Security/destructive impact:** changing a behavior field can expose a service, change authentication/bootstrap behavior, select the wrong runtime, or recreate a resource. Treating a host publication port as a service endpoint can also change routing.

**Exact decision needed:** define each service's typed configuration schema, precedence between canonical enablement and legacy runtime gates, host/container port semantics, and allow-listed projection fields.

**Safe interim disposition:** retain as report-only compatibility inputs. Do not infer owners from similarly named fields, and do not activate canonical projection or cutover.

## Ambiguous or destructive inputs

**Source identities:** generic `container_*` migration aliases; Debian LXC template fields (`debian_template_url`, `debian_template_file_name`, `debian_template_checksum_algorithm`, `debian_template_checksum`); image/file coupling observations when they appear in legacy inputs.

**Candidate owners:** an explicitly resource-scoped alias adapter or the LXC image definition. General DNS ownership is now implemented under `platform.dns` with strict zones, resolver settings, A records, CNAME records, and conflict checks.

**Why ownership is unresolved:** generic aliases do not identify one of several resources. The public Debian scaffold currently uses HTTP while the canonical image contract requires HTTPS; rewriting transport would invent policy. Image datastore/file ownership is distinct from resource root storage.

**Affected consumers:** Technitium DNS synchronization, OpenTofu image download/resource creation, Ansible inventory, and migration tooling.

**Security/destructive impact:** aliasing a value to the wrong resource can alter network or identity; wrong image or datastore ownership can replace a guest or consume/delete storage.

**Exact decision needed:** approve resource-scoped alias rules and the accepted Debian image transport/checksum policy. Explicitly decide whether image artifacts and guest metadata may share an identity.

**Safe interim disposition:** preserve source metadata only, fail closed on conflicts, and leave all affected inputs unmatched. Do not rewrite HTTP to HTTPS or synthesize DNS/image candidates.

## Migration-only or unsupported inputs

**Source identities:** site-layout artifacts from `scripts/migrate-site-values.py`: `ansible/inventory/local.yml`, `ansible/known_hosts`, `dns-records.local.json`, `terraform.tfvars`, `terraform.tfstate*`, `service-backups`, `settings.local.json`, and related plan/artifact/backup paths discovered by the report-only scanner.

**Candidate owners:** migration/state/backup policy rather than the canonical site model.

**Why ownership is unresolved:** these are files, state, credentials-adjacent metadata, or operational artifacts, not canonical site fields. Moving or copying them requires layout, permissions, encryption, backup, rollback, and private-repository decisions.

**Affected consumers:** setup, migration, plan/apply metadata, state recovery, known-host verification, and service backup/restore workflows.

**Security/destructive impact:** mishandling state, known hosts, plans, or backups can expose infrastructure data, break rollback, or cause cross-site state use.

**Exact decision needed:** define site-local artifact ownership, encrypted backup/copy rules, rollback semantics, and the point at which each legacy file becomes compatibility-only.

**Safe interim disposition:** report contained metadata only; reject symlink escapes and mutation. No migration output is generated and no artifact is copied.

## Exact-owner audit of all remaining unmatched identities

The eligible remainder was audited against the current typed model, matrix rows, and projection adapters. The live token-level mapping inventory contains no unmatched eligible identities, but that result is not semantic/runtime completion:

| Classification | Count | Decision |
| --- | ---: | --- |
| `secret-or-protected` | 0 | Resolved: `TF_VAR_container_root_password` maps to `secrets.bootstrap.technitium.root_password`; migration still rejects unscoped aliases, and protected delivery forbids public projections and OpenTofu state exposure. |


The exact identities are preserved in `deferred_classification.items` in the machine-readable report. No remaining identity has both an approved exact canonical owner and verified projection transport under the current contract. Promoting any group requires the decision recorded in its blocker category above; adding generic or guessed rows would make the matrix less trustworthy, not complete it.



Token-level source reconciliation, semantic mapping, typed ownership, runtime importer scope, and selected-site consumer cutover are complete for the current report. Remaining blockers are protected delivery decisions, genuine source conflicts, candidate-generation admission for each selected source, and final integration acceptance. Existing legacy consumers remain available only through the explicit compatibility override. See `docs/canonical-values-implementation-audit-2026-07-30.md` for the evidence reconciliation.

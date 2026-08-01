# Canonical Values Model — Deferred Input Register

**Status:** Source inventory/classification, semantic mapping, normalized non-secret importer admission, and canonical consumer authority for selected sites are implemented and test-covered. Candidate generation remains selected-source gated; protected delivery, private-site migration acceptance, semantic plan equivalence, and compatibility removal remain open. Legacy compatibility remains an explicit opt-in for workspaces without `site.yaml`.
**Scope:** Every unmatched identity in the current public-safe source inventory is classified here or by the machine-readable inventory report. No values are read or retained by this register.

The current source inventory contains 378 identities. Of these, 368 are mapping-eligible and 10 are explicitly excluded as generated projections, operational artifacts, or retired inputs. The live inventory requires semantic path, classification, consumer-evidence, source-reconciliation, and normalized importer gates; those gates are now implemented for the declared public scope. Candidate generation remains limited to an approved canonical base plus selected-source admission: it is not authorization for arbitrary legacy import, secret-bundle generation, or compatibility removal.

Regenerate the value-free inventory with:

```text
python3 scripts/canonical-mapping-inventory.py
```

**Current baseline: 307 mapping rows, 368 matched eligible inputs, 0 unmatched eligible inputs, 10 excluded non-canonical identities, and 0 ambiguous eligible matches.** The live report marks semantic mapping `semantic-coverage-complete`, canonical consumer authority `canonical-site-authoritative-with-legacy-compatibility`, and the runtime importer contract `implemented`. Candidate generation is still blocked by the explicit selected-source runtime-admission gate, including conflicts or unresolved protected inputs. The inventory's `deferred_classification.items` remains the authoritative identity-level disposition list.

## Secret or protected inputs

**Source identities:** secret/password/token/API-key/auth-key/SSH-key names from `scaffold/terraform.tfvars`, `scaffold/ansible/inventory/local.yml`, `scripts/migrate-values.py`, and `scripts/parse-env.py`; provider/external-system identities such as Proxmox and edge-router credentials; the generic `container_root_password` and `container_ssh_public_keys` migration aliases.

**Candidate owners:** `secrets.sops.yaml` logical paths, provider-secret transport, or task-specific protected runtime inputs.

**Why the boundary remains protected:** named service/provider secrets now have logical namespaces, consumer-delivery classes, and fail-closed state-exposure rules. Generic SSH-key aliases and unscoped `container_*` secret aliases remain rejected by migration preflight rather than promoted or silently renamed. Private recipient/key provisioning and selected-site operational delivery evidence are still required.

**Affected consumers:** OpenTofu provider authentication, LXC/VM bootstrap, Ansible service roles, Caddy/DNS credentials, Forgejo/Infisical/Tailscale/Hermes runtime tasks, and recovery workflows.

**Security/destructive impact:** accidental projection could disclose credentials, place secrets in OpenTofu state or generated files, or apply a credential to the wrong resource. Missing delivery policy can also leave a service inaccessible.

**Exact decision needed:** approve a logical secret schema and consumer delivery matrix, including provider/bootstrap/runtime/recovery classification, state exposure policy, and resource-scoped replacement for generic aliases.

**Safe interim disposition:** retain value-free metadata and deliver secrets only through the permitted protected consumer boundary. Never include them in public candidates, non-secret projections, logs, command-line arguments, or OpenTofu state. Candidate generation remains blocked when selected-source protected admission is unresolved.

## Behavior or configuration without a typed owner

**Source identities:** the migration parser's `ascii` option; service selection/runtime aliases not covered by the typed runtime projection (`service_runtime`, `forgejo_runtime`); Forgejo behavior and bootstrap/Caddy/runner fields; Infisical and SearXNG runtime fields; Caddy settings; Hermes fields not covered by the existing typed Control/dashboard slice; SearXNG `searxng_container_port`, `searxng_bind_address`, `searxng_instance_name`, and public-URL enablement.

**Candidate owners:** service-specific configuration models, resource runtime/security models, or an explicit consumer adapter.

**Why the boundary remains explicit:** these inputs control behavior rather than identity, endpoint metadata, or resource shape. Typed owners and strict importer contracts now exist for the declared service/runtime scope, while opaque or dynamic expressions remain report-only and cannot enter candidates or projections without an explicit adapter.

**Affected consumers:** Ansible roles, OpenTofu module selection, Podman/Caddy publication, cloud-init, and service bootstrap tasks.

**Security/destructive impact:** changing a behavior field can expose a service, change authentication/bootstrap behavior, select the wrong runtime, or recreate a resource. Treating a host publication port as a service endpoint can also change routing.

**Exact decision needed:** define each service's typed configuration schema, precedence between canonical enablement and legacy runtime gates, host/container port semantics, and allow-listed projection fields.

**Safe interim disposition:** retain unsupported or dynamic values as report-only compatibility inputs. Do not infer owners from similarly named fields; canonical projection remains limited to typed, evidence-backed paths.

## Ambiguous or destructive inputs

**Source identities:** generic `container_*` migration aliases; Debian LXC template fields (`debian_template_url`, `debian_template_file_name`, `debian_template_checksum_algorithm`, `debian_template_checksum`); image/file coupling observations when they appear in legacy inputs.

**Candidate owners:** an explicitly resource-scoped alias adapter or the LXC image definition. General DNS ownership is now implemented under `platform.dns` with strict zones, resolver settings, A records, CNAME records, and conflict checks.

**Why the boundary remains explicit:** generic aliases do not identify one of several resources. The public Debian scaffold currently uses HTTP while the canonical image contract requires HTTPS; rewriting transport would invent policy. Image datastore/file ownership is distinct from resource root storage and requires an explicit migration decision.

**Affected consumers:** Technitium DNS synchronization, OpenTofu image download/resource creation, Ansible inventory, and migration tooling.

**Security/destructive impact:** aliasing a value to the wrong resource can alter network or identity; wrong image or datastore ownership can replace a guest or consume/delete storage.

**Exact decision needed:** approve resource-scoped alias rules and the accepted Debian image transport/checksum policy. Explicitly decide whether image artifacts and guest metadata may share an identity.

**Safe interim disposition:** preserve source metadata, fail closed on conflicts, and do not rewrite HTTP to HTTPS or synthesize image candidates. General DNS ownership is typed and projected, but provider delivery and private-site acceptance remain separate gates.

## Migration-only or unsupported inputs

**Source identities:** site-layout artifacts from `scripts/migrate-site-values.py`: `ansible/inventory/local.yml`, `ansible/known_hosts`, `dns-records.local.json`, `terraform.tfvars`, `terraform.tfstate*`, `service-backups`, `settings.local.json`, and related plan/artifact/backup paths discovered by the report-only scanner.

**Candidate owners:** migration/state/backup policy rather than the canonical site model.

**Why the boundary remains operational:** these are files, state, credentials-adjacent metadata, or operational artifacts, not canonical site fields. Report-only inventory and transactional backup helpers exist; moving/copying them still requires private layout, permissions, encryption, restore, rollback, and private-repository evidence.

**Affected consumers:** setup, migration, plan/apply metadata, state recovery, known-host verification, and service backup/restore workflows.

**Security/destructive impact:** mishandling state, known hosts, plans, or backups can expose infrastructure data, break rollback, or cause cross-site state use.

**Exact decision needed:** define site-local artifact ownership, encrypted backup/copy rules, rollback semantics, and the point at which each legacy file becomes compatibility-only.

**Safe interim disposition:** report contained metadata only unless an explicitly authorized transactional migration is run; reject symlink escapes and unsafe mutation. Private-site artifact policy and restore rehearsal remain required before compatibility removal.

## Exact-owner audit of all remaining unmatched identities

The eligible remainder was audited against the current typed model, matrix rows, and projection adapters. The live token-level mapping inventory contains no unmatched eligible identities, but that result is not semantic/runtime completion:

| Classification | Count | Decision |
| --- | ---: | --- |
| `secret-or-protected` | 0 | Resolved: `TF_VAR_container_root_password` maps to `secrets.bootstrap.technitium.root_password`; migration still rejects unscoped aliases, and protected delivery forbids public projections and OpenTofu state exposure. |


The exact identities are preserved in `deferred_classification.items` in the machine-readable report. The current public matrix has no unmatched eligible identity; the remaining register entries describe protected, operational, dynamic, or migration-only boundaries rather than missing token matches. Promoting any such input still requires the explicit contract recorded in its blocker category; adding generic or guessed rows would make the matrix less trustworthy.



Source reconciliation, semantic mapping, typed ownership, normalized non-secret importer scope, and selected-site canonical consumer authority are complete for the current public report. Remaining blockers are selected-source candidate admission, private recipient/key and migration evidence, representative semantic plan equivalence, operational backup/restore and rollback rehearsal, and final compatibility removal. Existing legacy consumers remain available only through the explicit compatibility override. The historical audit above must be read with this reconciliation note.

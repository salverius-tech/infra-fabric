# Canonical Values Model — Deferred Input Register

**Status:** Review-required; no consumer cutover or candidate generation is authorized.
**Scope:** Every unmatched identity in the current public-safe source inventory is classified here or by the machine-readable inventory report. No values are read or retained by this register.

Regenerate the value-free inventory with:

```text
python3 scripts/canonical-mapping-inventory.py
```

Current baseline: 213 mapping rows, 226 matched inputs, 161 unmatched inputs, and 0 ambiguous matrix matches. The inventory's `deferred_classification.items` is the authoritative identity-level list; this document records the decision blockers that prevent promotion.

## Secret or protected inputs

**Source identities:** secret/password/token/API-key/auth-key/SSH-key names from `scaffold/terraform.tfvars`, `scaffold/ansible/inventory/local.yml`, `scripts/migrate-values.py`, and `scripts/parse-env.py`; provider/external-system identities such as Proxmox and edge-router credentials; the generic `container_root_password` and `container_ssh_public_keys` migration aliases.

**Candidate owners:** `secrets.sops.yaml` logical paths, provider-secret transport, or task-specific protected runtime inputs.

**Why ownership is unresolved:** a source name alone does not establish logical secret identity, permitted consumer, rotation policy, or whether the value belongs to a resource, service, provider, bootstrap task, or recovery path. Generic container credentials also lack resource scope.

**Affected consumers:** OpenTofu provider authentication, LXC/VM bootstrap, Ansible service roles, Caddy/DNS credentials, Forgejo/Infisical/Tailscale/Hermes runtime tasks, and recovery workflows.

**Security/destructive impact:** accidental projection could disclose credentials, place secrets in OpenTofu state or generated files, or apply a credential to the wrong resource. Missing delivery policy can also leave a service inaccessible.

**Exact decision needed:** approve a logical secret schema and consumer delivery matrix, including provider/bootstrap/runtime/recovery classification, state exposure policy, and resource-scoped replacement for generic aliases.

**Safe interim disposition:** metadata-only report; never read, print, project, generate, or migrate values. Candidate generation and secret delivery remain blocked.

## Behavior or configuration without a typed owner

**Source identities:** service selection/runtime aliases (`service_runtime`, `forgejo_runtime`, `tailscale_client_enabled`); Forgejo behavior and bootstrap/Caddy/database/runner fields; Infisical and SearXNG runtime fields; Caddy settings; Hermes fields not covered by the existing typed Control/dashboard slice; VM cloud-init/user inputs; SearXNG `searxng_container_port`, `searxng_bind_address`, `searxng_instance_name`, and public-URL enablement.

**Candidate owners:** service-specific configuration models, resource runtime/security models, or an explicit consumer adapter.

**Why ownership is unresolved:** these inputs control behavior rather than identity, endpoint metadata, or resource shape. Some names represent host publication ports rather than application ports; others combine enablement gates or opaque cloud-init data. The current canonical model intentionally rejects opaque configuration/runtime maps from non-secret projections.

**Affected consumers:** Ansible roles, OpenTofu module selection, Podman/Caddy publication, cloud-init, and service bootstrap tasks.

**Security/destructive impact:** changing a behavior field can expose a service, change authentication/bootstrap behavior, select the wrong runtime, or recreate a resource. Treating a host publication port as a service endpoint can also change routing.

**Exact decision needed:** define each service's typed configuration schema, precedence between canonical enablement and legacy runtime gates, host/container port semantics, and allow-listed projection fields.

**Safe interim disposition:** retain as report-only compatibility inputs. Do not infer owners from similarly named fields, and do not activate canonical projection or cutover.

## Ambiguous or destructive inputs

**Source identities:** top-level DNS shapes `settings`, `zones`, `a_records`, and `cname_records`; generic `container_*` migration aliases; Debian LXC template fields (`debian_template_url`, `debian_template_file_name`, `debian_template_checksum_algorithm`, `debian_template_checksum`); image/file coupling observations when they appear in legacy inputs.

**Candidate owners:** a general DNS zone/record model, an explicitly resource-scoped alias adapter, or the LXC image definition.

**Why ownership is unresolved:** DNS records can be owned by different services or an external resolver and may include aliases or policy, while generic aliases do not identify one of several resources. The public Debian scaffold currently uses HTTP while the canonical image contract requires HTTPS; rewriting transport would invent policy. Image datastore/file ownership is distinct from resource root storage.

**Affected consumers:** Technitium DNS synchronization, OpenTofu image download/resource creation, Ansible inventory, and migration tooling.

**Security/destructive impact:** wrong DNS ownership can redirect traffic; wrong image or datastore ownership can replace a guest or consume/delete storage; aliasing a value to the wrong resource can alter network or identity.

**Exact decision needed:** approve DNS ownership/record semantics, resource-scoped alias rules, and the accepted Debian image transport/checksum policy. Explicitly decide whether image artifacts and guest metadata may share an identity.

**Safe interim disposition:** preserve source metadata only, fail closed on conflicts, and leave all affected inputs unmatched. Do not rewrite HTTP to HTTPS or synthesize DNS/image candidates.

## Migration-only or unsupported inputs

**Source identities:** site-layout artifacts from `scripts/migrate-site-values.py`: `ansible/inventory/local.yml`, `ansible/known_hosts`, `dns-records.local.json`, `terraform.tfvars`, `terraform.tfstate*`, `service-backups`, `settings.local.json`, and related plan/artifact/backup paths discovered by the report-only scanner.

**Candidate owners:** migration/state/backup policy rather than the canonical site model.

**Why ownership is unresolved:** these are files, state, credentials-adjacent metadata, or operational artifacts, not canonical site fields. Moving or copying them requires layout, permissions, encryption, backup, rollback, and private-repository decisions.

**Affected consumers:** setup, migration, plan/apply metadata, state recovery, known-host verification, and service backup/restore workflows.

**Security/destructive impact:** mishandling state, known hosts, plans, or backups can expose infrastructure data, break rollback, or cause cross-site state use.

**Exact decision needed:** define site-local artifact ownership, encrypted backup/copy rules, rollback semantics, and the point at which each legacy file becomes compatibility-only.

**Safe interim disposition:** report contained metadata only; reject symlink escapes and mutation. No migration output is generated and no artifact is copied.

## Completion boundary

All four categories are intentionally deferred, not silently ignored. The canonical projection remains non-authoritative until the inventory reports zero unmatched identities and the associated typed schemas, protected delivery contracts, migration policy, and equivalence evidence are reviewed. Existing legacy OpenTofu and Ansible consumers remain active during this compatibility window.

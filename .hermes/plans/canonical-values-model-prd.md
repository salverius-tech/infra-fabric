# PRD: Canonical Site Values Model

**Status:** Draft — reviewer revision incorporated; implementation design still pending
**Branch:** `plan/canonical-values-model`
**Repository:** `infra-fabric`

## 1. Summary

`infra-fabric` currently distributes site configuration across `.env`, OpenTofu/Terraform `tfvars`, Ansible inventory, DNS JSON, and site metadata. The same logical values—service identity, addresses, hostnames, runtimes, credentials, and release settings—are therefore represented multiple times using platform-specific names.

This project introduces a canonical, platform-neutral site values model. Each site will declare its configuration once in `site.yaml` and its secrets once in an encrypted `secrets.sops.yaml`. Python-based validation and rendering will produce the inputs required by OpenTofu, Ansible, DNS synchronization, and runtime service configuration.

The first version includes migration from the existing layout, compatibility support, plan equivalence checks, rollback, and removal of permanent duplicate configuration surfaces.

## 2. Goals

- Establish one authoritative non-secret configuration document per site.
- Establish one authoritative encrypted secret document per site.
- Keep site identity, lifecycle policy, service selection, and service configuration together.
- Remove duplicated VMIDs, addresses, hostnames, domains, runtime choices, and public URLs.
- Preserve the current OpenTofu, Ansible, DNS, and service-role interfaces during migration.
- Generate platform-specific inputs rather than hand-maintaining them.
- Validate the complete site model before plan or apply.
- Bind plan and apply operations to an exact site/model identity.
- Support multiple independent sites in one private values repository.
- Preserve a deliberate migration and rollback path for existing private values repositories.
- Keep the public repository generic and public-safe.

## 3. Non-goals for version one

- 1Password integration.
- Infisical as the foundational secret source.
- Automatic synchronization between multiple secret providers.
- Site inheritance, shared bases, or overlays.
- Arbitrary Terraform or Ansible variable passthrough.
- Rewriting every OpenTofu module or Ansible role to use canonical names internally.
- Automatic production apply or destructive migration.
- Treating Terraform state as part of the canonical configuration model.

## 4. Decisions

### 4.1 Site layout

Each site is self-contained:

```text
values/
  settings.local.json              # repository/operator metadata only
  sites/
    dev/
      site.yaml                    # canonical non-secret model
      secrets.sops.yaml             # encrypted canonical secrets
      state/
        terraform.tfstate*
      generated/                   # disposable generated artifacts
      backups/                     # private site backups, if used
```

The target directory contract is explicit:

- `site.yaml` and `secrets.sops.yaml` are the only operator-edited configuration files;
- `state/` contains only state belonging to that site;
- `generated/` is ignored, mode `0700`, and contains disposable projections only;
- `backups/` is private, site-local, encrypted where it contains secrets or state, and is never used as an input path;
- `ansible/known_hosts` remains site-local during migration and is eventually stored under a site-local security/trust directory;
- plan files and plan metadata are site-local and are never reused across sites.

The root `settings.local.json` retains only values-repository remote and local operator metadata. It does not own service selection or site configuration. `VALUES_SITE` is required for validation, planning, applying, restoring, and teardown; commands that operate only on public source may remain site-independent.

### 4.2 Site metadata

Site metadata is merged into `site.yaml`. There is no separate authoritative `site.json` in the target model.

The canonical document owns:

- site name;
- site class;
- lifecycle;
- apply/destroy policy;
- enabled services;
- schema version.

### 4.2.1 Site metadata contract

Version one uses this exact site metadata structure:

```yaml
schema_version: 1

site:
  name: dev
  class: development
  lifecycle: disposable
  allow_apply: true
  allow_destroy: true
```

Field rules:

- `schema_version` is a required integer and must be `1` for version one.
- `site.name` is a required DNS-safe identifier and must match both the site directory name and `VALUES_SITE`.
- `site.class` is a required enum: `development`, `staging`, or `production`.
- `site.lifecycle` is a required enum: `disposable`, `persistent`, or `protected`.
- `site.allow_apply` is a required boolean authorizing site-level infrastructure mutation.
- `site.allow_destroy` is a required boolean authorizing destructive operations.
- Unknown fields under `site` are rejected unless introduced by a schema revision.

Safety constraints:

- `production` sites cannot use `lifecycle: disposable`.
- `production` sites cannot set `allow_destroy: true`.
- `protected` sites default to `allow_apply: false` and `allow_destroy: false`.
- Directory name, `VALUES_SITE`, and `site.name` must agree.
- Site metadata is necessary but not sufficient for mutation. Apply also requires an explicitly selected site, a matching reviewed plan, and the required acknowledgement for destructive changes.
- `allow_apply: false` permits validation and planning but rejects apply.
- `allow_destroy: false` rejects destructive changes even when ordinary apply is permitted.
- Production apply remains explicitly approved even when `allow_apply` is true.

### 4.3 Service selection

Service selection uses the service map itself. Each declared service has an `enabled` field:

```yaml
services:
  technitium:
    enabled: true
  forgejo:
    enabled: true
  hermes:
    enabled: false
```

The canonical loader validates enabled services against `infra/services.json` and checks the declared dependency graph. There is no second authoritative enabled-service list. The loader must translate the map into the service list expected by the current `scripts/settings.py` and OpenTofu `enabled_services` input during the transition.

Service selection must distinguish logical services from deployable resources. A service may run on a dedicated LXC/VM or on a shared host:

```yaml
services:
  searxng_onramp:
    enabled: true
    host: onramp_host
    runtime: rootless_podman
```

The model must represent logical service identity, hosting/resource ownership, dependencies, state capability, and shared-host relationships separately. Enabling or disabling a stateful service must produce an explicit destructive-change warning and require the existing apply/destroy acknowledgement path.

### 4.4 Site inheritance

Version one uses explicit, complete `site.yaml` files. There is no base-site inheritance or overlay precedence. A development site must have independent values, credentials, state, addresses, and lifecycle policy.

### 4.5 Secrets

Secrets are stored in one encrypted SOPS YAML file per site. The initial provider is SOPS using age recipients. 1Password and Infisical integrations are deferred.

The canonical model uses logical secret names. Platform-specific names such as `FORGEJO_ADMIN_PASSWORD` are renderer mappings, not operator-facing sources of truth.

### 4.6 Platform-specific values

The model permits narrowly typed, namespaced platform-specific overrides when a value is genuinely platform-specific:

```yaml
services:
  forgejo:
    ansible:
      write_initial_config: false
```

Unrestricted `extra_vars`, arbitrary Terraform maps, and arbitrary Ansible variable maps are prohibited because they would recreate the existing duplication problem.

## 5. User experience

An operator should be able to:

1. Select a site explicitly.
2. Edit one canonical non-secret document.
3. Edit one encrypted secret document when secrets change.
4. Run validation.
5. Review a plan generated from the canonical model.
6. Apply only the exact model that produced the reviewed plan.

The normal workflow should look like:

```text
VALUES_SITE=dev just validate
VALUES_SITE=dev just plan
VALUES_SITE=dev just apply
```

The public `just` command surface remains unchanged unless a deliberate follow-up decision changes it. Existing site-context safety requirements remain in force.

## 6. Canonical model

The first schema should be service-oriented and platform-neutral. It should represent intent rather than consumer variable names.

Illustrative structure:

```yaml
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
    bridge: vmbr0
    gateway: 192.0.2.1
    dns_servers:
      - 1.1.1.1
      - 9.9.9.9
    search_domain: example.internal

  storage:
    rootfs_datastore: local-lvm
    template_datastore: local

services:
  technitium:
    enabled: true
    runtime: lxc
    vmid: 106
    hostname: technitium-dns
    address: 192.0.2.53/24
    public_names:
      - dns.example.internal
      - technitium.example.internal
    resources:
      cores: 1
      memory_mb: 1024
      disk_gb: 8
    release:
      version: 15.2.0
      sha256: ...

  forgejo:
    enabled: true
    runtime: lxc
    vmid: 107
    hostname: forgejo
    address: dhcp
    expected_address: 192.0.2.62
    public_name: git.example.internal
    resources:
      cores: 2
      memory_mb: 2048
      disk_gb: 8
    database:
      type: sqlite
    storage:
      type: proxmox_volume
      storage_id: local-lvm
      size_gb: 32
      target: /var/lib/forgejo
```

The final schema must cover the current supported infrastructure concepts, including:

- Proxmox connection and node;
- template and image pins;
- shared network defaults;
- per-service runtime;
- VMID, hostname, address, gateway, bridge, VLAN;
- resources;
- storage and backup behavior;
- service enablement and dependencies;
- service public names and expected addresses;
- artifact versions and checksums;
- service-specific non-secret behavior;
- narrowly scoped platform overrides.

The schema must not blindly expose every current Terraform variable or Ansible role variable. Values should be added to the canonical schema only when they represent site intent or a justified platform boundary.

### 6.1 Version-one mapping contract

Before implementing the importer or cutover, create a versioned mapping matrix covering every supported service, runtime, and shared resource. Each row must define:

| Canonical path | Legacy source(s) | Generated consumer field(s) | Classification | Default/conflict behavior |
| --- | --- | --- | --- | --- |
| `services.forgejo.vmid` | `forgejo_container_vmid`, `forgejo_vmid` | `forgejo_container_vmid`, `forgejo_vmid` | public | equivalent numeric values normalize; conflicting values fail |
| `services.forgejo.public_name` | `forgejo_server_name`, `forgejo_domain` | Terraform server name, Ansible domain, Caddy name | public | normalized hostnames must agree |
| `platform.network.bridge` | `*_container_bridge`, inventory defaults | Terraform network bridge, Ansible host vars | public | explicit site value overrides scaffold default |
| `secrets.forgejo.admin_password` | `FORGEJO_ADMIN_PASSWORD`, inventory env lookup | `FORGEJO_ADMIN_PASSWORD` | secret | never printed; missing value fails unless generated idempotently |

The actual matrix must be generated from and checked against `infra/opentofu/variables.tf`, `infra/services.json`, `infra/ansible/inventory/tfvars.py`, `scripts/migrate-values.py`, and the scaffold contract. No renderer or migration phase is implementation-ready until every current supported input is classified as canonical, derived, Ansible-only, Terraform-only, deprecated, or unsupported.

The matrix must define normalization for quoted HCL values, CIDR versus bare addresses, `null`, `dhcp`, booleans, lists, checksums, generated names, and derived DNS records. Unknown legacy values must be retained in a review report rather than silently discarded.

### 6.2 Mapping-matrix contract

Every canonical field receives a versioned mapping row with:

```text
canonical path
type
required condition
legacy source path(s)
generated OpenTofu field(s)
generated Ansible field(s)
generated DNS/runtime field(s)
secret classification
normalization rule
default rule
conflict rule
destructive-change impact
```

For example, `services.forgejo.endpoints.public_names` maps legacy Forgejo domain/server-name values and DNS JSON into OpenTofu, Ansible, and DNS projections. Hostnames normalize to lowercase without a trailing dot; conflicting normalized names fail closed; DNS target/name changes require review. `resources.guests.forgejo.identity.vmid` maps legacy Forgejo VMID values into OpenTofu and inventory fields; differing integers fail closed and VMID changes are identity/replacement changes.

The matrix is complete only when checked against `infra/opentofu/variables.tf`, `infra/services.json`, `infra/ansible/inventory/tfvars.py`, `scripts/migrate-values.py`, `scripts/migrate-site-values.py`, and `scaffold/`. Every current input must be classified as `canonical`, `derived`, `Ansible-only`, `OpenTofu-only`, `deprecated`, or `unsupported`. Unmapped legacy values are retained in a review report and never silently discarded.

### 6.3 Top-level ownership contract

The canonical `site.yaml` has four top-level domains:

```yaml
schema_version: 1
site: {}
platform: {}
resources: {}
services: {}
```

Ownership is divided as follows:

- `site` owns identity, class, lifecycle, apply/destroy policy, and schema version.
- `platform` owns site-wide Proxmox, network, storage, and image/template defaults.
- `resources` owns deployable infrastructure such as LXC guests, VMs, shared application hosts, storage attachments, VMIDs, guest networking, and guest resources.
- `services` owns logical workloads, enablement, dependencies, public names, release pins, service configuration, and placement through a `resource` reference.
- `secrets.sops.yaml` owns secret material referenced by logical services or deployable resources.

A logical service must reference a resource rather than repeat resource identity fields:

```yaml
resources:
  guests:
    forgejo:
      type: lxc
      vmid: 107
      hostname: forgejo
      network:
        address: dhcp
        expected_address: 192.0.2.62

services:
  forgejo:
    enabled: true
    resource: forgejo
    public_name: git.example.internal
```

This structure is required to represent services sharing a resource, such as `searxng_onramp` and `infisical_onramp` on `onramp_host`. A service must not repeat VMID, hostname, address, runtime, CPU, memory, disk, or guest-storage facts owned by its referenced resource.

Consumer projections derive their inputs from this ownership model:

- OpenTofu receives platform and resource projections;
- Ansible inventory receives resource identity plus service configuration projections;
- DNS receives derived service names and resource addresses;
- runtime dotenv receives only process-environment values and secrets;
- platform-specific names remain renderer concerns rather than canonical field names.

### 6.3 Resource taxonomy

Resources use explicit categories:

```yaml
resources:
  guests:
    technitium:
      type: lxc
      vmid: 106
      hostname: technitium-dns
      # network, resources, storage, runtime

  shared_hosts:
    onramp_host:
      type: vm
      vmid: 112
      hostname: onramp-host
      # network, resources, image, cloud-init, deploy settings
```

`resources.guests` represents dedicated LXC or VM guests normally associated with one primary service. `resources.shared_hosts` represents guests or hosts that intentionally run multiple logical services, such as the onramp host. Both categories share validated identity, network, resource, lifecycle, and storage structures, while category-specific fields are typed and validated separately.

A service reference must resolve to exactly one resource in either category. Shared-host services must not acquire independent VMIDs, guest network interfaces, or duplicate guest storage declarations.

### 6.4 Common resource shape

Resource fields are grouped by concern:

```yaml
resources:
  guests:
    forgejo:
      type: lxc
      identity:
        vmid: 107
        hostname: forgejo
        description: Forgejo Git service
      network:
        address: dhcp
        expected_address: 192.0.2.62
        gateway: null
        bridge: vmbr0
        vlan_id: null
        dns_servers:
          - 192.0.2.1
        search_domain: example.internal
      compute:
        cores: 2
        memory_mb: 2048
        swap_mb: 512
      storage:
        root:
          type: proxmox_volume
          storage_id: local-lvm
          size_gb: 8
          target: /
          backup: true
      runtime:
        started: true
        start_on_boot: true
```

The common groups are `type`, `identity`, `network`, `compute`, `storage`, and `runtime`. LXC and VM resources share these groups where semantics are equivalent; runtime-specific fields such as cloud-init, guest users, or container features are typed under the relevant group and rejected for incompatible resource types. Resource defaults come from `platform` only when the resource does not provide an explicit value.

### 6.5 Common resource contract

The common resource contract is:

```yaml
resources:
  guests:
    forgejo:
      type: lxc
      identity:
        vmid: 107
        hostname: forgejo
        description: Forgejo Git service
      network:
        address: dhcp
        expected_address: 192.0.2.62
        gateway: null
        bridge: vmbr0
        vlan_id: null
        dns_servers:
          - 192.0.2.1
        search_domain: example.internal
      compute:
        cores: 2
        memory_mb: 2048
        swap_mb: 512
      storage:
        root:
          type: proxmox_volume
          storage_id: local-lvm
          size_gb: 8
          target: /
          backup: true
      runtime:
        started: true
        start_on_boot: true
```

Resource IDs are stable DNS-safe identifiers and must be unique across `guests` and `shared_hosts`. `identity.vmid` and `identity.hostname` are required and unique within the site. VMID changes are identity changes and normally replacements; hostname changes are potentially disruptive.

`network.address` is either `dhcp` or a static CIDR. DHCP resources may declare `expected_address`; static resources normally must not. Duplicate or overlapping addresses are rejected. `gateway`, `bridge`, and `dns_servers` inherit from platform defaults when omitted. A DHCP resource cannot require a static gateway unless its runtime explicitly supports it.

`compute` contains positive `cores` and `memory_mb` values plus zero-or-positive `swap_mb`. `storage` is a named volume map; `root` is required for deployable guests, volume names are unique, sizes cannot shrink through normal apply, and storage changes require plan review. `runtime` contains common lifecycle fields and typed runtime-specific fields.

A service cannot define VMID, hostname, address, compute, storage, or runtime facts; it references a resource instead. Resource changes are included in plan-equivalence comparisons.

### 6.6 Runtime-specific resource fields

LXC resources may define:

```yaml
runtime:
  started: true
  start_on_boot: true
  unprivileged: true
  nesting: false
  features:
    keyctl: false
    fuse: false
  template:
    image_ref: debian_lxc
  users:
    deploy:
      name: anvil
      sudo: true
```

VM resources may define:

```yaml
runtime:
  started: true
  start_on_boot: true
  firmware: uefi
  machine: q35
  guest_agent: true
  template:
    image_ref: debian_vm
  cloud_init:
    enabled: true
    deploy_user: anvil
    deploy_dir: /srv/onramp
```

LXC-only fields such as `unprivileged`, `nesting`, and container features are rejected on VMs. VM-only fields such as `firmware`, `machine`, `guest_agent`, and `cloud_init` are rejected on LXC resources. Template references point to entries under `platform.images`; resources do not repeat URLs or checksums. Usernames and deployment directories are non-secret; passwords, tokens, and private keys remain in `secrets.sops.yaml`. A resource cannot define both a template reference and an ad hoc image URL.

### 6.7 Image and template contract

Platform images are named entries separated by runtime category:

```yaml
platform:
  images:
    lxc:
      debian_lxc:
        type: lxc_template
        url: https://download.example.internal/debian-13-standard.tar.zst
        file_name: debian-13-standard.tar.zst
        checksum:
          algorithm: sha512
          value: "..."
    vm:
      debian_vm:
        type: vm_image
        url: https://cloud.example.internal/debian-13-genericcloud-amd64.qcow2
        file_name: debian-13-genericcloud-amd64.qcow2
        checksum:
          algorithm: sha512
          value: "..."
```

Resources select approved entries using `runtime.template.image_ref`. LXC resources may reference only `platform.images.lxc`; VM resources may reference only `platform.images.vm`. Image IDs are unique within their category. Remote images require a checksum using `sha256` or `sha512`. URLs, filenames, and checksums are platform/image metadata rather than service or resource-local values. Image-reference, URL, filename, or checksum changes are reviewed resource changes. Downloaded artifacts must be checksum-verified before OpenTofu uses them. Per-resource image URLs are prohibited.

### 6.8 Service catalog contract

`infra/services.json` is the capability-and-schema registry for logical services. Site-specific values remain in `site.yaml` and `secrets.sops.yaml`.

A catalog entry has this shape:

```json
{
  "forgejo": {
    "display_name": "Forgejo",
    "supported_runtimes": ["lxc"],
    "default_runtime": "lxc",
    "requires_resource": true,
    "state_capable": true,
    "dependencies": [],
    "required": {
      "service_fields": [
        "resource",
        "endpoints.public_name",
        "release.version"
      ],
      "secret_paths": [
        "services.forgejo.admin_password",
        "services.forgejo.secret_key"
      ]
    },
    "configuration_schema": "forgejo"
  }
}
```

The catalog owns service identifiers, display names, supported runtime/resource types, default runtime, resource requirements, state capability, dependency declarations, required canonical fields, required logical secret paths, configuration-schema identifiers, and renderer capability metadata where necessary.

The catalog does not own site-specific VMIDs, addresses, domains, credentials, versions, resource sizes, or generated Terraform/Ansible names. Every enabled service must resolve to a catalog entry. The loader validates catalog dependencies, supported resource/runtime combinations, required fields, and required secret paths before rendering.

### 6.9 Service lifecycle and state contract

A state-capable service declares operational state policy:

```yaml
services:
  forgejo:
    enabled: true
    resource: forgejo
    state:
      capable: true
      backup:
        enabled: true
        order: 2
        retention_class: standard
      disable_policy: retain
```

`state.capable` indicates persistent state that must be considered in backup, restore, migration, and disable operations. `state.backup.enabled` controls participation in site backup; `order` controls relative backup/restore ordering; `retention_class` references a backup policy such as `standard`, `critical`, or `disposable`. `disable_policy` is one of `retain`, `archive`, or `destroy`.

`retain` stops or removes deployment while retaining state. `archive` stops the service and creates a verified archive. `destroy` removes service deployment and state only with explicit destructive acknowledgement. Stateful services default to `retain`; stateless services may use `destroy`. `state.capable: true` requires a disable policy, and a service cannot declare itself stateless when its catalog entry marks it stateful. Resource storage backup and service state policy must agree; neither may silently disable the other.

### 6.10 Endpoint and DNS intent

Service endpoint intent is declared under the logical service:

```yaml
services:
  forgejo:
    endpoints:
      public_names:
        - git.example.internal
      public_url: https://git.example.internal/
      protocols:
        - https
        - ssh
      ports:
        https: 443
        ssh: 22
      visibility: public
      dns:
        enabled: true
        record_type: A
        ttl: 300
```

`public_names` is always a list, even for one name. `public_url` is optional and must match one declared name. `protocols` and `ports` describe service intent, not firewall rules. `visibility` is `internal`, `public`, or `none`. `dns.enabled: true` requires at least one name and a supported record type.

DNS records are derived from service endpoint intent and the referenced resource address. A DHCP resource requires a verified current address or approved expected-address policy before DNS publication. DNS provider credentials remain in `secrets.sops.yaml`. DNS ownership is canonical, while DNS application remains a separate reviewed projection/action.

### 6.11 Service release and artifact pins

Service releases are declared under a typed `release` group:

```yaml
services:
  forgejo:
    release:
      version: 12.0.4
      image: null
      digest: null
      source: package
```

Containerized services use:

```yaml
release:
  version: null
  image: docker.io/searxng/searxng
  digest: sha256:...
  source: container
```

`source` is one of `package`, `container`, `binary`, or `image`. Packages require `version` and prohibit `digest`. Containers require `image` and an immutable `digest`; mutable tags alone are prohibited. Binaries require `version` and a checksum. `image` source refers to a platform image and belongs on the resource rather than the service. Version, image, digest, and checksum changes are reviewed service changes. Release identity is public metadata and does not belong in `secrets.sops.yaml`. Service catalog entries declare supported release forms.

### 6.12 Service configuration and typed overrides

Services declare provider-neutral behavior under `configuration`:

```yaml
services:
  forgejo:
    configuration:
      database:
        type: sqlite
      actions:
        enabled: true
      ssh:
        enabled: true
        port: 22
    overrides:
      ansible:
        write_initial_config: false
```

Each service has a catalog-referenced configuration schema. Unknown configuration fields are rejected. `overrides` is optional and namespaced by consumer; allowed keys are declared in the service catalog. Unrestricted `extra_vars`, `terraform`, or `ansible` maps are prohibited. Overrides may affect rendering but cannot redefine resource identity, service placement, secrets, or canonical endpoints. Every override is included in plan metadata and the generated projection digest.

### 6.13 Platform defaults and resource overrides

Precedence is one-way:

```text
platform defaults
    -> resource values
        -> service logical configuration only
```

`platform` contains site-wide substrate defaults and capabilities. Resources may override individual fields with explicit merge semantics. A resource does not need to restate an entire network or storage block when changing one field:

```yaml
platform:
  network:
    default_bridge: vmbr0
    default_gateway: 192.0.2.1
    default_dns_servers:
      - 192.0.2.1

resources:
  guests:
    forgejo:
      network:
        bridge: vmbr1
        gateway: 192.0.2.20
```

The effective resource retains the platform DNS default while using its explicit bridge and gateway. Map fields merge recursively by declared schema rules; lists and scalar values replace rather than concatenate unless a field explicitly defines another behavior. Services may not override resource or platform infrastructure fields.

### 6.6 Platform section

The `platform` section contains only site-wide substrate settings and defaults. Version one defines four groups:

```yaml
platform:
  proxmox:
    endpoint: https://proxmox.example.internal:8006/
    node: pve
    insecure: true

  network:
    default_bridge: vmbr0
    default_gateway: 192.0.2.1
    default_dns_servers:
      - 1.1.1.1
      - 9.9.9.9
    default_search_domain: example.internal
    default_vlan_id: null

  storage:
    rootfs_datastore: local-lvm
    template_datastore: local
    backup_datastore: backup

  images:
    lxc:
      url: https://download.example.internal/debian.tar.zst
      file_name: debian.tar.zst
      checksum_algorithm: sha512
      checksum: "..."
    vm:
      url: https://cloud.example.internal/debian.qcow2
      file_name: debian.qcow2
      checksum_algorithm: sha512
      checksum: "..."
```

`platform` must not contain service-specific configuration or individual guest identity. Resource fields may override individual platform defaults according to Section 6.5.

### 6.7 Logical service shape

Logical services use grouped fields:

```yaml
services:
  forgejo:
    enabled: true
    resource: forgejo
    dependencies: []
    state:
      capable: true
      backup_order: 2
    endpoints:
      public_name: git.example.internal
      public_url: https://git.example.internal/
      ssh_port: 22
    release:
      version: 12.0.4
      image: null
      digest: null
    configuration:
      database:
        type: sqlite
      actions:
        enabled: true
    overrides:
      ansible:
        write_initial_config: false
```

The groups are:

- `enabled` for service selection;
- `resource` for placement;
- `dependencies` for service ordering and registry validation;
- `state` for backup/restore capability and ordering;
- `endpoints` for public names, URLs, ports, and service-facing identity;
- `release` for version, image, and digest pins;
- `configuration` for service behavior;
- `overrides` for narrowly typed platform-specific fields.

A service must not put VMID, guest hostname, guest address, CPU, memory, disk, or resource storage under its own configuration. Those belong to the referenced resource.

## 7. Secret model

Illustrative decrypted structure:

```yaml
proxmox:
  api_token: ...

lxc:
  root_password: ...
  ssh_public_keys:
    - ssh-ed25519 ...

cloudflare:
  dns_api_token: ...

forgejo:
  secret_key: ...
  internal_token: ...
  admin_password: ...
  postgres_password: ...

hermes:
  dashboard_auth_hash: ...
  control_api_token: ...
```

Version one uses direct logical namespaces. The secret file does not mirror environment-variable names and does not contain provider-reference objects:

```yaml
platform:
  proxmox:
    api_token: ...

resources:
  lxc:
    root_password: ...
    ssh_public_keys: [...]

services:
  forgejo:
    secret_key: ...
    admin_password: ...
  hermes:
    dashboard_auth_hash: ...
```

The initial provider is SOPS using age recipients. 1Password and Infisical integrations are deferred.

### 7.1 Provider-neutral secret interface

The loader exposes a provider-neutral boundary:

```text
SecretProvider.resolve(logical_path, context) -> secret value
SecretProvider.describe(logical_path, context) -> metadata only
SecretProvider.list_versions(logical_path, context) -> version metadata
```

Version one implements `SopsAgeProvider`, which decrypts the selected site's `secrets.sops.yaml` and resolves logical paths in memory. Future adapters may include OnePassword, Infisical, or Vault. Canonical paths remain stable across providers; provider configuration is outside `site.yaml`; provider selection is an execution concern; adapters cannot alter service or resource schemas. Version one works without an external secret service. Provider metadata never exposes values, and errors identify site and logical path without printing the secret.

### 7.2 Secret taxonomy and required-secret contract

Service catalog entries declare required logical secrets:

```yaml
services:
  forgejo:
    secrets:
      - path: services.forgejo.admin_password
        class: bootstrap
        required_when: enabled
      - path: services.forgejo.secret_key
        class: runtime
        required_when: enabled
      - path: services.forgejo.smtp_password
        class: runtime
        required_when: smtp.enabled
```

Secret classes are `bootstrap`, `runtime`, `provider`, `recovery`, and `generated`. Bootstrap secrets create or initially configure a resource/service. Runtime secrets are needed by the running service. Provider secrets are needed by OpenTofu, DNS, or another external provider. Recovery secrets restore or regain access. Generated secrets are created idempotently by the loader and stored only through the encrypted bundle.

`required_when` is evaluated after service configuration and enablement. Missing required secrets fail validation before planning. Generated secrets require an explicit generation policy and are never logged. Bootstrap and runtime secrets may share one SOPS file but retain distinct classifications. A secret class determines which renderer may receive the value. Provider secrets must not be rendered into service dotenv files, and runtime secrets must not enter OpenTofu inputs unless genuinely required by the provider.

The committed file remains encrypted. Public age recipients may be committed in `.sops.yaml`; private age keys must remain outside the repository.

### 7.2 SOPS/age recipient policy

SOPS creation rules target each site secret bundle:

```yaml
creation_rules:
  - path_regex: values/sites/[^/]+/secrets\\.sops\\.yaml
    age:
      - age1operator...
      - age1ci...
      - age1recovery...
```

Key roles are:

- `operator`: authorized local editing and execution;
- `ci/deployment`: site-scoped non-interactive plan/apply;
- `recovery`: offline break-glass recovery stored separately from normal credentials.

Public recipients may be committed; private keys are always external. Development and production recipients are separate. CI keys are site-scoped and least-privilege; one key must not decrypt every site without explicit justification. Recipient rotation decrypts and re-encrypts the bundle and updates the recipient manifest; it does not itself rotate secret values. Secret rotation is a separate operation. Recovery must be tested by restoring a disposable copy.

The PRD implementation must document key creation, recipient rotation, revocation, backup, and recovery. Loss of all private age keys is an unrecoverable secret-loss event and must be treated accordingly.

SOPS decryption must occur only during the controlled values-loading phase. Secret material must not be printed, passed in ordinary command-line arguments, committed, or left in generated artifacts after execution.

SOPS protects source secrets but does not protect Terraform state, plans, rendered guest files, or service databases. Those outputs require separate protection and cleanup rules.

### 7.1 Secret transport and threat model

Before implementation, classify every secret as one of:

- provider/bootstrap secret;
- OpenTofu-required secret;
- Ansible-only secret;
- guest-persistent service secret;
- generated/recoverable secret.

Provider credentials should be supplied through process environment or a protected provider mechanism wherever supported. Secrets required only by Ansible must not be rendered into Terraform inputs. If a secret must enter Terraform state, the PRD implementation must document the state backend, encryption, access control, backup, restore, and rotation implications before enabling that path.

The values runner must define a single controlled decryption boundary. It must use mode `0700` temporary directories, mode `0600` secret files, restrictive process environment handling, and cleanup handlers for success, validation failure, renderer failure, OpenTofu failure, Ansible failure, interruption, and normal termination. Cleanup tests must verify that temporary files and generated logs do not contain secret values. Existing `.tmp` service logs and `scripts/run-infra.sh` environment staging are part of this threat model.

Private CI may decrypt only with a site-scoped least-privilege age key. Public CI must validate schema and public fixtures without decrypting private values. Key discovery, rotation, revocation, offline recovery, and backup must be documented and tested.

### 7.3 Secret transport and state exposure

Secret transport is classified by consumer:

```text
provider secrets
  -> process environment or provider-specific protected mechanism
  -> OpenTofu/provider only

bootstrap secrets
  -> protected temporary Ansible variables or process environment
  -> bootstrap task only

runtime secrets
  -> protected temporary runtime.env or Ansible variables
  -> target service only

recovery secrets
  -> explicit recovery workflow only

generated secrets
  -> in-memory generation
  -> encrypted SOPS bundle
```

Secrets are decrypted only inside one controlled loader boundary. Temporary directories use mode `0700`; temporary secret files use mode `0600`; secrets are never ordinary command-line arguments. Provider secrets are not placed in service dotenv files. Runtime secrets are not passed to OpenTofu unless unavoidable. If a secret enters OpenTofu state, the state backend must be encrypted, access-controlled, backed up, and documented before that path is enabled. Generated artifacts are deleted after execution. Cleanup is tested after success, validation failure, renderer failure, OpenTofu failure, Ansible failure, interruption, and termination. Logs and error reports redact values and secret-bearing paths.

### 7.4 YAML and SOPS parsing rules

The canonical loader must use safe YAML loading and reject duplicate keys. Anchors and aliases are prohibited unless explicitly required and tested. Unknown fields are errors in canonical input; compatibility fields are accepted only in the importer. Types are not coerced silently, `null` has schema-defined meaning, and schema versions must be explicit. Comments and formatting must not affect canonical identity.

## 8. Values processing architecture

Add a Python values layer with these responsibilities:

1. Resolve `VALUES_DIR` and `VALUES_SITE` through the existing values context.
2. Load and validate `site.yaml`.
3. Load and decrypt `secrets.sops.yaml`.
4. Apply schema-defined defaults.
5. Validate service registry membership and dependencies.
6. Validate VMID and address uniqueness.
7. Validate cross-field invariants such as DHCP versus gateway usage.
8. Resolve logical secret references.
9. Produce a redacted model summary.
10. Calculate a stable non-secret model digest and generated-input digest.
11. Render consumer-specific inputs.

The loader must be the common entry point for validation, planning, application, migration, and generated-output comparison. Individual consumers must not independently reinterpret the canonical files.

### 8.1 Schema validation and versioning

Version one uses strict Pydantic models as the primary schema contract. The models reject unknown fields, duplicate YAML keys are rejected before model construction, and secret models use the same structural rules after decryption. `schema_version` is required and is `1` for version one. Schema migrations are explicit transformations rather than implicit type coercion; a loader supports the current version plus only explicitly supported previous versions. An optional JSON Schema export may support editor and fixture validation, but generated Python models remain authoritative. Defaults are applied before digesting. Errors identify logical paths and expected/actual types without exposing secret values.

### 8.2 Identity and digest semantics

The loader must normalize the parsed model before hashing. Canonical identity is independent of YAML comments, whitespace, key order, line endings, and equivalent formatting. The normalized form includes schema defaults and explicit `null` semantics, and uses stable representations for numbers, booleans, lists, maps, CIDRs, and hostnames.

The plan metadata must record:

- `schema_version`;
- loader/renderer version;
- source repository commit;
- selected site;
- normalized non-secret model digest;
- SOPS ciphertext hash and a separately protected secret-bundle identity when decrypted values affect execution;
- exact generated projection names and digest;
- enabled logical services and resource/host ownership;
- OpenTofu and Ansible tool versions.

### 8.2 Digest contract

The implementation uses four identities:

- `model_digest`: SHA-256 of canonical JSON generated from the fully parsed, schema-defaulted, non-secret model;
- `secret_digest`: SHA-256 of canonical JSON generated from decrypted logical secret values used for execution;
- `ciphertext_hash`: SHA-256 of committed `secrets.sops.yaml` bytes;
- `projection_digest`: SHA-256 of a canonical manifest containing projection names, projection contents, schema version, `model_digest`, and secret-bearing projection classifications.

Comments, whitespace, key order, and line endings do not affect identity. Defaults are applied before hashing; explicit `null` semantics are schema-defined; numbers, booleans, lists, maps, CIDRs, and hostnames use stable representations. Secret digests never contain plaintext. SOPS re-encryption changes `ciphertext_hash` but not `secret_digest`; actual secret rotation changes `secret_digest`. Plan and apply must match `model_digest`, `secret_digest`, and `projection_digest`. Generated manifests reject stale or manually altered projections.

Before OpenTofu and again before Ansible, the workflow must verify the selected site, model identity, secret identity, generated-input digest, and projection set. Ansible must use the same normalized snapshot or a re-rendered snapshot whose identity is revalidated; it must not silently reread changed source files after OpenTofu completes.

## 9. Consumer projections

### 9.0 Projection set and lifecycle

Each site may produce this projection set:

```text
values/sites/<site>/generated/
  terraform.auto.tfvars.json
  ansible-inventory.json
  ansible-vars.json
  dns-records.json
  runtime.env
  plan-metadata.json
  manifest.json
```

`terraform.auto.tfvars.json` contains existing OpenTofu variable names and is temporary or ignored. `ansible-inventory.json` contains resource identity, connection data, service placement, and non-secret host variables. `ansible-vars.json` contains non-secret service variables; secrets are injected through protected execution inputs. `dns-records.json` contains names, record type, address target, TTL, and ownership metadata. `runtime.env` is a mode-`0600` temporary dotenv projection. `plan-metadata.json` records site/model/secret/generated digests, renderer versions, enabled services, ownership, and tool versions. `manifest.json` records projection names, hashes, creation time, schema version, and source identity.

Every projection carries site identity and model digest. Secret-bearing projections are temporary and mode `0600`; non-secret generated projections are ignored, with the directory mode `0700`. Stale or manually altered projections are rejected. Compatibility wrappers may consume projections during migration, but generated files are never canonical inputs.

### 9.1 OpenTofu

Generate a temporary or ignored JSON variable file, such as:

```text
generated/terraform.auto.tfvars.json
```

The first implementation should preserve existing Terraform variable names at the renderer boundary. OpenTofu modules can therefore remain mostly unchanged while configuration ownership moves to the canonical model.

The generated file must not become an operator-edited source of truth.

The cutover must update `scripts/plan-infra.sh`, `scripts/apply-infra.sh`, and all OpenTofu invocation paths to consume exactly this projection. The PRD implementation must choose one default: a mode-0700 temporary directory is preferred for secret-bearing inputs; an ignored site-local `generated/` directory is allowed only for non-secret projections and must be cleaned before completion.

Secrets should be passed to OpenTofu only when OpenTofu actually requires them. Provider credentials should prefer environment delivery where supported. The implementation must identify which secrets enter state and document the resulting state-protection requirement.

### 9.1.1 OpenTofu renderer contract

The canonical loader renders `generated/terraform.auto.tfvars.json` for the existing OpenTofu modules. The projection preserves current OpenTofu variable names at the renderer boundary; canonical names remain authoritative only in the model. It contains only OpenTofu-required fields. Ansible-only values and runtime-only secrets are excluded. Provider credentials use environment delivery where supported.

The projection is generated from the normalized model and bound through `plan-metadata.json` to `site.name`, `model_digest`, `secret_digest`, and `projection_digest`; these identities are metadata rather than arbitrary Terraform variables. `scripts/plan-infra.sh`, `scripts/apply-infra.sh`, and every OpenTofu invocation consume exactly this projection. Secret-bearing inputs are temporary; non-secret projections may be ignored site-local artifacts. OpenTofu modules are not rewritten to canonical names in version one.

### 9.2 Ansible

Generalize or replace `infra/ansible/inventory/tfvars.py` so it reads the canonical normalized model rather than parsing `terraform.tfvars` as the primary source.

It should continue to emit the inventory contract expected by existing playbooks and roles:

- groups and hosts;
- direct service addresses;
- VMIDs where required for lifecycle operations;
- runtime-specific users and become behavior;
- service domains;
- service storage and runtime values;
- typed service-specific variables.

The projection contract must identify whether inventory is emitted as a temporary JSON file, an executable dynamic inventory, or an in-memory library interface. `scripts/validate-values.sh`, `scripts/plan-infra.sh`, `scripts/apply-infra.sh`, and `scripts/apply-ansible-services.py` must all consume the same selected projection and snapshot.

Static `ansible/inventory/local.yml` should be reduced to genuine Ansible-only overrides and eventually removed as an authoritative configuration file.

### 9.2.1 Ansible renderer contract

Ansible receives separate projections:

```text
ansible-inventory.json
  Resource identity and connection inventory.

ansible-vars.json
  Non-secret service and host variables.

protected secret input
  Bootstrap/runtime secrets only for tasks that require them.
```

`ansible-inventory.json` is derived from `resources` and preserves the groups and variable names expected by existing playbooks during migration. `ansible-vars.json` is derived from `services` and contains service placement, endpoints, and non-secret configuration. Secret-bearing variables are injected separately and are not written into long-lived inventory files.

`infra/ansible/inventory/tfvars.py` becomes a compatibility adapter or is replaced. Static `ansible/inventory/local.yml` is no longer authoritative. Site, model, secret, and projection identities are checked before Ansible runs. `scripts/apply-ansible-services.py` consumes the same normalized snapshot used for OpenTofu.

### 9.3 Environment delivery

Generate a temporary restricted dotenv file only for process-environment inputs and secrets consumed through existing Ansible templates or tooling. The current `scripts/run-infra.sh` staging file and `scripts/apply-ansible-services.py` direct `.env` loading must be replaced or routed through the canonical runner.

The projection contract must specify its path, mode, ownership, lifetime, cleanup behavior, and allowed key set. It must be created only inside the controlled execution boundary and removed on all exit paths.

Public configuration such as VMIDs, hostnames, public URLs, resources, and storage must not remain in `.env` merely because a legacy consumer once used environment variables.

Existing restricted parsing from `scripts/envfile.py` and `scripts/parse-env.py` should be retained and extended only as needed.

### 9.3.1 Runtime dotenv contract

`generated/runtime.env` is a compatibility projection, not a source of truth. It is created only inside the controlled execution boundary with mode `0600` and deleted on every exit path. It contains only keys declared by the service/runtime schema and required process-environment values or secrets. VMIDs, hostnames, public URLs, resource sizes, and DNS intent do not belong in it.

The projection uses the existing restricted dotenv parser and escaping rules. Duplicate keys, unknown keys, invalid quoting, and newline violations fail validation. Values are never printed in logs or errors. Model and secret identities are recorded in `manifest.json`, not as environment keys.

### 9.4 DNS

Initially render `dns-records.local.json` from canonical service public names and addresses so the existing Technitium Ansible workflow can remain in place. The generated projection must be consumed by the existing `DNS_RECORDS_FILE` path expected by `technitium-dns.yml`, while `scripts/validate-values.sh` and DNS checks are updated to validate the generated projection.

A later step may make DNS synchronization consume the normalized model directly. The generated DNS file must not be independently edited.

### 9.5 Service configuration

Ansible roles remain responsible for rendering service-local configuration and managing permissions. The canonical layer supplies typed inputs and secret values; roles continue to own implementation details and idempotence.

All secret-bearing templates must use appropriate redaction and `no_log` behavior. Template escaping must be tested for dotenv, YAML, INI, JSON, Caddy, and service-specific formats.

Every projection must have one declared lifecycle: temporary execution input, ignored derived artifact, or compatibility-only output. No generated file may become an untracked second source of truth.

## 10. Migration strategy

Migration must be additive and reversible.

### 10.1 Migration precedence and compatibility window

Migration proceeds in five stages:

1. Canonical files are added while legacy files remain authoritative.
2. The importer reads legacy files and produces a candidate canonical model; conflicts fail closed and legacy files are not deleted.
3. Canonical projections are compared with legacy consumer files and OpenTofu plans.
4. After explicit cutover, the canonical model becomes authoritative and legacy files are read only through compatibility wrappers; direct edits produce warnings or failures.
5. Legacy files are removed after the documented removal criteria pass.

After cutover, precedence is:

```text
canonical site.yaml/secrets.sops.yaml
  -> authoritative

legacy root/site-aware files
  -> importer and compatibility input only

settings.local.json
  -> repository/operator metadata only
```

Conflicting values fail closed. Semantically equivalent values are normalized and accepted. Unknown legacy values are preserved in a migration report. Migration is dry-run by default; file movement or deletion requires explicit apply and a verified backup. Root and site-aware sources cannot silently override one another. Production migration requires explicit approval.

The compatibility window lasts one release cycle after canonical cutover. Direct legacy-file use emits warnings during that cycle, and the removal release and criteria are documented before cutover.

### 10.2 State, plan, and backup policy

Each site has isolated state and operational artifacts:

```text
values/sites/<site>/
  state/
    terraform.tfstate
    terraform.tfstate.backup
  generated/
    plan-metadata.json
  backups/
    <timestamp>-<operation>.manifest.json
    <timestamp>-<operation>.tar.age
```

Each site uses an isolated state namespace/backend. State is never shared between sites, is encrypted at rest and access-controlled, and is never committed to the public repository. Plan files are site-local, short-lived, and bound to model, secret, projection, renderer, and tool identities. A plan is invalid after any relevant source, secret, renderer, or tool change.

Version one uses local site-scoped state at `values/sites/<site>/state/terraform.tfstate` with restrictive filesystem permissions and encrypted site backup copies. State is resolved through `VALUES_SITE`, never committed to the public repository, and never shared across sites. A future remote encrypted backend may be introduced through a backend adapter without changing the canonical model. Version one does not require remote-backend availability for foundational recovery.

Backups include encrypted secret bundles, state, migration inputs, manifests, and required trust or artifact references. Restore is tested into a disposable directory before production readiness is claimed. State restoration requires matching site identity and an explicit state-recovery procedure. Restoring state does not imply that already-applied infrastructure changes are automatically reversible.

### 10.3 Phase 1: schema and loader

- Add the canonical schema and Python model.
- Add SOPS/age policy and safe local tooling.
- Add validation and redacted summary commands.
- Add unit tests for schema and secret separation.
- Do not change OpenTofu or Ansible consumers yet.

### Phase 2: legacy importer

The importer must support both existing private-values layouts:

Legacy root layout:

```text
values/.env
values/terraform.tfvars
values/ansible/inventory/local.yml
values/dns-records.local.json
values/terraform.tfstate*
settings.local.json
```

Current site-aware layout:

```text
values/sites/<site>/site.json
values/sites/<site>/.env
values/sites/<site>/terraform.tfvars
values/sites/<site>/ansible/inventory/local.yml
values/sites/<site>/ansible/known_hosts
values/sites/<site>/dns-records.local.json
values/sites/<site>/terraform.tfstate*
values/sites/<site>/tfplan*
values/sites/<site>/backups/
values/sites/<site>/artifacts/
```

`settings.local.json` is repository/operator metadata and must not be conflated with site metadata. The importer must use the existing `values_context.py`, `site-context.sh`, `migrate-values.py`, and `migrate-site-values.py` contracts rather than creating a competing path-resolution mechanism.

The migration manifest must record source paths and hashes, destination paths, schema/renderer version, selected site, conflict decisions, generated-secret actions, and verified backup identifier. Migration is idempotent: rerunning against an already canonical site produces no changes, while a changed legacy source requires explicit review.

Produce a candidate `site.yaml` and `secrets.sops.yaml`.

The importer must:

- detect conflicting declarations;
- never silently select between conflicting values;
- compare semantically equivalent values after normalization;
- preserve unknown values for explicit review;
- generate missing persistent secrets idempotently;
- avoid printing secrets;
- support dry-run by default;
- require explicit apply for file movement or rewriting;
- create a verified backup before mutation;
- roll back completed moves if a later operation fails;
- preserve or deliberately migrate `ansible/known_hosts`, state, plan metadata, backups, and private artifact references;
- refuse to overwrite an existing canonical site without an explicit migration mode;
- ensure production credentials, state, and backups are never copied into a development site.

Migration must define separate precedence rules for root layout, site-aware layout, `site.json`, and root `settings.local.json`. It must fail closed when those sources disagree after normalization.

### Phase 3: render and compare

Render the current consumer formats from the canonical model:

```text
generated/terraform.auto.tfvars.json
generated/ansible-inventory.json
generated/runtime.env
generated/dns-records.json
```

Compare them with the legacy files and report intentional, derived, ignored, and conflicting differences. Comparison must distinguish semantic equivalence from textual difference and must identify defaults, computed values, provider refresh differences, replacements, and intentional schema changes.

The pre-migration and post-migration OpenTofu plans must be compared through a documented equivalence oracle. Path-only changes must not create resource changes. Any create, destroy, replacement, changed address, changed runtime, changed storage, changed secret-dependent field, or changed shared-resource ownership requires explicit review and is not treated as equivalent.

### Phase 4: Ansible cutover

- Make dynamic inventory read the normalized canonical model.
- Remove infrastructure-derived duplicates from static inventory.
- Preserve only typed Ansible-specific overrides.
- Run syntax, inventory, role contract, and service configuration tests.

### Phase 5: OpenTofu cutover

- Run OpenTofu with generated JSON variables.
- Bind generated inputs to site and model digests.
- Compare pre- and post-migration plans.
- Confirm that path/schema migration alone causes no resource changes.

### Phase 6: operational cutover

- Update setup, validate, plan, apply, backup, restore, update, and operator tooling.
- Update README, AGENTS, scaffold documentation, and the site-aware migration plan.
- Make canonical files the only documented operator-editable inputs.

### Phase 7: compatibility removal

After successful migration and validation cycles:

- stop treating root-level `.env`, `terraform.tfvars`, inventory, and DNS JSON as authoritative;
- remove permanent duplicate knobs;
- retain a time-bounded legacy migration command;
- retain rollback documentation and tests.

## 11. Safety and rollback

The plan/apply workflow must record:

```text
site name
source repository commit
schema version
loader/renderer version
canonical model digest
secret bundle identity or digest without secret values
exact generated projection set and digest
enabled logical services
resource/host ownership
OpenTofu and Ansible tool versions
```

Apply must refuse to continue if any identity changes between plan and apply. It must verify the inputs before OpenTofu and again before Ansible. A failure in the Ansible phase must not cause the workflow to claim that the overall apply succeeded.

Rollback is defined at four separate levels:

1. **File-layout rollback:** restore the private values repository from the verified migration backup and migration manifest.
2. **Generated-artifact rollback:** remove only generated projections and temporary files; never restore generated files as authoritative configuration.
3. **State rollback:** restore Terraform/OpenTofu state only through an explicit, backend-supported state recovery procedure with matching site and model identity.
4. **Infrastructure recovery:** already-applied infrastructure changes are not automatically reversible. Recovery requires a new reviewed plan, service-specific rollback procedure, and explicit operator approval.

A verified backup must include a manifest, source hashes, encrypted secret files, state files, private Git history or remote reference, and any required known-hosts/artifact references. Verification must include readable archive metadata, hash comparison, and a tested restore into a disposable directory.

Migration rollback must restore the original private values layout from a verified backup, remove only generated artifacts, and leave public source unchanged. Terraform state must not be renamed, copied, or reused across sites without an explicit state migration procedure and equivalent-plan evidence.

Production and development must never share:

- state files;
- credentials;
- DNS records;
- generated inputs;
- backup archives;
- mutable generated directories.

## 12. Validation requirements

### Unit and contract tests

- canonical schema validation;
- safe YAML loading and duplicate-key rejection;
- unknown-field, alias/anchor, null, and schema-version behavior;
- site/path traversal protection;
- site metadata validation;
- enabled-service registry and dependency validation;
- logical-service/resource/shared-host ownership validation;
- duplicate VMID detection;
- duplicate and overlapping address detection;
- runtime-specific field validation;
- storage model validation;
- secret reference and secret classification validation;
- SOPS file presence and recipient policy checks;
- legacy importer conflict handling for root and site-aware layouts;
- migration manifest, backup verification, rollback, and idempotence;
- renderer output contracts and mapping-matrix coverage;
- dotenv and format-specific escaping;
- redaction and generated-artifact cleanup tests;
- destructive-change acknowledgement for disabled stateful services.

Failure-path cleanup tests must cover successful runs, validation failures, renderer failures, OpenTofu failures, Ansible failures, interruption, and process termination. They must verify file modes and absence of secret material from temporary directories, generated files, and `.tmp` logs.

### Integration tests

- canonical model to OpenTofu variable projection;
- canonical model to Ansible inventory projection;
- canonical model to DNS projection;
- generated runtime environment delivery;
- plan metadata binding before OpenTofu and before Ansible;
- canonical digest stability across formatting-only changes;
- secret identity behavior across SOPS re-encryption and actual secret rotation;
- plan equivalence before and after migration;
- semantic equivalence handling for provider refresh and computed values;
- separate dev and production model/state selection;
- every supported service in `infra/services.json`;
- LXC and VM variants;
- shared onramp-host services;
- stateful and stateless service enablement;
- migration from both root and site-aware values repositories.

### 12.2 Acceptance and plan-equivalence criteria

A migration is equivalent only when the resource set, resource addresses, VMIDs, runtime types, storage identity and sizes, service enablement, service placement, endpoint/DNS intent, release pins, and secret-dependent infrastructure behavior are unchanged.

The comparison may ignore generated file paths, projection formatting, YAML/HCL/JSON key ordering, comments and whitespace, provider refresh-only differences, and computed values that remain semantically equal. It must flag creates, destroys, replacements, address changes, VMID changes, runtime changes, storage changes, service placement changes, DNS target changes, and secret-dependent field changes.

Version-one acceptance requires:

1. Every enabled catalog service has a schema fixture.
2. Every supported runtime has a fixture.
3. Shared-host services have fixtures.
4. Root-layout and site-aware migration fixtures both pass.
5. Plan equivalence passes for representative existing sites.
6. Conflict, stale-plan, wrong-site, missing-secret, and cleanup failures are tested.
7. Backup restore and migration rollback are rehearsed.
8. A second plan after apply produces no unexpected changes.

### Operational validation

Before production readiness is claimed, validate through the existing evidence-based process:

- `just validate` for the selected site;
- reviewed `just plan`;
- approved apply only where explicitly authorized;
- repeat plan with zero unexpected changes;
- service health and direct-access checks;
- backup and restore coverage;
- migration rollback rehearsal;
- secret rotation behavior;
- generated-artifact cleanup.

## 13. Documentation updates

The implementation must update together:

- `README.md`;
- `AGENTS.md`;
- `scaffold/README.md`;
- `scaffold/sites/dev/`;
- `.hermes/plans/site-aware-values-migration.md`;
- `docs/development-environment.md`;
- values setup and migration help text;
- tests describing the private values contract.

The legacy four-file layout may be documented only in the migration section, not as the normal operating model.

## 14. Implementation-design decisions

The following items remain implementation-design work, not unresolved product direction. They must be documented before the corresponding code phase begins:

- complete per-service configuration schemas and fixtures for every entry in `infra/services.json`;
- complete mapping rows for every current Terraform, Ansible, migration, DNS, and dotenv field;
- exact SOPS/age command integration, external key-file discovery, and executable availability checks;
- exact projection temporary-file paths, cleanup hooks, and compatibility-wrapper invocation details;
- exact allowed override keys for each service and consumer;
- final dynamic-inventory caller cutover across all scripts and playbooks;
- complete inventory of secrets that currently enter OpenTofu state;
- concrete local-state filesystem permissions, encryption-at-rest mechanism, and backup transport;
- final release-pin ownership once all current service and runtime fixtures are mapped;
- compatibility-window warning text, owner, and removal release criteria.

No implementation phase may begin with an item above affecting that phase still undefined. Any newly discovered product-level decision must be added to this PRD before implementation continues.

## 15. Glossary

- **Site:** an isolated environment with its own configuration, credentials, state, DNS, and lifecycle policy.
- **Logical service:** a platform capability such as Forgejo, Hermes, or SearXNG.
- **Deployable resource:** an LXC, VM, shared host, storage attachment, or other infrastructure object used to run one or more logical services.
- **Projection:** a generated consumer-specific representation of the canonical model.
- **Secret bundle:** the encrypted per-site SOPS file and its identity/recipient policy.
- **Generated artifact:** a disposable or ignored file produced from the canonical model; never an authoritative input.
- **Plan equivalence:** a documented semantic comparison showing that a migration or path change did not introduce unintended infrastructure changes.

## 16. Success criteria

The project is successful when:

1. A site’s operator-editable configuration consists of `site.yaml` and `secrets.sops.yaml`.
2. No infrastructure fact is manually declared in both canonical configuration and a consumer file.
3. Ansible inventory is derived from the canonical model.
4. OpenTofu receives generated inputs from the canonical model.
5. DNS records are derived from canonical service identity and address data.
6. Secrets are encrypted at rest and are not exposed in logs or committed generated files.
7. Plan/apply is bound to the exact site and model used to produce the plan.
8. Existing private values repositories have a tested, reversible migration path.
9. Development and production values, state, credentials, and generated artifacts are isolated.
10. The public repository documents one current values architecture and keeps legacy details only in migration guidance.

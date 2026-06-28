# Homelab Infrastructure Runbooks

Reusable OpenTofu and Ansible runbooks for Proxmox LXCs running Technitium DNS, Caddy, and Forgejo.

This public repo is intentionally generic. Real domains, LAN IPs, DNS records, Proxmox endpoints, credentials, and state belong in the ignored private `values/` repo.

## Layout

Tracked public source:

```text
infra/opentofu/    OpenTofu configuration and Technitium DNS API helper
infra/ansible/     Ansible playbooks and roles for in-LXC service config
scaffold/          Public-safe starter files copied into values/
scripts/           Local workflow helpers
tools/             Docker tooling image
```

Ignored site/local state:

```text
values/            Private site values repo
.terraform/        OpenTofu/Terraform working data
tfplan             Local plan artifact
```

Keep non-public material in `values/` or outside this checkout; do not add another sensitive-data directory to this repo.

## Fresh setup

From a fresh checkout, run:

```bash
just setup
```

This builds the local tooling container and creates `values/` from `scaffold/`.

To clone an existing private values repo instead:

```bash
just setup git@git.example.internal:owner/homelab-infra-values.git
```

Then edit the private files:

```text
values/.env
values/terraform.tfvars
values/dns-records.local.json
values/ansible/inventory/local.yml
```

## Daily workflow

Validate tracked public source only:

```bash
just validate-public
```

Validate public source and private values wiring:

```bash
just validate
```

Review infrastructure/DNS changes:

```bash
just plan
```

Apply the reviewed plan and configure services with Ansible:

```bash
just apply
```

`just apply` runs the saved `tfplan`, removes plan artifacts, then runs `infra/ansible/playbooks/site.yml`.

## Private values repo

`values/` is ignored by this public repo and can be its own private Git repo. The scaffold defines this shape:

```text
values/
  .env
  terraform.tfvars
  dns-records.local.json
  ansible/inventory/local.yml
```

Use `just status-values` to inspect the nested private repo.

## Responsibilities

OpenTofu manages:

- Proxmox LXC resources
- Forgejo ZFS bind mount shape
- Technitium DNS records/settings through `infra/opentofu/scripts/apply-technitium-dns.py`

Ansible manages:

- Technitium installation
- Caddy installation/configuration on the Technitium LXC
- Forgejo installation/configuration
- Caddy and OpenSSH integration on the Forgejo LXC

## Safety

Do not apply without reviewing `just plan` output. Do not commit secrets, state, plans, or real site values to the public repo.

`scripts/edgeos-static-host-mapping.sh` mutates a live EdgeRouter config and should only be run after explicit review/approval.

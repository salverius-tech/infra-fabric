# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

This repo manages homelab DNS infrastructure with OpenTofu/Terraform.

Tracked files are intentionally public-safe examples/source. Real Proxmox endpoints, LAN IPs, DNS zones, records, and credentials belong in local gitignored files:

- `.env`
- `terraform.tfvars`
- `dns-records.local.json`

## Safety Rules

- Do not run `tofu apply`, `terraform apply`, `destroy`, import, or state surgery without explicit user approval.
- Do not commit secrets, `.env`, `terraform.tfvars`, `dns-records.local.json`, state files, plans, or generated local credentials.
- Treat DNS as critical infrastructure. Prefer reviewed plans over ad hoc mutation.
- Do not mutate production routers/firewalls unless explicitly requested.
- If changing the DNS server IP or hostname, update local tfvars, local DNS records, README, and any migration notes together.

## Commands

Prefer OpenTofu:

```bash
tofu fmt -check -recursive
tofu validate
tofu plan -out=tfplan
tofu show tfplan
```

Terraform may be used for local validation if OpenTofu is unavailable:

```bash
terraform fmt -check -recursive
terraform validate
```

Shell/Python validation:

```bash
shellcheck scripts/*.sh
python -m py_compile scripts/apply-technitium-dns.py
python -m json.tool dns-records.example.json >/dev/null
```

## Credentials and Local Config

Load `.env` before planning:

```bash
set -a
. ./.env
set +a
```

Expected local files:

```bash
cp example.vars terraform.tfvars
cp dns-records.example.json dns-records.local.json
cp .env.example .env
```

Do not print token values, generated passwords, or real local DNS inventory in responses or logs.

## Workflow

1. Edit tracked source/example files or local ignored config as requested.
2. Run formatting and validation.
3. If a plan is requested, load `.env` and run `tofu plan -out=tfplan` or `terraform plan -out=tfplan`.
4. Summarize planned creates/changes/destroys.
5. Apply only after explicit approval.
6. Remove plan files after use.

## Bootstrap

After the LXC is created, install Technitium with:

```bash
./scripts/bootstrap-technitium.sh <vmid>
```

Configure local Caddy HTTPS proxy with:

```bash
./scripts/bootstrap-caddy.sh <vmid>
```

## EdgeRouter helper

`scripts/edgeos-static-host-mapping.sh` mutates a live EdgeRouter config to add a temporary static host mapping.

Run only after explicit approval.

## DNS Management

`dns.tf` uses `terraform_data` to run `scripts/apply-technitium-dns.py` against the local DNS records file specified by `var.dns_records_file`.

The intended pattern is hybrid DNS:

- Technitium Forwarder zones hold explicit static records.
- Unknown names in those zones forward to existing internal resolvers.
- The gateway should remain focused on DHCP/routing/firewall and eventually point DHCP DNS to Technitium.

A Technitium API token must be supplied via `.env`/`TF_VAR_technitium_api_token` before planning or applying DNS resources.

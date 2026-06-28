# Technitium DNS Infrastructure

OpenTofu/Terraform configuration for Proxmox LXCs running Technitium DNS and Forgejo, plus an idempotent API script for local DNS records and upstream resolver settings.

This repo intentionally keeps real hostnames, LAN IPs, DNS zones, and secrets out of tracked files. Copy the example files to local gitignored files before planning/applying.

## Tracked vs local files

Tracked examples/source:

- `*.tf`
- `scripts/`
- `.env.example`
- `example.vars`
- `dns-records.example.json`

Local ignored configuration:

- `.env` — tokens/passwords and bootstrap credentials
- `terraform.tfvars` — local Proxmox/LXC values
- `dns-records.local.json` — real local DNS zones, records, and upstream resolver policy
- `terraform.tfstate*`, `.terraform/`, `tfplan*`

## Initial local setup

```bash
cp example.vars terraform.tfvars
cp dns-records.example.json dns-records.local.json
cp .env.example .env
```

Edit those local files with your real values.

## Install OpenTofu

Windows examples:

```powershell
winget install OpenTofu.Tofu
# or
choco install opentofu
```

Verify:

```bash
tofu version
```

Terraform can be used for validation if OpenTofu is unavailable.

## Credentials

Preferred Proxmox auth is an API token. Example token creation on the Proxmox host:

```bash
pveum user add terraform@pve
pveum aclmod / -user terraform@pve -role Administrator
pveum user token add terraform@pve provider --privsep=0
```

Store secrets in `.env` or ignored `terraform.tfvars`, never in tracked files.

Load `.env` before planning/applying:

```bash
set -a
. ./.env
set +a
```

## Plan and apply

Do not apply without reviewing the plan.

```bash
tofu init
tofu fmt -check -recursive
tofu validate
tofu plan -out=tfplan
tofu show tfplan
# after review
tofu apply tfplan
```

## Import existing LXCs

If a container was created manually before adding it to this repo, import it before applying. Example for the current Forgejo shape:

```bash
tofu import proxmox_virtual_environment_container.forgejo pve/107
```

Do not run imports without review; imports mutate local state.

## Install Technitium inside the LXC

After the LXC exists and is reachable:

```bash
./scripts/bootstrap-technitium.sh 106
```

## Configure Caddy HTTPS UI on the LXC

If you want local Caddy to terminate HTTPS for the Technitium web console, add Cloudflare DNS credentials to `.env` and run:

```bash
./scripts/bootstrap-caddy.sh 106
```

The script builds Caddy with the Cloudflare DNS module and reverse-proxies the configured hostname to Technitium's local web console.

To add the Forgejo vhost in the same Caddyfile, set these in `.env` before running the script:

```bash
export FORGEJO_SERVER_NAME="git.example.internal"
export FORGEJO_UPSTREAM="192.0.2.62:3000"
```

## Install Forgejo inside the LXC

After the Forgejo LXC exists and its ZFS bind mount is writable, set the Forgejo bootstrap values and run:

```bash
export FORGEJO_VERSION="12.0.4"
export FORGEJO_DOMAIN="git.example.internal"
./scripts/bootstrap-forgejo.sh 107
```

By default, the script installs Forgejo and starts the web setup flow. To write a minimal SQLite `app.ini` during bootstrap, set:

```bash
export FORGEJO_WRITE_INITIAL_CONFIG=1
```

## DNS zones and records

`dns.tf` manages DNS through `terraform_data`, which runs:

```bash
python scripts/apply-technitium-dns.py dns-records.local.json
```

The local JSON file controls:

- upstream DNS forwarders, e.g. DNS-over-TLS Quad9 and Cloudflare Security
- conditional forwarder zones
- local A records
- local CNAME records

Use `dns-records.example.json` as the public-safe schema example.

## EdgeRouter helper

`scripts/edgeos-static-host-mapping.sh` mutates the live EdgeRouter config to add a temporary static host mapping. Run only after review and explicit approval.

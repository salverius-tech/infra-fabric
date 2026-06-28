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

## Containerized tooling

A local Docker tool image provides OpenTofu, Ansible, ShellCheck, Python, Git, SSH, and `jq` without installing those tools directly on Windows.

```bash
docker compose build infra
docker compose run --rm infra tofu fmt -check -recursive
docker compose run --rm infra tofu validate
docker compose run --rm infra ansible --version
```

For commands that need local secrets, source `.env` inside the container shell. If `.env` has Windows CRLF line endings, strip `\r` while sourcing:

```bash
docker compose run --rm infra bash -lc 'set -a; . <(tr -d "\r" < ./.env); set +a; tofu plan -out=tfplan'
```

The Compose service mounts the repo at `/workspace`, copies your Windows `%USERPROFILE%/.ssh` into the container with safe permissions for SSH access, and keeps the OpenTofu plugin cache in a named Docker volume.

## Ansible configuration management

Terraform/OpenTofu manages Proxmox infrastructure. Ansible manages in-LXC service configuration through the Proxmox host using `pct exec`/`pct push`.

Create a local inventory from the example, then keep real hostnames/IPs/tokens out of git:

```bash
cp ansible/inventory/example.yml ansible/inventory/local.yml
```

Run playbooks from the tooling container:

```bash
docker compose run --rm infra ansible-playbook ansible/playbooks/technitium.yml
docker compose run --rm infra ansible-playbook ansible/playbooks/forgejo.yml
docker compose run --rm infra ansible-playbook ansible/playbooks/caddy-proxy.yml
```

`ansible/playbooks/cleanup-old-forgejo-proxy.yml` removes the legacy Forgejo proxy/socket path from the DNS LXC after the Forgejo hostname points directly at the Forgejo LXC.

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

If `git.example.internal` points at the DNS LXC instead of the Forgejo LXC, you can add a Forgejo vhost and SSH socket proxy in the same Caddy bootstrap by setting `FORGEJO_SERVER_NAME`, `FORGEJO_UPSTREAM`, and `FORGEJO_SSH_UPSTREAM`. The preferred layout is to point the Forgejo hostname directly at the Forgejo LXC instead.

## Install Forgejo inside the LXC

After the Forgejo LXC exists and its ZFS bind mount is writable, set the Forgejo bootstrap values and run:

```bash
export FORGEJO_VERSION="12.0.4"
export FORGEJO_DOMAIN="git.example.internal"
export FORGEJO_SSH_PORT="22"
export FORGEJO_ENABLE_CADDY="1"
./scripts/bootstrap-forgejo.sh 107
```

With `FORGEJO_ENABLE_CADDY=1`, the script installs Caddy on the Forgejo LXC and terminates HTTPS for `FORGEJO_DOMAIN` with Cloudflare DNS-01. With the default `FORGEJO_CONFIGURE_SYSTEM_SSH=1`, the LXC's OpenSSH server on port 22 is integrated with Forgejo for git access, e.g. `git@git.example.internal:owner/repo.git`.

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

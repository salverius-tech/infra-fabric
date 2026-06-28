#!/usr/bin/env bash
set -euo pipefail

VMID="${1:-107}"
: "${PVE_HOST:?PVE_HOST is required}"
: "${FORGEJO_VERSION:?FORGEJO_VERSION is required, for example 12.0.4}"
: "${FORGEJO_DOMAIN:?FORGEJO_DOMAIN is required, for example git.example.internal}"
FORGEJO_ROOT_URL="${FORGEJO_ROOT_URL:-https://${FORGEJO_DOMAIN}/}"
FORGEJO_DOWNLOAD_BASE="${FORGEJO_DOWNLOAD_BASE:-https://code.forgejo.org/forgejo/forgejo/releases/download}"

pct_exec() {
  local command="$1"
  # VMID and command are intentionally expanded locally before invoking pct on the Proxmox host.
  # shellcheck disable=SC2029
  ssh "${PVE_HOST}" "pct exec '${VMID}' -- bash -lc $(printf '%q' "${command}")"
}

pct_push() {
  local destination="$1"
  local destination_dir
  local local_tmp
  local remote_tmp
  destination_dir="$(dirname "${destination}")"
  local_tmp="$(mktemp)"
  remote_tmp="/tmp/pct-push-${VMID}-$(basename "${destination}").$$"
  cat >"${local_tmp}"
  scp "${local_tmp}" "${PVE_HOST}:${remote_tmp}" >/dev/null
  rm -f "${local_tmp}"
  # VMID and destination paths are intentionally expanded locally before invoking pct on the Proxmox host.
  # shellcheck disable=SC2029
  ssh "${PVE_HOST}" "pct exec '${VMID}' -- install -d -m 0755 '${destination_dir}' && pct push '${VMID}' '${remote_tmp}' '${destination}' && rm -f '${remote_tmp}'"
}

pct_exec 'DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git git-lfs sqlite3'
pct_exec 'git lfs install --system'

pct_exec 'if ! id git >/dev/null 2>&1; then adduser --system --shell /bin/bash --gecos "Git Version Control" --group --disabled-password --home /var/lib/forgejo git; fi'
pct_exec 'install -d -m 0750 -o git -g git /var/lib/forgejo /var/lib/forgejo/custom /var/lib/forgejo/data /var/lib/forgejo/log'
pct_exec 'install -d -m 0770 -o root -g git /etc/forgejo'

pct_exec "curl -fsSL -o /usr/local/bin/forgejo ${FORGEJO_DOWNLOAD_BASE}/v${FORGEJO_VERSION}/forgejo-${FORGEJO_VERSION}-linux-amd64"
pct_exec 'chmod 0755 /usr/local/bin/forgejo && /usr/local/bin/forgejo --version'

cat <<SERVICE | pct_push /etc/systemd/system/forgejo.service
[Unit]
Description=Forgejo
After=network.target

[Service]
RestartSec=2s
Type=simple
User=git
Group=git
WorkingDirectory=/var/lib/forgejo
ExecStart=/usr/local/bin/forgejo web --config /etc/forgejo/app.ini
Restart=always
Environment=USER=git HOME=/var/lib/forgejo GITEA_WORK_DIR=/var/lib/forgejo

[Install]
WantedBy=multi-user.target
SERVICE

if [[ "${FORGEJO_WRITE_INITIAL_CONFIG:-0}" == "1" ]]; then
  cat <<APPINI | pct_push /etc/forgejo/app.ini
APP_NAME = Forgejo
RUN_USER = git
WORK_PATH = /var/lib/forgejo

[database]
DB_TYPE = sqlite3
PATH = /var/lib/forgejo/data/forgejo.db

[repository]
ROOT = /var/lib/forgejo/data/gitea-repositories

[server]
DOMAIN = ${FORGEJO_DOMAIN}
ROOT_URL = ${FORGEJO_ROOT_URL}
HTTP_ADDR = 0.0.0.0
HTTP_PORT = 3000
SSH_DOMAIN = ${FORGEJO_DOMAIN}
START_SSH_SERVER = false

[log]
MODE = file
LEVEL = Info
ROOT_PATH = /var/lib/forgejo/log
APPINI
  pct_exec 'chown root:git /etc/forgejo/app.ini && chmod 0640 /etc/forgejo/app.ini'
fi

pct_exec 'systemctl daemon-reload && systemctl enable --now forgejo && systemctl status forgejo --no-pager'

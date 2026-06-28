#!/usr/bin/env bash
set -euo pipefail

VMID="${1:-107}"
: "${PVE_HOST:?PVE_HOST is required}"
: "${FORGEJO_VERSION:?FORGEJO_VERSION is required, for example 12.0.4}"
: "${FORGEJO_DOMAIN:?FORGEJO_DOMAIN is required, for example git.example.internal}"
FORGEJO_ROOT_URL="${FORGEJO_ROOT_URL:-https://${FORGEJO_DOMAIN}/}"
FORGEJO_SSH_PORT="${FORGEJO_SSH_PORT:-22}"
FORGEJO_CONFIGURE_SYSTEM_SSH="${FORGEJO_CONFIGURE_SYSTEM_SSH:-1}"
FORGEJO_ENABLE_CADDY="${FORGEJO_ENABLE_CADDY:-0}"
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

pct_exec 'DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git git-lfs openssh-server sqlite3'
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
SSH_PORT = ${FORGEJO_SSH_PORT}
SSH_USER = git
START_SSH_SERVER = false

[log]
MODE = file
LEVEL = Info
ROOT_PATH = /var/lib/forgejo/log
APPINI
  pct_exec 'chown root:git /etc/forgejo/app.ini && chmod 0640 /etc/forgejo/app.ini'
fi

if [[ "${FORGEJO_CONFIGURE_SYSTEM_SSH}" == "1" ]]; then
  cat <<SSHD | pct_push /etc/ssh/sshd_config.d/forgejo.conf
Match User git
    AuthorizedKeysCommandUser git
    AuthorizedKeysCommand /usr/local/bin/forgejo keys -c /etc/forgejo/app.ini -e git -u %u -t %t -k %k
SSHD
  pct_exec 'systemctl restart ssh'
fi

if [[ "${FORGEJO_ENABLE_CADDY}" == "1" ]]; then
  if [[ -z "${FORGEJO_CADDY_CERT_FILE:-}" || -z "${FORGEJO_CADDY_KEY_FILE:-}" ]]; then
    : "${CF_API_EMAIL:?CF_API_EMAIL is required when FORGEJO_ENABLE_CADDY=1 without static cert files}"
    : "${CF_DNS_API_TOKEN:?CF_DNS_API_TOKEN is required when FORGEJO_ENABLE_CADDY=1 without static cert files}"
  fi

  pct_exec 'DEBIAN_FRONTEND=noninteractive apt-get install -y caddy'

  if [[ -n "${FORGEJO_CADDY_CERT_FILE:-}" && -n "${FORGEJO_CADDY_KEY_FILE:-}" ]]; then
    cat <<CADDYFILE | pct_push /etc/caddy/Caddyfile
${FORGEJO_DOMAIN} {
    encode zstd gzip
    reverse_proxy 127.0.0.1:3000
    tls ${FORGEJO_CADDY_CERT_FILE} ${FORGEJO_CADDY_KEY_FILE}
}
CADDYFILE
  else
    pct_exec 'curl -fsSL https://go.dev/dl/go1.24.4.linux-amd64.tar.gz -o /tmp/go.tar.gz && rm -rf /usr/local/go && tar -C /usr/local -xzf /tmp/go.tar.gz'
    # PATH is intentionally expanded inside the remote pct_exec shell.
    # shellcheck disable=SC2016
    pct_exec 'PATH=/usr/local/go/bin:${PATH} GOBIN=/usr/local/bin /usr/local/go/bin/go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest'
    # shellcheck disable=SC2016
    pct_exec 'PATH=/usr/local/go/bin:${PATH} /usr/local/bin/xcaddy build --with github.com/caddy-dns/cloudflare --output /tmp/caddy-cloudflare'
    pct_exec 'install -m 0755 /tmp/caddy-cloudflare /usr/bin/caddy && /usr/bin/caddy version'

    {
      printf 'CF_API_EMAIL=%s\n' "${CF_API_EMAIL}"
      printf 'CF_DNS_API_TOKEN=%s\n' "${CF_DNS_API_TOKEN}"
    } | pct_push /etc/caddy/env
    pct_exec 'chmod 0600 /etc/caddy/env && chown root:caddy /etc/caddy/env'

    cat <<CADDYFILE | pct_push /etc/caddy/Caddyfile
{
    email ${CF_API_EMAIL}
}

${FORGEJO_DOMAIN} {
    encode zstd gzip
    reverse_proxy 127.0.0.1:3000

    tls {
        dns cloudflare {env.CF_DNS_API_TOKEN}
        resolvers 1.1.1.1
    }
}
CADDYFILE
  fi
  pct_exec 'chown root:caddy /etc/caddy/Caddyfile && chmod 0644 /etc/caddy/Caddyfile'

  if [[ -n "${FORGEJO_CADDY_CERT_FILE:-}" && -n "${FORGEJO_CADDY_KEY_FILE:-}" ]]; then
    cat <<OVERRIDE | pct_push /etc/systemd/system/caddy.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile
OVERRIDE
  else
    cat <<OVERRIDE | pct_push /etc/systemd/system/caddy.service.d/override.conf
[Service]
EnvironmentFile=/etc/caddy/env
ExecStart=
ExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile
OVERRIDE
  fi

  if [[ -n "${FORGEJO_CADDY_CERT_FILE:-}" && -n "${FORGEJO_CADDY_KEY_FILE:-}" ]]; then
    pct_exec 'systemctl daemon-reload && caddy fmt --overwrite /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile'
  else
    pct_exec 'systemctl daemon-reload && set -a && . /etc/caddy/env && set +a && caddy fmt --overwrite /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile'
  fi
  pct_exec 'systemctl enable --now caddy && systemctl restart caddy && systemctl status caddy --no-pager'
fi

pct_exec 'systemctl daemon-reload && systemctl enable --now forgejo && systemctl status forgejo --no-pager'

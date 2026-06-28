#!/usr/bin/env bash
set -euo pipefail

VMID="${1:-106}"
: "${PVE_HOST:?PVE_HOST is required}"

pct_exec() {
  local command="$1"
  # VMID and command are intentionally expanded locally before invoking pct on the Proxmox host.
  # shellcheck disable=SC2029
  ssh "${PVE_HOST}" "pct exec '${VMID}' -- bash -lc $(printf '%q' "${command}")"
}

pct_exec 'DEBIAN_FRONTEND=noninteractive apt-get update && (DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates libicu72 || DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates libicu-dev)'
pct_exec 'curl -sSL https://download.technitium.com/dns/install.sh | bash'
pct_exec 'systemctl status dns --no-pager'

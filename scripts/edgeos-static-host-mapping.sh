#!/usr/bin/env bash
set -euo pipefail

: "${EDGE_HOST:?EDGE_HOST is required}"
EDGE_USER="${EDGE_USER:-ubnt}"
: "${1:?hostname argument is required}"
: "${2:?ip-address argument is required}"
HOSTNAME="$1"
IP_ADDRESS="$2"

# Intentionally expand HOSTNAME/IP_ADDRESS locally before sending EdgeOS commands.
# shellcheck disable=SC2087
ssh "${EDGE_USER}@${EDGE_HOST}" <<EOF
configure
set system static-host-mapping host-name ${HOSTNAME} inet ${IP_ADDRESS}
commit
save
exit
EOF

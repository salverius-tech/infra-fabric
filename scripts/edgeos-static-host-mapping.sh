#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/edgeos-static-host-mapping.sh [--dry-run] [--yes] <hostname> <ip-address>

Adds an EdgeOS static host mapping. This mutates live router config unless --dry-run is used.
Requires EDGE_HOST and optionally EDGE_USER (default: ubnt).
USAGE
}

dry_run=0
yes=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --yes)
      yes=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

: "${EDGE_HOST:?EDGE_HOST is required}"
EDGE_USER="${EDGE_USER:-ubnt}"
: "${1:?hostname argument is required}"
: "${2:?ip-address argument is required}"
HOSTNAME="$1"
IP_ADDRESS="$2"

if [[ ! "${HOSTNAME}" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$ ]]; then
  printf 'Invalid hostname: %s\n' "${HOSTNAME}" >&2
  exit 1
fi

if [[ ! "${IP_ADDRESS}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  printf 'Invalid IPv4 address: %s\n' "${IP_ADDRESS}" >&2
  exit 1
fi
IFS=. read -r octet1 octet2 octet3 octet4 <<<"${IP_ADDRESS}"
for octet in "${octet1}" "${octet2}" "${octet3}" "${octet4}"; do
  if ((octet < 0 || octet > 255)); then
    printf 'Invalid IPv4 address: %s\n' "${IP_ADDRESS}" >&2
    exit 1
  fi
done

commands=$(cat <<EOF
configure
set system static-host-mapping host-name ${HOSTNAME} inet ${IP_ADDRESS}
commit
save
exit
EOF
)

if [[ "${dry_run}" -eq 1 ]]; then
  printf '%s\n' "${commands}"
  exit 0
fi

if [[ "${yes}" -ne 1 ]]; then
  printf 'This will update EdgeOS static host mapping on %s@%s. Continue? [y/N] ' "${EDGE_USER}" "${EDGE_HOST}" >&2
  read -r answer
  if [[ ! "${answer}" =~ ^[Yy]$ ]]; then
    printf 'Aborted.\n' >&2
    exit 1
  fi
fi

ssh -- "${EDGE_USER}@${EDGE_HOST}" <<<"${commands}"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  scripts/hermes-state.sh backup
  scripts/hermes-state.sh restore values/service-backups/hermes/hermes-state-YYYYmmddTHHMMSSZ.tar.gz

Compatibility wrapper for scripts/service-state.sh. Hermes backups contain the
runtime user's .hermes directory, including memory/soul files, config, history,
logs, and Hermes-managed backups.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command_name="$1"
shift

case "${command_name}" in
  backup)
    if [[ $# -ne 0 ]]; then
      usage
      exit 2
    fi
    scripts/service-state.sh backup hermes
    ;;
  restore)
    if [[ $# -ne 1 ]]; then
      usage
      exit 2
    fi
    scripts/service-state.sh restore hermes "$1"
    ;;
  *)
    usage
    exit 2
    ;;
esac

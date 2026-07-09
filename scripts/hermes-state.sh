#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  scripts/hermes-state.sh backup
  scripts/hermes-state.sh restore values/hermes-backups/hermes-state-YYYYmmddTHHMMSSZ.tar.gz

Backups are written to values/hermes-backups/ and contain /root/.hermes from the Hermes service host.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command_name="$1"
shift

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
backup_dir="${HERMES_STATE_BACKUP_DIR:-/workspace/values/hermes-backups}"

container_path() {
  local input="$1"
  case "${input}" in
    /workspace/*)
      printf '%s\n' "${input}"
      ;;
    /*)
      case "${input}" in
        "${repo_root}"/*)
          printf '/workspace/%s\n' "${input#"${repo_root}"/}"
          ;;
        *)
          printf '%s\n' "${input}"
          ;;
      esac
      ;;
    *)
      printf '/workspace/%s\n' "${input#./}"
      ;;
  esac
}

case "${command_name}" in
  backup)
    if [[ $# -ne 0 ]]; then
      usage
      exit 2
    fi
    # shellcheck disable=SC2016
    HERMES_STATE_BACKUP_DIR="${backup_dir}" scripts/run-infra.sh bash -lc \
      'export PATH=/opt/ansible/bin:$PATH; ansible-playbook -i values/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py infra/ansible/playbooks/hermes-state-backup.yml'
    ;;
  restore)
    if [[ $# -ne 1 ]]; then
      usage
      exit 2
    fi
    restore_file="$(container_path "$1")"
    case "${restore_file}" in
      /workspace/values/hermes-backups/*.tar.gz) ;;
      *)
        printf 'Restore archive must be under values/hermes-backups/ and end in .tar.gz\n' >&2
        exit 2
        ;;
    esac
    # shellcheck disable=SC2016
    HERMES_STATE_RESTORE_FILE="${restore_file}" scripts/run-infra.sh bash -lc \
      'export PATH=/opt/ansible/bin:$PATH; ansible-playbook -i values/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py infra/ansible/playbooks/hermes-state-restore.yml'
    ;;
  *)
    usage
    exit 2
    ;;
esac

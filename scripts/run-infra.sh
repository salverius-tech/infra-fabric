#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
source scripts/container-secret-transport.sh
require_site_context
transport_parse_args "$@"
set -- "${transport_remaining_args[@]}"
transport_prepare
values_dir="$(site_values_dir)"

# The normal snapshot destination is inside the selected private values site. An
# explicit host path is needed only when that filesystem cannot provide the
# no-replace directory publication required by the execution-snapshot boundary.
# Mount it at a fixed container path so a host-local path is never interpreted
# inside the tooling container.
execution_snapshot_host_root="${INFRA_EXECUTION_SNAPSHOT_ROOT:-}"
if [[ -n "${execution_snapshot_host_root}" ]]; then
  if [[ "${execution_snapshot_host_root}" != /* ]]; then
    printf 'INFRA_EXECUTION_SNAPSHOT_ROOT must be an absolute private host path.\n' >&2
    exit 2
  fi
  if [[ -L "${execution_snapshot_host_root}" ]]; then
    printf 'INFRA_EXECUTION_SNAPSHOT_ROOT must not be a symlink.\n' >&2
    exit 2
  fi
  mkdir -p -- "${execution_snapshot_host_root}"
  chmod 0700 -- "${execution_snapshot_host_root}"
  transport_compose_mount_args+=(
    -v "${execution_snapshot_host_root}:/run/infra-fabric/execution-snapshots"
  )
  transport_compose_env_args+=(
    --env "INFRA_EXECUTION_SNAPSHOT_ROOT=/run/infra-fabric/execution-snapshots"
  )
fi
state_snapshot_host_root="${INFRA_STATE_SNAPSHOT_ROOT:-}"
if [[ -n "${state_snapshot_host_root}" ]]; then
  if [[ "${state_snapshot_host_root}" != /* ]]; then
    printf 'INFRA_STATE_SNAPSHOT_ROOT must be an absolute private host path.\n' >&2
    exit 2
  fi
  if [[ -L "${state_snapshot_host_root}" ]]; then
    printf 'INFRA_STATE_SNAPSHOT_ROOT must not be a symlink.\n' >&2
    exit 2
  fi
  mkdir -p -- "${state_snapshot_host_root}"
  chmod 0700 -- "${state_snapshot_host_root}"
  transport_compose_mount_args+=(
    -v "${state_snapshot_host_root}:/run/infra-fabric/state-backups"
  )
  transport_compose_env_args+=(
    --env "INFRA_STATE_SNAPSHOT_ROOT=/run/infra-fabric/state-backups"
  )
fi

export INFRA_HOST_UID="${INFRA_HOST_UID:-$(scripts/host-id.sh uid)}"
export INFRA_HOST_GID="${INFRA_HOST_GID:-$(scripts/host-id.sh gid)}"
export INFRA_GIT_COMMIT="${INFRA_GIT_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/run-infra.XXXXXX")"
chmod 0700 "${tmp_dir}"
cleanup() {
  rm -rf -- "${tmp_dir}"
}
trap cleanup EXIT HUP INT TERM

umask 077
docker compose run --rm \
  "${transport_compose_mount_args[@]}" \
  "${transport_compose_env_args[@]}" \
  --env VALUES_DIR="${VALUES_DIR:-values}" \
  --env VALUES_SITE="${VALUES_SITE:-}" \
  --env INFRA_VALUES_DIR="${values_dir}" \
  --env INFRA_HOST_IDENTITY_SKIP_ROOT="${INFRA_HOST_IDENTITY_SKIP_ROOT:-}" \
  --env INFRA_HOST_IDENTITY_ONLY="${INFRA_HOST_IDENTITY_ONLY:-}" \
  infra python scripts/site_lock.py --lock-path "${values_dir}/.infra-fabric.lock" -- "$@"

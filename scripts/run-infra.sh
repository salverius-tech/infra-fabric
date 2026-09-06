#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
source scripts/container-secret-transport.sh
require_site_context
transport_parse_args "$@"
set -- "${transport_remaining_args[@]}"
transport_prepare
values_dir="$(site_values_dir)"
private_site_root="${XDG_STATE_HOME:-${HOME}/.local/state}/infra-fabric/sites/${VALUES_SITE}"
if [[ "${private_site_root}" != /* ]]; then
  printf 'controller-local private artifact root must be absolute.\n' >&2
  exit 2
fi

prepare_private_directory() {
  local path="$1"
  local label="$2"
  python3 - "${path}" "${label}" <<'PY'
import os
from pathlib import Path
import sys

sys.path.insert(0, "scripts")
from private_files import PrivateFileError, ensure_private_directory, open_private_directory

path = Path(sys.argv[1])
label = sys.argv[2]
try:
    if os.path.lexists(path):
        with open_private_directory(path, label) as descriptor:
            if os.fstat(descriptor).st_uid != os.getuid():
                raise PrivateFileError(f"{label} owner is unsafe")
    else:
        ensure_private_directory(path)
except (OSError, PrivateFileError) as error:
    raise SystemExit(f"{label} is unavailable or unsafe") from error
PY
}

# Generated projections are derived private artifacts. Some selected values
# filesystems (notably NFS) cannot provide the atomic directory exchange used by
# canonical-render. Mount a private controller-local parent and publish into its
# ordinary generated/ child: a bind-mount root itself cannot be renamed or
# exchanged atomically. Canonical inputs remain on the shared values filesystem.
generated_host_root="${INFRA_GENERATED_ROOT:-${private_site_root}/generated}"
if [[ -n "${generated_host_root}" ]]; then
  if [[ "${generated_host_root}" != /* ]]; then
    printf 'INFRA_GENERATED_ROOT must be an absolute private host path.\n' >&2
    exit 2
  fi
  prepare_private_directory "${generated_host_root}" INFRA_GENERATED_ROOT
  transport_compose_mount_args+=(
    -v "${generated_host_root}:/run/infra-fabric/generated"
  )
  transport_compose_env_args+=(
    --env "INFRA_GENERATED_DIR=/run/infra-fabric/generated/generated"
  )
fi

# The normal snapshot destination is inside the selected private values site. An
# explicit host path is needed only when that filesystem cannot provide the
# no-replace directory publication required by the execution-snapshot boundary.
# Mount it at a fixed container path so a host-local path is never interpreted
# inside the tooling container.
execution_snapshot_host_root="${INFRA_EXECUTION_SNAPSHOT_ROOT:-${private_site_root}/execution-snapshots}"
if [[ -n "${execution_snapshot_host_root}" ]]; then
  if [[ "${execution_snapshot_host_root}" != /* ]]; then
    printf 'INFRA_EXECUTION_SNAPSHOT_ROOT must be an absolute private host path.\n' >&2
    exit 2
  fi
  prepare_private_directory "${execution_snapshot_host_root}" INFRA_EXECUTION_SNAPSHOT_ROOT
  transport_compose_mount_args+=(
    -v "${execution_snapshot_host_root}:/run/infra-fabric/execution-snapshots"
  )
  transport_compose_env_args+=(
    --env "INFRA_EXECUTION_SNAPSHOT_ROOT=/run/infra-fabric/execution-snapshots"
  )
fi
state_snapshot_host_root="${INFRA_STATE_SNAPSHOT_ROOT:-${private_site_root}/state-backups}"
if [[ -n "${state_snapshot_host_root}" ]]; then
  if [[ "${state_snapshot_host_root}" != /* ]]; then
    printf 'INFRA_STATE_SNAPSHOT_ROOT must be an absolute private host path.\n' >&2
    exit 2
  fi
  prepare_private_directory "${state_snapshot_host_root}" INFRA_STATE_SNAPSHOT_ROOT
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

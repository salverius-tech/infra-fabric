#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
source scripts/container-secret-transport.sh
require_site_context
transport_parse_args "$@"
set -- "${transport_remaining_args[@]}"
transport_prepare
values_dir="$(site_values_dir)"

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

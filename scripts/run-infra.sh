#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
source scripts/container-secret-transport.sh
transport_parse_args "$@"
set -- "${transport_remaining_args[@]}"
transport_prepare
values_dir="$(site_values_dir)"
env_file="${values_dir}/.env"
canonical_site=false
if [[ -f "${values_dir}/site.yaml" ]]; then
  canonical_site=true
fi
if [[ "${canonical_site}" != true && ! -f "${env_file}" ]]; then
  printf 'Missing %s. Run just setup or just setup <remote>.\n' "${env_file}" >&2
  exit 1
fi

export INFRA_HOST_UID="${INFRA_HOST_UID:-$(scripts/host-id.sh uid)}"
export INFRA_HOST_GID="${INFRA_HOST_GID:-$(scripts/host-id.sh gid)}"
export INFRA_GIT_COMMIT="${INFRA_GIT_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/run-infra.XXXXXX")"
chmod 0700 "${tmp_dir}"
compose_env_file="${tmp_dir}/env"
cleanup() {
  rm -rf -- "${tmp_dir}"
}
trap cleanup EXIT HUP INT TERM

umask 077
compose_env_args=()
if [[ "${canonical_site}" != true ]]; then
  # Convert values/.env to a sanitized Docker env file. Do not source it directly.
  scripts/python.sh scripts/parse-env.py --env-file "${env_file}" >"${compose_env_file}"
  chmod 0600 "${compose_env_file}"
  compose_env_args=(--env-from-file "${compose_env_file}")
fi

docker compose run --rm \
  "${transport_compose_mount_args[@]}" \
  "${transport_compose_env_args[@]}" \
  --env VALUES_DIR="${VALUES_DIR:-values}" \
  --env VALUES_SITE="${VALUES_SITE:-}" \
  --env INFRA_VALUES_DIR="${values_dir}" \
  --env INFRA_HOST_IDENTITY_SKIP_ROOT="${INFRA_HOST_IDENTITY_SKIP_ROOT:-}" \
  --env INFRA_HOST_IDENTITY_ONLY="${INFRA_HOST_IDENTITY_ONLY:-}" \
  "${compose_env_args[@]}" \
  infra "$@"

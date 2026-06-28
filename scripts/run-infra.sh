#!/usr/bin/env bash
set -euo pipefail

values_dir="${VALUES_DIR:-values}"
env_file="${values_dir}/.env"
if [[ ! -f "${env_file}" ]]; then
  printf 'Missing %s. Run just setup or just setup <remote>.\n' "${env_file}" >&2
  exit 1
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/run-infra.XXXXXX")"
chmod 0700 "${tmp_dir}"
compose_env_file="${tmp_dir}/env"
cleanup() {
  rm -rf -- "${tmp_dir}"
}
trap cleanup EXIT HUP INT TERM

# Convert values/.env to a sanitized Docker env file. Do not source it directly.
umask 077
python3 scripts/parse-env.py --env-file "${env_file}" >"${compose_env_file}"
chmod 0600 "${compose_env_file}"

docker compose run --rm --env-from-file "${compose_env_file}" infra "$@"

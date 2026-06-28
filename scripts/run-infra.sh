#!/usr/bin/env bash
set -euo pipefail

values_dir="${VALUES_DIR:-values}"
env_file="${values_dir}/.env"
if [[ ! -f "${env_file}" ]]; then
  printf 'Missing %s. Run just setup or just setup <remote>.\n' "${env_file}" >&2
  exit 1
fi

# Convert values/.env to a sanitized Docker env file. Do not source it directly.
compose_env_file="$(mktemp)"
trap 'rm -f "${compose_env_file}"' EXIT
python3 scripts/parse-env.py --env-file "${env_file}" >"${compose_env_file}"

exec docker compose run --rm --env-from-file "${compose_env_file}" infra "$@"

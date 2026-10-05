#!/usr/bin/env bash
set -euo pipefail

site_arg="${1:-}"
site="${site_arg#SITE=}"
if [[ -z "${site}" || "${site_arg}" != "SITE="* ]]; then
  printf 'Usage: scripts/edit-secrets.sh SITE=<site>\n' >&2
  exit 2
fi

VALUES_SITE="${site}"
export VALUES_SITE
source scripts/site-context.sh
require_site_context
values_dir="$(site_values_dir)"
SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${HOME}/.config/infra-fabric/keys/${VALUES_SITE}/site.age}"
export SOPS_AGE_KEY_FILE

if [[ ! -f "${SOPS_AGE_KEY_FILE}" || ! -r "${SOPS_AGE_KEY_FILE}" ]]; then
  printf 'External site age identity is missing or unreadable: %s\n' "${SOPS_AGE_KEY_FILE}" >&2
  exit 2
fi
if [[ ! -f "${values_dir}/.sops.yaml" || ! -f "${values_dir}/secrets.sops.yaml" ]]; then
  printf 'Selected site SOPS policy or bundle is missing: %s\n' "${values_dir}" >&2
  exit 2
fi

sops_bin="$(command -v sops || true)"
if [[ -z "${sops_bin}" && -x "${HOME}/.local/bin/sops" ]]; then
  sops_bin="${HOME}/.local/bin/sops"
fi
if [[ -n "${sops_bin}" ]]; then
  SOPS_EDITOR="${SOPS_EDITOR:-${EDITOR:-vi}}" "${sops_bin}" \
    --config "${values_dir}/.sops.yaml" edit "${values_dir}/secrets.sops.yaml"
else
  source scripts/container-secret-transport.sh
  transport_prepare
  docker compose run --rm \
    "${transport_compose_mount_args[@]}" \
    "${transport_compose_env_args[@]}" \
    infra sops --config "/workspace/${values_dir}/.sops.yaml" \
    edit "/workspace/${values_dir}/secrets.sops.yaml"
fi

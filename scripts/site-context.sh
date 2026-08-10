#!/usr/bin/env bash
# Resolve the selected private site values directory.
# shellcheck shell=bash

require_site_context() {
  local site="${VALUES_SITE:-}"
  if [[ -z "${site}" ]]; then
    printf 'VALUES_SITE is required for normal operator workflows. Set VALUES_SITE=<site>, ensure values/sites/<site>/site.yaml exists, then rerun the canonical recipe. Use the explicit migration or recovery tools for legacy forensics.\n' >&2
    return 2
  fi
  local values_path
  values_path="$(site_values_dir)" || return
  export INFRA_VALUES_DIR="${INFRA_VALUES_DIR:-${values_path}}"
  # Canonical SOPS consumers use the site-scoped external age identity by default.
  # Callers may override this for an explicitly supplied transport path.
  export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${HOME}/.config/infra-fabric/keys/${site}/site.age}"
  if [[ ! -f "${values_path}/site.yaml" ]]; then
    printf 'Selected canonical site is missing: %s/site.yaml. Restore or create the canonical site through just setup "" %s; use explicit migration or recovery tools for legacy forensics.\n' "${values_path}" "${site}" >&2
    return 2
  fi
  return 0
}

require_canonical_authority() {
  local values_path
  values_path="$(site_values_dir)" || return
  require_site_context
}

canonical_projection_names() {
  printf '%s\n' \
    manifest.json \
    terraform.auto.tfvars.json \
    ansible-inventory.json \
    ansible-vars.json \
    dns-records.json
}

require_canonical_projection_set() {
  local generated_dir="${1:?canonical generated directory is required}"
  local projection
  while IFS= read -r projection; do
    if [[ ! -f "${generated_dir}/${projection}" ]]; then
      printf 'Canonical projections are missing: %s. Rerun just plan for the selected canonical site.\n' "${projection}" >&2
      return 2
    fi
  done < <(canonical_projection_names)
}

site_values_dir() {
  local root="${VALUES_DIR:-values}"
  local site="${VALUES_SITE:-}"
  if [[ -n "${site}" ]]; then
    if [[ ! "${site}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ || "${site}" == *..* ]]; then
      printf 'VALUES_SITE must be a simple site identifier.\n' >&2
      return 2
    fi
    if [[ "${root}" != */"${site}" ]]; then
      root="${root}/sites/${site}"
    fi
  fi
  printf '%s\n' "${root}"
}

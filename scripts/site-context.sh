#!/usr/bin/env bash
# Resolve the selected private site values directory.
# shellcheck shell=bash

require_site_context() {
  local site="${VALUES_SITE:-}"
  if [[ -z "${site}" ]]; then
    printf 'VALUES_SITE is required for mutating infrastructure operations.\n' >&2
    return 2
  fi
  local values_path
  values_path="$(site_values_dir)" || return
  if [[ ! -f "${values_path}/site.json" ]]; then
    printf 'Selected site metadata is missing: %s/site.json\n' "${values_path}" >&2
    return 2
  fi
}

require_canonical_authority() {
  local values_path
  values_path="$(site_values_dir)" || return
  if [[ -f "${values_path}/site.yaml" ]]; then
    return 0
  fi
  if [[ "${INFRA_ALLOW_LEGACY_COMPATIBILITY:-}" == "true" ]]; then
    printf 'WARNING: legacy compatibility explicitly enabled for %s.\n' "${values_path}" >&2
    return 0
  fi
  printf 'Canonical site.yaml is required for operational consumers: %s/site.yaml. Set INFRA_ALLOW_LEGACY_COMPATIBILITY=true only for a reviewed legacy-only run.\n' "${values_path}" >&2
  return 2
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

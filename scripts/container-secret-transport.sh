#!/usr/bin/env bash
# Shared host-side transport for an external SOPS age key file.
set -euo pipefail

SOPS_AGE_CONTAINER_KEY_FILE=/run/secrets/sops-age-key
transport_compose_mount_args=()
transport_compose_env_args=()
transport_remaining_args=()

transport_parse_args() {
  local key_from_arg=""
  transport_remaining_args=()
  if (($# > 0)) && [[ "$1" == --sops-age-key-file ]]; then
    if (($# < 2)); then
      printf 'SOPS age key-file transport is unavailable\n' >&2
      return 1
    fi
    key_from_arg=$2
    shift 2
    if (($# > 0)) && [[ "$1" == -- ]]; then
      shift
    fi
  elif (($# > 0)) && [[ "$1" == -- ]]; then
    shift
  fi
  transport_remaining_args=("$@")
  if [[ -n "$key_from_arg" ]]; then
    SOPS_AGE_KEY_FILE=$key_from_arg
    export SOPS_AGE_KEY_FILE
  fi
}

transport_prepare() {
  transport_compose_mount_args=()
  transport_compose_env_args=()
  [[ -n "${SOPS_AGE_KEY_FILE:-}" ]] || return 0
  if [[ "${SOPS_AGE_KEY_FILE}" == "${SOPS_AGE_CONTAINER_KEY_FILE}" ]]; then
    return 0
  fi

  local resolved mode
  resolved=$(readlink -f -- "$SOPS_AGE_KEY_FILE" 2>/dev/null || true)
  if [[ -z "$resolved" || ! -f "$resolved" || ! -r "$resolved" ]]; then
    printf 'SOPS age key-file transport is unavailable\n' >&2
    return 1
  fi
  mode=$(stat -c '%a' -- "$resolved" 2>/dev/null || true)
  if [[ -z "$mode" || $((8#$mode & 077)) -ne 0 ]]; then
    printf 'SOPS age key-file transport is unavailable\n' >&2
    return 1
  fi
  transport_compose_mount_args=(--mount "type=bind,src=${resolved},dst=${SOPS_AGE_CONTAINER_KEY_FILE},readonly")
  transport_compose_env_args=(--env "SOPS_AGE_KEY_FILE=${SOPS_AGE_CONTAINER_KEY_FILE}")
}

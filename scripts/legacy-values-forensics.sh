#!/usr/bin/env bash
set -euo pipefail

if (( $# != 0 )); then
  printf 'recover-legacy-values-forensics does not accept or forward arguments.\n' >&2
  exit 2
fi

values_dir="${VALUES_DIR:-values}"
if [[ ! "${values_dir}" =~ ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$ || "/${values_dir}/" == *"/./"* || "/${values_dir}/" == *"/../"* ]]; then
  printf 'VALUES_DIR must be a normalized workspace-relative path.\n' >&2
  exit 2
fi

export INFRA_HOST_UID="${INFRA_HOST_UID:-$(scripts/host-id.sh uid)}"
export INFRA_HOST_GID="${INFRA_HOST_GID:-$(scripts/host-id.sh gid)}"

compose_args=(compose run --rm --no-deps)
if [[ ! -t 0 || ! -t 1 ]]; then
  compose_args+=(-T)
fi

# Exact command: caller arguments, output/candidate flags, provider inputs, and
# alternate Python entrypoints never cross this report-only boundary.
exec docker "${compose_args[@]}" legacy-values-forensics \
  python -B scripts/legacy-values-discovery.py \
  --values-dir "/workspace/${values_dir}" \
  --repo /workspace

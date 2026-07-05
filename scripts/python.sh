#!/usr/bin/env bash
set -euo pipefail

python_bin=""
for candidate in python3 py python; do
  if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" --version >/dev/null 2>&1; then
    python_bin="${candidate}"
    break
  fi
done

if [[ -z "${python_bin}" ]]; then
  printf 'Missing Python. Install Python or ensure python3, py, or python is on PATH.\n' >&2
  exit 1
fi

exec "${python_bin}" "$@"

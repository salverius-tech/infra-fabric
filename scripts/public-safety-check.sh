#!/usr/bin/env bash
set -euo pipefail

ignored_file="$(mktemp .public-safety-ignored.XXXXXX)"
cleanup() {
  rm -f -- "${ignored_file}"
}
trap cleanup EXIT HUP INT TERM

: >"${ignored_file}"
for path in \
  scaffold/dns-records.local.json \
  scaffold/sites/_template/site.yaml \
  settings.example.json; do
  if git check-ignore -q -- "${path}"; then
    printf '%s\n' "${path}" >>"${ignored_file}"
  fi
done

scripts/python.sh scripts/public-safety-check.py \
  --ignored-files "${ignored_file}"

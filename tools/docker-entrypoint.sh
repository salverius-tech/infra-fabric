#!/usr/bin/env bash
set -euo pipefail

if [[ -d /ssh-ro ]]; then
  install -d -m 0700 /root/.ssh

  for path in /ssh-ro/known_hosts /ssh-ro/config /ssh-ro/*.pub; do
    if [[ -f "${path}" ]]; then
      cp "${path}" /root/.ssh/
    fi
  done

  if [[ "${INFRA_COPY_SSH_KEYS:-false}" == "true" ]]; then
    find /ssh-ro -maxdepth 1 -type f \
      ! -name '*.pub' \
      ! -name known_hosts \
      ! -name config \
      -exec cp {} /root/.ssh/ \;
  fi

  chmod 0700 /root/.ssh
  find /root/.ssh -type f -name '*.pub' -exec chmod 0644 {} +
  find /root/.ssh -type f ! -name '*.pub' -exec chmod 0600 {} +
fi

exec "$@"

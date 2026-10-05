#!/usr/bin/env bash
# shellcheck shell=bash

require_host_ssh_directory() {
  local ssh_dir="${HOST_SSH_DIR:-}"
  if [[ -z "${ssh_dir}" ]]; then
    if [[ -z "${HOME:-}" ]]; then
      printf 'HOME or HOST_SSH_DIR is required for the read-only SSH mount.\n' >&2
      return 2
    fi
    ssh_dir="${HOME}/.ssh"
  fi
  if [[ ! -d "${ssh_dir}" || ! -r "${ssh_dir}" || ! -x "${ssh_dir}" ]]; then
    printf 'SSH mount directory is missing or unreadable; set HOST_SSH_DIR to a readable directory: %s\n' "${ssh_dir}" >&2
    return 2
  fi
  HOST_SSH_DIR="${ssh_dir}"
  export HOST_SSH_DIR
}

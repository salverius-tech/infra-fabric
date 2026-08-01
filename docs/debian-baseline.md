# Debian baseline

This runbook uses Debian 13 as the default guest baseline:

- **LXCs** (Technitium, Forgejo runner, Infisical, Hermes, Tailscale client, and LXC-mode services) are created from the Proxmox `debian-13` standard container template represented by the `debian_template_*` OpenTofu variables.
- **Service VMs** use Debian 13 genericcloud images through the shared VM image variables.
- **`onramp_host`** remains provisioned as a Debian 13 genericcloud VM.

Changing `debian_template_*` affects newly created LXCs. Existing containers do not change operating-system baselines in place because the LXC module ignores `operating_system[0].template_file_id` drift to avoid accidental guest replacement. To move an existing LXC to the current Debian 13 template, rebuild that guest through the reviewed `just plan` / approved `just apply` workflow.

The managed host root password is delivered only during a host-limited bootstrap invocation through the transient `INFRA_BOOTSTRAP_ROOT_PASSWORD` environment boundary. Service playbooks do not rotate credentials, and SSH key access remains the preferred authentication method. Password rotation requires an existing working Ansible connection; recovery from lost access still requires the Proxmox console or another approved recovery path.

When rebuilding stateful services, review the plan carefully and confirm any replacements explicitly. Preserve service data with external storage or backups when desired; this repository does not automatically migrate arbitrary in-guest state between OS baseline rebuilds.

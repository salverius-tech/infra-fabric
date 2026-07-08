[
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "Onramp can receive a host that is SSH-reachable but not deployable because the container runtime contract is undefined.",
    "evidence": "Plan T5 accepts either 'podman compose' or a 'Compose-compatible provider'; Onramp constraint says service port semantics but the plan never defines deploy user, compose command, Docker API socket, or DOCKER_HOST semantics.",
    "required_fix": "Specify rootless vs rootful Podman, deployment user, exact compose provider/command, socket path/API expectations, and validate them using the same user Onramp will use.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "Ansible bootstrap may fail before Podman installation if VM login assumptions differ from inventory defaults.",
    "evidence": "Existing infra/ansible/inventory/tfvars.py sets tfvars-derived hosts to ansible_user=root; the plan only says SSH keys and root/user access should be 'consistent with existing bootstrap patterns' while introducing a QEMU cloud-init VM.",
    "required_fix": "Define cloud-init user, authorized keys, root-login policy, sudo requirements, and inventory variables for onramp_host explicitly; include an SSH preflight that proves Ansible can become the required user before package tasks.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "medium",
    "severity_rationale": "The Debian 13 VM may not be creatable from this repo as planned.",
    "evidence": "Current OpenTofu evidence shows only Debian 12 LXC template download variables/resources; the plan asks for a Debian 13 Proxmox QEMU VM via cloud-init but does not require a concrete image/template source, template ID, or prerequisite validation.",
    "required_fix": "Add an explicit Debian 13 QEMU image/template contract: variables, scaffold defaults/placeholders, validation, and a fail-fast check or documented operator prerequisite before writing VM HCL.",
    "confidence": "medium"
  },
  {
    "category": "substantive defect",
    "severity": "medium",
    "severity_rationale": "Readiness criteria can pass while Onramp deployment still fails at first compose run.",
    "evidence": "Minimum readiness lists SSH reachability and 'podman --version'; T5 only verifies a deployment directory and version output, not podman info, compose config execution, user socket availability, linger, or a non-secret container smoke test.",
    "required_fix": "Require readiness checks for podman info, compose provider execution, socket/service state if used, permissions on the deployment directory, and a harmless hello-world or dry-run compose validation under the Onramp user.",
    "confidence": "high"
  },
  {
    "category": "process defect",
    "severity": "medium",
    "severity_rationale": "The evidence contract can accidentally persist private topology in tracked spec files during validation.",
    "evidence": "Plan stores sanitized JSONL under .specs and asks for onramp-host address/hostname outputs and validation summaries; commands may inspect values-derived inventory without a required redaction schema for hostnames/IPs.",
    "required_fix": "Define allowed evidence fields and redaction rules for onramp_host address, hostname, inventory, SSH targets, and Onramp summaries; require placeholders in tracked evidence and keep private run logs out of the repo.",
    "confidence": "medium"
  }
]

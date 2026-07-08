[
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "The stated user outcome is a Hermes-usable SearXNG backend, but the plan explicitly excludes deploying SearXNG, modifying onramp-vNext, wiring the Hermes plugin, and running plan/apply. Completion can pass while no backend exists.",
    "evidence": "Objective says make a concrete runtime path and Hermes consumes the endpoint; Out of scope excludes live deployment, onramp-vNext mutation, and Hermes plugin implementation; Success Criteria only require docs/scaffold checks for HERMES_WEB_SEARXNG_URL.",
    "required_fix": "Either rename/re-scope this as onramp-host substrate only, or add a separately approved minimal path that actually produces and smoke-tests a SearXNG URL consumable by Hermes.",
    "confidence": "high"
  },
  {
    "category": "low-value/theater",
    "severity": "medium",
    "severity_rationale": "The plan builds a generic VM platform before proving the smallest search-backend path. That front-loads OpenTofu VM, migrations, inventory, and Podman readiness work for one plugin backend.",
    "evidence": "MVP includes service selection, VM variables/resources/outputs, scaffold migrations, Ansible inventory, Podman role, and docs. Existing Hermes role already installs docker.io and Docker Compose, while the plan provides no comparative spike proving a new VM is necessary now.",
    "required_fix": "Add a decision gate: first validate an existing Onramp target or disposable Hermes-local/container smoke backend; only proceed to permanent onramp_host if that is insufficient.",
    "confidence": "medium"
  },
  {
    "category": "substantive defect",
    "severity": "medium",
    "severity_rationale": "The handoff may be non-actionable because it is authored only in homelab-infra while Onramp owns the service definition and conventions needed to run SearXNG.",
    "evidence": "Constraints forbid mutating onramp-vNext without approval; T6 creates docs/onramp-searxng-handoff.md in this repo. No task requires reading Onramp schemas, commands, health-check conventions, or where service definitions live.",
    "required_fix": "Require a read-only Onramp interface check and produce a handoff in the exact terms/files/commands Onramp expects, or explicitly stop at a generic infra contract.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "medium",
    "severity_rationale": "VM provisioning feasibility is under-specified. The repo currently shows only Proxmox container resources, so a Debian 13 cloud-init VM may require templates/images not represented in variables or acceptance criteria.",
    "evidence": "rg finds proxmox_virtual_environment_container resources for existing services and no proxmox_virtual_environment_vm. The plan says use cloud-init when supported and verify provider shape, but does not require a public-safe VM template/image prerequisite variable or operator setup path.",
    "required_fix": "Make the VM image/template prerequisite explicit, with variables, scaffold placeholders, validation, and a stop condition if the provider/template path is not already available.",
    "confidence": "medium"
  },
  {
    "category": "process defect",
    "severity": "low",
    "severity_rationale": "The JSONL evidence ledger and validator waves add process mass without reducing the key product risk: no SearXNG endpoint exists at completion.",
    "evidence": "T0 creates validation.jsonl and multiple V/F gates maintain sanitized evidence, while the actionable deliverables are ordinary repo changes validated by targeted commands and just validate.",
    "required_fix": "Collapse evidence requirements to the plan checklist plus final validation summary; spend the saved effort on an executable smoke test or Onramp handoff verification.",
    "confidence": "medium"
  }
]

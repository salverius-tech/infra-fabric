[
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "The new QEMU VM can validate syntactically but fail to boot or even plan if no cloud image/template source exists.",
    "evidence": "Plan requires a Debian 13 Proxmox QEMU VM with cloud-init (plan.md:55,75) and lists knobs for VMID/disk/network only (plan.md:80). Existing infra only downloads LXC templates via proxmox_download_file.debian_12_lxc_template (infra/opentofu/main.tf:1,70); no VM image/template pattern exists.",
    "required_fix": "Make the VM boot source explicit: clone template ID/name or cloud image file_id/download/upload, cloud-init datastore requirements, and scaffold variables. Add acceptance checks for those exact inputs.",
    "confidence": "high"
  },
  {
    "category": "process defect",
    "severity": "medium",
    "severity_rationale": "The plan's stated validation cannot prove provider/API feasibility before source completion, leaving failures for a later live-deployment cycle.",
    "evidence": "The plan forbids just plan during this work (plan.md:64,353,376) and relies on just validate (plan.md:60,235,257,344). Provider docs are only recorded as consulted (plan.md:207-208), while feasibility fallback is deferred to execution discovery (plan.md:382).",
    "required_fix": "Add a non-mutating provider-feasibility gate before archive: exact provider-version schema evidence plus either a reviewed no-apply plan with explicit approval or a documented blocked status requiring image/template prerequisites before implementation is marked complete.",
    "confidence": "medium"
  },
  {
    "category": "substantive defect",
    "severity": "medium",
    "severity_rationale": "A duplicate VMID or IP in private tfvars can break provisioning or create LAN conflicts, and the plan does not require a cross-service safety check.",
    "evidence": "The plan adds onramp-host VMID and static IPv4 inputs (plan.md:80,234) but only requires per-field validation for VMID/IP formats (plan.md:234-235). Existing enabled services already have VMIDs/IPs, so onramp_host must be checked against them, not just parsed.",
    "required_fix": "Add validation in the tfvars/inventory/settings tooling that checks onramp_host VMID and non-DHCP address are unique against all other service VMIDs and addresses before plan/apply; include scaffold and migration tests.",
    "confidence": "medium"
  }
]

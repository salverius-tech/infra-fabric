---
reviewer: security-reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: Host-key replacement can silently redirect root Ansible to the wrong LXC. Evidence: plan allows known_hosts entries to be \"refreshed\" and says strict checking blocks until known_hosts is refreshed, but defines no trusted source for expected host keys or changed-key investigation criteria."
  required_fix: "Define host-key trust source and workflow: fetch expected keys through an authenticated Proxmox/LXC boundary or preseeded inventory, compare fingerprints, fail closed on changed keys, and require explicit operator approval before replacing an existing trusted key."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: Non-destructive classification is inaccurate; known_hosts refresh and direct root/become probes mutate local trust state and may touch live hosts. Evidence: manual approval is \"not required\" for direct probes, while Automation Plan includes known-hosts refresh with sanitized changed status."
  required_fix: "Treat trust-store changes as controlled mutations: use a repo/private scoped UserKnownHostsFile, back it up, show redacted diff/status, and require an explicit gate for replacing existing keys. Keep probes read-only and fail if they would modify service state."
- severity: high
  category: "substantive defect"
  confidence: medium
  evidence: "severity_rationale: The reusable bootstrap handoff could become a Proxmox backdoor that enables root SSH or installs Python across services without a hard safety contract. Evidence: plan requires \"minimal direct-management bootstrap\" but does not enumerate allowed commands, files, services, or approval conditions."
  required_fix: "Specify a strict allowlist for direct_access_ready: readiness checks, host-key collection, Python presence check/install if explicitly approved, and SSH/become probe only. Ban firewall/root-SSH changes by default, require approval for bootstrap mutations, and add tests enforcing the allowlist."
- severity: medium
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: Converting service management to direct root SSH increases key blast radius across all LXCs. Evidence: plan records current effective direct user is root and defers non-root operator users; success criteria accept \"connect as root by design\" without compensating controls."
  required_fix: "Add compensating controls for root direct access: scoped deployment key, service-specific inventory vars, no agent forwarding, restricted known_hosts, sudo/become policy documentation, and an explicit issue/deferral for migrating to non-root users with acceptance criteria."
- severity: medium
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: Evidence redaction can miss private data, causing endpoint or token leakage into archived artifacts. Evidence: T8 only greps for \"192.168\", one local string, \".internal\", and \".local\"; it misses 10/8, 172.16/12, IPv6, real public domains, hostnames, usernames, and token-like strings."
  required_fix: "Replace blacklist grep with sanitizer tests using allowlisted output fields plus deny patterns for all RFC1918/link-local/IPv6 literals, FQDNs from values/settings, usernames, SSH fingerprints where disallowed, and token/password/key-shaped strings."

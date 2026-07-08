---
reviewer: security-reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: Migrating every service to direct SSH with the default root user can broaden high-impact remote admin access. Evidence: plan defers \"Creating new non-root operator users\" and says it uses existing direct Ansible SSH users; infra/ansible/inventory/tfvars.py sets DEFAULT_ANSIBLE_USER = \"root\" for services without a tf_user override."
  required_fix: "Add a security gate before Wave 2: prove direct SSH uses dedicated least-privilege deploy users with sudo, or explicitly verify root SSH was already enabled, key-only, LAN/firewall-limited, and not broadened by this migration. Block rather than enabling root SSH ad hoc."
- severity: medium
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: The plan can pass connectivity while live direct roles fail at privilege escalation, causing partial service reconfiguration. Evidence: T1 uses `ansible ... -m ping` only; T3 requires direct service plays with `become: true`; syntax-check does not validate sudo/become behavior."
  required_fix: "Replace/augment ping with a non-mutating become probe for each enabled service, e.g. `ansible <group> -b -m command -a 'id -u'` expecting root, using approved secret handling. Make failure a Wave 1 blocker."
- severity: medium
  category: "substantive defect"
  confidence: medium
  evidence: "severity_rationale: Secret files may move from Proxmox staging to service-host staging without an explicit no-tempfile/mode contract. Evidence: existing roles stage env/config secrets under `/tmp/*.{{ vmid }}` with `no_log`; plan only says convert to direct modules and preserve no_log, while tests mainly cover existing names and Caddy validation."
  required_fix: "Require direct templates/copies for secret-bearing files to final paths with explicit owner/group/mode and no_log. Add regression checks for env/app.ini/runner config/Caddy env modes and no `/tmp` staging of secret templates on service hosts."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: Disabled services can cause false failures or unsafe pressure to enable access. Evidence: commands loop unconditionally over `technitium forgejo forgejo_runner infisical hermes tailscale_client onramp_host`; prose says disabled groups are skipped by settings, but the shell loop exits on absent inventory groups."
  required_fix: "Generate the connectivity/syntax target list from `settings.local.json`/service registry or first query inventory groups and skip absent disabled groups explicitly. Require the command to print sanitized `checked/skipped` groups without leaking endpoints."
- severity: low
  category: "process defect"
  confidence: medium
  evidence: "severity_rationale: Validation evidence can leak private topology during failures. Evidence: the plan requires `ansible-inventory --graph` and direct SSH ping outputs using private `values`; Telemetry says not to record private IPs/domains but does not require redaction around command output or evidence artifacts."
  required_fix: "Add a redaction step/format for saved evidence: record only group names, pass/fail, and sanitized error class. Do not persist raw ansible failure lines, hostnames, IPs, SSH banners, or inventory-derived endpoints under `.specs`."

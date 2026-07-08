- category: false positive
  severity: high
  severity_rationale: "The plan can accept an always-on VM resource even though live plan/apply is out of scope, so the defect may not surface before archive."
  evidence: "plan.md:232-235 verifies optional OpenTofu behavior with only `rg -n 'onramp_host_enabled|proxmox_virtual_environment_vm|onramp_host'`; that does not prove the VM resource is gated by enabled_services or disabled by default."
  required_fix: "Require a deterministic disabled/enabled check, e.g. HCL/unit test or `tofu plan -refresh=false` only if explicitly approved; otherwise static parse asserting count/for_each depends on local.onramp_host_enabled."
  confidence: high

- category: false positive
  severity: high
  severity_rationale: "A grep for Podman strings can pass with comments or nonfunctional tasks while archive claims Podman readiness."
  evidence: "plan.md:90-94 requires Podman/Compose/readiness; plan.md:276-279 verifies with `rg -n 'podman|podman-compose|podman compose|containers.conf'` plus inspection/lint, which does not execute or assert `podman --version`."
  required_fix: "Add concrete Ansible acceptance: syntax plus role tests or check-mode assertions for package names, deployment dir ownership, command task registration, failed_when, and no_log/secrets handling; mark live SSH readiness unproven and not an archive condition."
  confidence: high

- category: process defect
  severity: medium
  severity_rationale: "The specified public-safety command depends on an evidence file that no task creates, so validation can fail late or be silently skipped."
  evidence: "plan.md:255 and 340 require `--tracked-files .specs/.../public-safety-files.txt`; only validation.jsonl is initialized in T0 at plan.md:203-204."
  required_fix: "Add an explicit task to generate the planned-file list from all touched tracked/untracked paths before any public-safety checks, and require the check to fail if the list is missing or incomplete."
  confidence: high

- category: process defect
  severity: medium
  severity_rationale: "Archive decisions depend on unverifiable negative claims about commands not run and mutations not made."
  evidence: "plan.md:210-214 says confirm no apply/import/destroy/live mutation; plan.md:356-359 allows archive after validations; evidence schema at plan.md:363-366 records only validation commands, not forbidden-command audit or external mutation proof."
  required_fix: "Define archive evidence: sanitized command log from executor, git status before/after, and explicit blocked status for any live checks. Remove claims that /do-it can prove no external mutation without such evidence."
  confidence: medium

- category: substantive defect
  severity: medium
  severity_rationale: "Existing test coverage is optional in the plan, allowing settings/inventory/migration regressions to pass by string checks."
  evidence: "plan.md:183 says `tests if present`; tests/test_settings.py exists and covers service validation/playbook mapping. T4 allows `targeted tests or rg` at plan.md:264-266, and T3 migration tests are conditional at plan.md:245-246."
  required_fix: "Make unit tests mandatory for onramp_host settings acceptance, playbook mapping, all-playbooks inclusion, tfvars-derived inventory, and migration idempotence; grep may supplement but not replace tests."
  confidence: high

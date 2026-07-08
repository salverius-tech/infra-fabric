## Finding 1
category: substantive defect
severity: medium
severity_rationale: The helper is intended to gate archive/deployment-independent validation; ambiguous exit statuses can let broken services archive as success.
evidence: plan.md:256 only requires `--help` exits 0. Subcommand pass/fail text appears throughout (e.g. plan.md:267-280, plan.md:300-327), but no contract defines exit codes for partial failures, skipped enabled services, redaction violations, documented check-mode exceptions, invalid settings, or missing inventory.
required_fix: Add a CLI contract: exit 0 only when all required checks pass; nonzero for enabled-service failure/redaction breach/parse error; distinct code or machine-readable status for documented skips/exceptions. Test each subcommand’s exit behavior.
confidence: high

## Finding 2
category: substantive defect
severity: medium
severity_rationale: Redaction is a safety boundary for private infrastructure evidence; the planned test can miss common leaks and can also reject allowed examples.
evidence: plan.md:404 tests only `192.168.`, `ilude`, `.internal`, and `.local` against `settings.example.json` output. It misses 10/8, 172.16/12, public real domains, host keys, usernames, API URLs, tokens, and Ansible stderr. It also treats `.internal` as forbidden although AGENTS permits `example.internal` placeholders and settings.example.json contains `git.example.internal`.
required_fix: Add fixture-based redaction tests with representative private inventory, stderr, host-key, token, and domain values; whitelist documented placeholders; run redaction checks for private-backed subcommands too.
confidence: high

## Finding 3
category: process defect
severity: medium
severity_rationale: The host-key command mutates trust state, but the plan does not require isolation or dry-run tests, so tests can be order-dependent and live runs can silently change operator state.
evidence: plan.md:271-272 allows `known-hosts` to refresh entries. No acceptance criterion requires `--known-hosts-file`, temporary HOME, dry-run mode, atomic writes, changed-key failure semantics, or unit tests using a temporary known_hosts file.
required_fix: Specify isolated known_hosts handling: explicit path option, temp path in tests, atomic update, changed-key classification as failure unless approved, and a no-mutation `--check`/plan mode for public/example validation.
confidence: medium

## Finding 4
category: substantive defect
severity: medium
severity_rationale: Public example commands are required as proof, but the plan leaves several subcommands dependent on private inventory or defaults, making the helper hard to verify in clean checkouts.
evidence: T2 public checks cover only `inventory` and `bootstrap-plan` with `settings.example.json` (plan.md:229,237). Later required commands such as `policy --redacted` omit `--settings` (plan.md:495), while syntax/check-mode require `values/...` private inventory (plan.md:480). There is no required fixture inventory for public execution of parsing paths.
required_fix: Add committed fixture inventory/settings inputs and require every non-live subcommand to run against them. Make live-only subcommands fail clearly without private inputs and document that contract.
confidence: medium

## Finding 5
category: duplicate
severity: low
severity_rationale: Conflicting validation text can make implementers satisfy the wrong command and skip the actual policy gate.
evidence: The validation contract has duplicate item “6. Run policy checks”. The first copy runs `bootstrap-plan` and describes sequencing (plan.md:489-492); the second runs `policy` plus `pve-boundary` (plan.md:494-496).
required_fix: Delete the duplicate bootstrap-plan policy item or renumber it under bootstrap validation. Keep one policy gate with the actual `policy` and `pve-boundary` commands.
confidence: high

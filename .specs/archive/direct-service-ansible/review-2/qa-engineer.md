# QA Review: Verification Realism / False Positives

## Finding 1
category: false positive
severity: high
severity_rationale: Core acceptance can pass if the new helper reports planned structure rather than executing Ansible against direct hosts.
evidence: Many pass criteria use `scripts/check-direct-service-ansible.py ... --redacted` summaries for inventory/playbooks/bootstrap/policy/dryness, but the plan does not require independent evidence that the helper invokes `ansible-playbook`/`ansible` for connectivity, become, syntax, or check-mode instead of returning sanitized self-assessments.
required_fix: Define helper contract per subcommand: exact Ansible command/API invoked, exit-code propagation, required raw fields consumed before redaction, and tests that force failures when inventory hosts, become, or playbook syntax are broken.
confidence: high

## Finding 2
category: false positive
severity: high
severity_rationale: Check-mode evidence may be accepted while mutating behavior remains unproved or exempted.
evidence: T4 and validation allow “check-mode pass or documented task-level exceptions.” For service roles with commands, registration, Caddy reloads, systemd changes, and secret file writes, broad exceptions could leave the riskiest behavior untested while still satisfying the gate.
required_fix: Require an exception budget/list with task path, reason, compensating evidence, and an idempotence proof. Fail archive if any direct service role has unbounded check-mode skips or if exempted tasks lack changed_when/creates/removes or a dry-run substitute.
confidence: high

## Finding 3
category: process defect
severity: medium
severity_rationale: The plan contains contradictory duplicate validation numbering and one duplicate heading with different commands, making gate completion ambiguous.
evidence: “Required automated validation” has item 5, then item 6 for bootstrap-plan only, then another item 6 for policy checks. The first “Run policy checks” entry actually runs `bootstrap-plan`, duplicating item 5 rather than policy.
required_fix: Renumber the validation contract and remove the duplicate/mislabeled policy item. Ensure each final gate maps to one unique command set and one checkbox/evidence record.
confidence: high

## Finding 4
category: substantive defect
severity: high
severity_rationale: Host-key refresh could silently bless changed keys, defeating the safety goal while producing sanitized success.
evidence: T1 requires known_hosts entries “or are refreshed with sanitized changed status,” but only says investigate changed host keys on fail. A helper could refresh a changed key and return changed/pass without proving the old key was absent vs conflicting.
required_fix: Split known-hosts states into absent-added, unchanged-verified, changed-conflict-blocked. Require changed/conflicting keys to fail unless an explicit approval flag is supplied, and record only sanitized conflict status.
confidence: high

## Finding 5
category: low-value/theater
severity: medium
severity_rationale: Redaction tests check a few literals and can miss real private data while giving false confidence.
evidence: T8 verifies redaction with `rg -n "192\.168\.|ilude|\.internal|\.local"` against example settings. That does not cover RFC1918 ranges beyond 192.168, public real domains, hostnames, usernames, IPv6, SSH key material, tokens, or output from private settings.
required_fix: Add a reusable public-safety/redaction test fixture with injected fake private IPs/domains/tokens/keys/usernames and assert none appear after redaction. Run it against every helper subcommand that emits evidence.
confidence: high

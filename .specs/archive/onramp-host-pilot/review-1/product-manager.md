- category: duplicate
  severity: medium
  severity_rationale: Adds a second contract artifact where a smaller PRD decision update likely suffices.
  evidence: "Existing docs/hermes-operator-pilot-prd.md already covers the key boundary: Onramp/app-services host for general Docker services, Hermes plugin backend classification, repo workflow safety, and SearXNG decision recording. Plan still creates docs/onramp-app-platform-contract.md plus README/docs navigation, increasing maintenance surface for a docs-only MVP. Severity medium because duplicated product truth can drift across repos."
  required_fix: "Collapse MVP to one PRD decision section or ADR unless a distinct contract has non-overlapping consumers/fields; otherwise defer separate contract/navigation."
  confidence: high
- category: substantive defect
  severity: medium
  severity_rationale: Validation can pass while required content is missing.
  evidence: "Acceptance checks use broad OR regexes, e.g. `rg -n \"Ownership|DNS|Caddy|Secrets|State|Approval|Debian 13|Podman|SearXNG\"`, which exits 0 if any one term appears. Same issue exists for PRD terms. Severity medium because this is the main guardrail for a documentation contract."
  required_fix: "Replace OR grep checks with per-required-term checks or a small script that reports each missing required section/decision."
  confidence: high
- category: low-value/theater
  severity: low
  severity_rationale: Evidence step adds cross-repo ceremony without useful evidence.
  evidence: "Automation plan reads only filenames from `C:/Projects/Personal/onramp-vNext/docs/prd`; filenames cannot validate Onramp ownership, port, Caddy, secrets, or state conventions. It also introduces an absolute local path into an otherwise repo-local docs task. Severity low because it wastes time rather than breaking output."
  required_fix: "Remove this step, make it optional, or read specific public-safe Onramp docs with a fallback when the sibling repo is absent."
  confidence: medium
- category: low-value/theater
  severity: low
  severity_rationale: Evidence/audit schema is disproportionate to a small docs edit.
  evidence: "The plan defers runtime telemetry but requires JSONL evidence records with episode/phase/task/archive fields for every validation record. For a docs-only MVP validated by git diff, public-safety, and just validate, this adds process overhead without changing product quality."
  required_fix: "Use a brief sanitized validation summary in the plan checklist; defer JSONL evidence schema to a workflow-telemetry project."
  confidence: high

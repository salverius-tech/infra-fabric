---
reviewer: reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: high because T1 depends on an untracked PRD draft that may not exist in a fresh /do-it checkout. Evidence: plan Constraints says current uncommitted state includes untracked docs/hermes-operator-pilot-prd.md; T1 says update that path, not create it; preflight only tests for existence in an optional input-review operation."
  required_fix: "Make the PRD input durable or self-contained: either add a tracked starter file requirement, change T1 to create the PRD when absent, or embed the required source decisions in the plan so /do-it does not need hidden untracked context."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: medium because acceptance checks can pass while required content is absent. Evidence: T2 verify uses one rg alternation: \"Ownership|DNS|Caddy|Secrets|State|Approval|Debian 13|Podman|SearXNG\". rg exits 0 if any term matches, despite Pass claiming all required topic matches."
  required_fix: "Replace alternation checks with explicit per-topic checks or a small script that verifies every required heading/topic and fails with missing-topic names."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: medium because T1 verification proves keyword presence, not the required decision semantics. Evidence: T1 AC1 rg checks \"homelab-infra|onramp-vNext|Hermes|SearXNG|Debian 13|Podman\"; any single term can satisfy exit 0 and does not prove selected architecture, ownership split, or pilot classification."
  required_fix: "Specify concrete required statements/headings and verify each separately, including selected option 3, ownership split, SearXNG classification, Debian 13 VM default, and Podman-in-LXC experimental status."
- severity: medium
  category: "process defect"
  confidence: medium
  evidence: "severity_rationale: medium because optional docs/README.md can make documented validation brittle for fresh sessions. Evidence: T3 says docs/README.md is optional, but verify command passes README.md docs/README.md directly to rg; Automation Plan also lists git diff --check with docs/README.md as a path."
  required_fix: "Use commands that tolerate absence of optional docs/README.md, or make docs/README.md mandatory. Example: build an existing-file list before rg/diff, then verify README-only navigation is sufficient when docs/README.md is absent."
- severity: medium
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: medium because a fresh /do-it may not have the sibling repo/path and the plan gives no fallback. Evidence: Automation Plan requires reading C:/Projects/Personal/onramp-vNext/docs/prd/*.md, while Handoff says this plan must not mutate that repo but may read it. No prerequisite, skip rule, or alternate embedded context is defined."
  required_fix: "Declare the sibling repo as optional with a safe skip condition, or include the necessary Onramp context in this plan so execution does not depend on local machine-specific paths."

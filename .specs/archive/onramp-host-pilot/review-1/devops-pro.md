[
  {
    "category": "process defect",
    "severity": "high",
    "severity_rationale": "A docs-only plan can be blocked by private state/bootstrap rather than by document quality, especially in a brand-new session.",
    "evidence": "Plan requires final `just validate`; justfile defines `validate: validate-public validate-values`, and `validate-values` runs `scripts/validate-values.sh`, which requires `values/dns-records.local.json`, private inventory, and workspace preflight with `--require-values`. The stated repair path `just setup` can still require a private values remote or operator-edited private files.",
    "required_fix": "Add an explicit preflight/precondition for existing valid `values/` and settings, with a blocked outcome if absent, or change this docs-only MVP to a public-source validation path plus clearly deferred private-values validation.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "medium",
    "severity_rationale": "The required acceptance checks can pass while required contract content is missing.",
    "evidence": "T2 verifies `rg -n \"Ownership|DNS|Caddy|Secrets|State|Approval|Debian 13|Podman|SearXNG\" docs/onramp-app-platform-contract.md`; `rg` exits 0 on any one alternative, not all topics. T1/T3 use similar broad alternation checks, so a stub mentioning one keyword can satisfy the gate.",
    "required_fix": "Replace broad `rg` alternations with a small deterministic checker or separate assertions for each required heading/topic and for the OpenTofu boundary sentence.",
    "confidence": "high"
  },
  {
    "category": "process defect",
    "severity": "medium",
    "severity_rationale": "A fresh executor can silently skip required cross-repo context and still produce plausible evidence.",
    "evidence": "Automation Plan hard-codes `C:/Projects/Personal/onramp-vNext/docs/prd` and only iterates `root.glob('*.md')`. If the sibling repo is absent, differently located, or running inside the tooling container, the command prints an empty list without failing, making the evidence ambiguous.",
    "required_fix": "Make Onramp context optional and non-blocking, or add `test -d`/explicit failure with a portable configured path. Record whether context was read, absent, or deferred.",
    "confidence": "high"
  },
  {
    "category": "process defect",
    "severity": "medium",
    "severity_rationale": "The archive trail is optional where the plan later depends on it for resumability and review.",
    "evidence": "Telemetry says `/do-it` `should` record sanitized evidence in terminal output or evidence dir, while checklist entries start with `Evidence: --`. Terminal-only output is not durable across a new session, and JSONL evidence is described as `should` rather than required.",
    "required_fix": "Require a specific `.specs/onramp-host-pilot/evidence/validation.jsonl` artifact for every gate, including command, exit status, sanitized summary, and checklist evidence path updates before archiving.",
    "confidence": "medium"
  }
]

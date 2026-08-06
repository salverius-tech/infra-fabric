# Explicit source questions and decisions

Only list items under exact authoritative **Open questions** or **Decisions that must not be guessed** headings belong here. Historical approvals, headings, instructions, acceptance language, and generic decision wording remain in their source packages.

## Canonical unresolved questions

- `recon-open-question-ddd39b03e3334cf5` — **durable local-state single-controller policy versus remote locking backend;**
  Source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:161`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-6ee9d06283feea00` — **final ownership/retirement trigger for temporary `searxng_onramp`;**
  Source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:162`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-95333eb886ffe2b4` — **Hermes operator local apply versus Forgejo workflow semantics;**
  Source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:163`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-be64460ced4c9bd3` — **required durable audit trail for operator actions;**
  Source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:164`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-eb86f57df8987ea9` — **compatibility-window end and legacy-removal authorization;**
  Source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:165`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-0a0b20a2c71d09ed` — **provider/live/recovery environments used for final acceptance**
  Source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:166`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-af01bfba1bd4d97b` — **Which Hermes actions are in scope for the first pilot: status only, validate, plan, apply, private values commits, or Forgejo workflow monitoring?**
  Source: `docs/hermes-operator-pilot-prd.md:156`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-f41d01cf73b19daf` — **Which onramp-host provisioning shape should a future infrastructure plan expose to `onramp-vNext`?**
  Source: `docs/hermes-operator-pilot-prd.md:159`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-f5c52449e956928e` — **How should Hermes safely support edits to `values/` without exposing private values in transcripts or summaries?**
  Source: `docs/hermes-operator-pilot-prd.md:160`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`
- `recon-open-question-17f05123e73d1bb4` — **What recovery path should be documented when Hermes is unavailable but infrastructure needs maintenance?**
  Source: `docs/hermes-operator-pilot-prd.md:161`; owner: `unassigned`; options: `[]`; trigger: ``; deadline: ``; dependency IDs: `[]`

## Duplicate source provenance

- `recon-open-question-3019c450883c7477` duplicates canonical `recon-open-question-95333eb886ffe2b4`: Should Hermes trigger `just apply` locally, trigger Forgejo Actions, or support both with different approval paths?
  Source: `docs/hermes-operator-pilot-prd.md:157`
- `recon-open-question-d70459d1a290222d` duplicates canonical `recon-open-question-be64460ced4c9bd3`: What is the minimum audit trail required for an operator-approved apply?
  Source: `docs/hermes-operator-pilot-prd.md:158`

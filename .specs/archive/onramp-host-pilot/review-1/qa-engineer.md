- category: false positive
  severity: high
  severity_rationale: 'A shallow edit can pass core contract checks while omitting most required content.'
  evidence: 'T2 AC1 uses `rg -n "Ownership|DNS|Caddy|Secrets|State|Approval|Debian 13|Podman|SearXNG" ...`; regex alternation requires only one term, despite Pass saying all topics. Same pattern exists in T1, T3, and Success Criteria.'
  required_fix: 'Replace OR-only rg checks with per-term assertions or a small validation script that fails for each missing required topic/section.'
  confidence: high
- category: false positive
  severity: high
  severity_rationale: 'Boundary validation can pass when the required prohibition is absent or contradicted.'
  evidence: 'T2 AC2 `rg -n "not.*OpenTofu|Onramp.*owns|app services"` passes on generic app services text and does not prove not managed through OpenTofu by default.'
  required_fix: 'Use a targeted phrase/section check for the exact OpenTofu default-management prohibition and require surrounding context review in V1 evidence.'
  confidence: high
- category: substantive defect
  severity: medium
  severity_rationale: 'Cross-repo coherence is claimed but not actually verified before accepting the contract.'
  evidence: 'Automation reads only filenames from `C:/Projects/Personal/onramp-vNext/docs/prd`; no acceptance criterion compares the new contract to Onramp docs or records what assumptions were imported.'
  required_fix: 'Add an explicit read/summary step for relevant Onramp docs and a validation check that contract terms do not conflict with cited Onramp assumptions.'
  confidence: medium
- category: process defect
  severity: medium
  severity_rationale: 'Evidence requirements are optional enough that unverifiable terminal output can satisfy final gates.'
  evidence: 'Telemetry says evidence may be in terminal output or files, while archive depends on validated gates. There is no required evidence artifact path or schema validation for JSONL records.'
  required_fix: 'Require a sanitized evidence JSONL artifact and add a validation command that checks required records exist for T1/T2/T3/V1/V2/F gates.'
  confidence: medium
- category: false positive
  severity: medium
  severity_rationale: 'Navigation/workflow checks can pass after losing required workflow commands.'
  evidence: 'T3 AC2 uses `rg -n "just validate|just plan|just apply" README.md`; it exits 0 if any one command remains, but Pass requires all workflow commands remain present.'
  required_fix: 'Check each command independently, e.g. three `rg -q` assertions or a script reporting the specific missing workflow command.'
  confidence: high

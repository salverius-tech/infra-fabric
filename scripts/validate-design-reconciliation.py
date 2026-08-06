#!/usr/bin/env python3
"""Generate and fail-closed validate the lossless public reconciliation ledger.

Extraction is deliberately lossless over the declared structural and keyword contract:
every matched tracked-source task, requirement, acceptance criterion, deferral,
blocker, authoritative question, and audit finding remains a ledger record.
Adjudication is conservative and rule-based. Checkboxes/status prose are source claims,
never implementation evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / ".hermes" / "reconciliation"
AUDIT_PATH = ".hermes/plans/2026-08-04-comprehensive-project-audit.md"
PLAN_PATH = ".hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md"
AUDIT_IDS = tuple([f"H{i}" for i in range(1, 13)] + [f"M{i}" for i in range(1, 19)] + [f"L{i}" for i in range(1, 9)])
DISPOSITIONS = frozenset({"implemented-static", "outstanding", "evidence-required", "blocked-external", "superseded", "duplicate"})
EVIDENCE_LEVELS = frozenset({"source", "static", "provider", "live", "recovery"})
CHECKBOX = re.compile(r"^\s*- \[([ xX])\]\s+(.+?)\s*$")
AUDIT_HEADING = re.compile(r"^###\s+((?:H|M|L)\d+)\.\s+(.+?)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+?)\s*$")
# This is the restored HEAD extraction contract.  It intentionally captures explicit
# backlog language and checkbox tasks, rather than widening extraction heuristically.
EXPLICIT = re.compile(r"\b(remaining|partial|deferred|blocked|outstanding|open question|open questions|decision|required verification|acceptance criteria|success criteria|definition of done|exit gate)\b", re.I)

# An unresolved choice is authoritative only when a current design/tracker places a
# list item under one of these exact headings.  This deliberately does not infer a
# decision from an ordinary use of “decision”, a historical decision log, or an
# instruction to create a register.
OPEN_QUESTION_HEADINGS = frozenset({"open questions", "decisions that must not be guessed"})
OPEN_QUESTION_AUTHORITIES = frozenset({"working design", "implementation tracker"})
OPEN_QUESTION_LABEL = re.compile(r"^\s*(Open questions|Decisions that must not be guessed):\s*$", re.I)
# These are the only cross-document semantic equivalences currently asserted by
# source.  They are intentionally a closed mapping, rather than fuzzy matching.
DECISION_SEMANTIC_KEYS = {
    "Should Hermes trigger `just apply` locally, trigger Forgejo Actions, or support both with different approval paths?": "hermes-apply-semantics",
    "Hermes operator local apply versus Forgejo workflow semantics;": "hermes-apply-semantics",
    "What is the minimum audit trail required for an operator-approved apply?": "operator-apply-audit-trail",
    "required durable audit trail for operator actions;": "operator-apply-audit-trail",
}

# Explicit package rules are source-location/heading rules, never keyword inference.
# Rules run in order; audit IDs are a separate explicit authoritative mapping.
PACKAGE_RULES = (
    ("R1", ("service-state", "backup", "restore")),
    ("R2", ("fresh-site", "scaffold", "validate-values", "workspace-preflight")),
    ("S1", ("canonical service", "stateful ownership", "site.yaml authority")),
    ("S2", ("secret contract", "secret delivery", "secret namespace", "sops")),
    ("S3", ("plan/apply", "teardown", "state protection", "execution snapshot")),
    ("O1", ("hermes control", "hermes_control", "hermes operator")),
    ("O2", ("ansible scheduling", "shared host", "apply-ansible-services")),
    ("O3", ("supply chain", "image integrity", "immutable runtime")),
    ("Q1", ("ansible convergence", "check mode", "idempotence", "tags")),
    ("Q2", ("projection", "opentofu module", "compatibility adapter")),
    ("Q3", ("update workflow", "update parity")),
)
AUDIT_PACKAGE = {
    "H1":"S1", "H2":"O3", "H3":"O2", "H4":"R1", "H5":"R2", "H6":"S1", "H7":"S2", "H8":"S3", "H9":"O1", "H10":"S2", "H11":"O3", "H12":"S3",
    "M1":"O2", "M2":"R2", "M3":"S3", "M4":"Q1", "M5":"Q1", "M6":"Q2", "M7":"Q2", "M8":"O3", "M9":"Q3", "M10":"S2", "M11":"S2", "M12":"R1", "M13":"S2", "M14":"Q1", "M15":"S1", "M16":"S2", "M17":"CI", "M18":"O1",
    "L1":"R1", "L2":"R2", "L3":"O3", "L4":"CI", "L5":"R2", "L6":"DOCS", "L7":"Q2", "L8":"DOCS",
}
PACKAGES = [
 {"id":"R1","title":"Canonical service-state recovery correctness","priority":"P0","depends_on":["R2"],"files":["scripts/service-state.sh","infra/ansible/playbooks/service-state-backup.yml","infra/ansible/playbooks/service-state-restore.yml","docs/service-state-backup.md","tests/test_service_state.py"],"contracts":["catalog-derived state-capable selection","paired inventory/vars projection","restart failure propagation"],"criteria":["source claims are cited","focused static verification passes"],"safety":["no real restore during reconciliation"],"commands":["python3 -m unittest -v tests/test_service_state.py"]},
 {"id":"R2","title":"Fresh-site validation and scaffold correctness","priority":"P0","depends_on":[],"files":["scripts/validate-values.sh","scripts/workspace-preflight.py","scripts/values.sh","scaffold/README.md","tests/test_documentation_contract.py"],"contracts":["provider-independent render/verify","atomic private projection handoff","installed-scaffold link validity"],"criteria":["source claims are cited","fresh static fixture verifies"],"safety":["no private values or provider contact"],"commands":["python3 -m unittest -v tests/test_documentation_contract.py"]},
 {"id":"S1","title":"Canonical service and stateful ownership","priority":"P0","depends_on":["R2"],"files":["scripts/tfplan-metadata.py","scripts/values_context.py","infra/opentofu/services.tf","tests/test_tfplan_metadata.py"],"contracts":["site.yaml is canonical selection","stateful retain/destroy acknowledgement","no legacy double gate"],"criteria":["source claims are cited","canonical state tests pass"],"safety":["no provider plan"],"commands":["python3 -m unittest -v tests/test_tfplan_metadata.py","tofu fmt -check -recursive"]},
 {"id":"S2","title":"Unified secret contract and preflight","priority":"P0","depends_on":["R2"],"files":["infra/services.json","scripts/secret_delivery.py","scripts/workspace-preflight.py","scripts/secret_bundle_migration.py","tests/test_secret_delivery.py"],"contracts":["one provider/operator namespace","complete pre-mutation requirements","least-privilege environments"],"criteria":["metadata-only tests pass","no secret values inspected"],"safety":["never read or create private values"],"commands":["python3 -m unittest -v tests/test_secret_delivery.py","python3 -m unittest -v tests/test_workspace_preflight.py"]},
 {"id":"S3","title":"Plan/apply/teardown integrity and state protection","priority":"P0","depends_on":["S1","S2"],"files":["scripts/apply-infra.sh","scripts/teardown-infra.sh","scripts/tfplan-metadata.py","docs/canonical-teardown.md","tests/test_tfplan_metadata.py"],"contracts":["immutable reviewed snapshot","site-scoped lock","metadata-bound teardown"],"criteria":["pre-mutation probes fail closed","recovery evidence separately required"],"safety":["no plan/apply/teardown"],"commands":["python3 -m unittest -v tests/test_tfplan_metadata.py","bash -n scripts/apply-infra.sh scripts/teardown-infra.sh"]},
 {"id":"O1","title":"Hermes Control readiness and role contracts","priority":"P1","depends_on":["S2"],"files":["infra/ansible/roles/hermes/tasks/main.yml","infra/ansible/roles/hermes_control/meta/argument_specs.yml","tests/test_hermes_control_role.py"],"contracts":["authenticated readiness header","typed parent/subrole inputs","secret-safe rendering"],"criteria":["role tests pass","live guest acceptance remains external"],"safety":["do not contact guest"],"commands":["python3 -m unittest -v tests/test_hermes_control_role.py"]},
 {"id":"O2","title":"Host-aware Ansible scheduling","priority":"P1","depends_on":["S2"],"files":["scripts/apply-ansible-services.py","tests/test_apply_ansible_services.py"],"contracts":["one service per execution resource","parallelism across distinct hosts","registry-only orchestration"],"criteria":["shared-host ordering tests pass","live convergence remains external"],"safety":["no live orchestration"],"commands":["python3 -m unittest -v tests/test_apply_ansible_services.py"]},
 {"id":"O3","title":"Immutable runtime and image supply chain","priority":"P1","depends_on":["Q3"],"files":["infra/opentofu/modules/debian-vm","infra/ansible/roles/infisical","infra/ansible/roles/sssf","tests/test_tooling_image_integrity.py"],"contracts":["checksummed VM acquisition","digest-pinned images","managed immutable updates"],"criteria":["static integrity tests pass","no-cache build remains external"],"safety":["retain existing verified pins"],"commands":["python3 -m unittest -v tests/test_tooling_image_integrity.py"]},
 {"id":"Q1","title":"Ansible convergence and check mode","priority":"P1","depends_on":["O1","O2"],"files":[".ansible-lint","infra/ansible/roles/host_identity","scripts/check-direct-service-ansible.py","tests/test_ansible_safety.py"],"contracts":["idempotence","host-specific salts","closed tag/check-mode contract"],"criteria":["static safety tests pass","real host second run remains external"],"safety":["do not rotate real credentials"],"commands":["python3 -m unittest -v tests/test_ansible_safety.py"]},
 {"id":"Q2","title":"OpenTofu module and projection contracts","priority":"P1","depends_on":["S1"],"files":["infra/opentofu/modules/debian-vm","infra/opentofu/modules/debian-lxc","scripts/canonical_projections.py","tests/test_canonical_mapping_inventory.py"],"contracts":["module invariants","typed adapters","state address preservation"],"criteria":["mapping tests pass","provider equivalence plan remains external"],"safety":["no state moves"],"commands":["python3 -m unittest -v tests/test_canonical_mapping_inventory.py"]},
 {"id":"Q3","title":"Update workflow parity","priority":"P1","depends_on":[],"files":["scripts/update.py","docs/service-update-policy.md","tests/test_update.py"],"contracts":["canonical repository pins","catalog targets","non-mutating dry run"],"criteria":["update tests pass"],"safety":["dry-run only"],"commands":["python3 -m unittest -v tests/test_update.py"]},
 {"id":"DOCS","title":"Documentation authority and operations","priority":"P2","depends_on":["R1","R2","S1","S3","O1","O2","O3","Q1","Q2","Q3"],"files":["docs/documentation-inventory.json","docs/README.md","docs/service-catalog.md","tests/test_documentation_contract.py"],"contracts":["one authority classification","service operations matrix","validated commands"],"criteria":["historical links retained","documentation tests pass"],"safety":["preserve history and provenance"],"commands":["python3 -m unittest -v tests/test_documentation_contract.py"]},
 {"id":"CI","title":"Tooling, CI, and quality gates","priority":"P2","depends_on":["O3","DOCS"],"files":["tools/Dockerfile","tools/pip-bootstrap.lock","tools/requirements.txt","tools/requirements.lock","tools/python-format-files.txt","scripts/validate-public.sh",".github/workflows/validate.yml"],"contracts":["reproducible tool image","quality gates","named validation stages"],"criteria":["public validation passes","build/advisory evidence external"],"safety":["keep live checks out of public CI"],"commands":["scripts/validate-public.sh"]},
 {"id":"DECISIONS","title":"Explicit operator/product decisions","priority":"P2","depends_on":[],"files":[PLAN_PATH],"contracts":["explicit owner and trigger","no inferred decisions"],"criteria":["decision is recorded before dependent work"],"safety":["do not guess policy"],"commands":["python3 -B scripts/validate-design-reconciliation.py --check"]},
 {"id":"ACCEPTANCE","title":"Separate external acceptance","priority":"P3","depends_on":["R1","R2","S1","S2","S3","O1","O2","O3","Q1","Q2","Q3","DOCS","CI"],"files":["docs/canonical-readiness.md","docs/canonical-teardown.md"],"contracts":["layered provider/live/recovery acceptance","approval per risk boundary"],"criteria":["approved plan, live health, recovery rehearsal evidenced separately"],"safety":["no provider/live/recovery execution"],"commands":["python3 -B scripts/validate-design-reconciliation.py --check"]},
]

# This registry is intentionally package-scoped rather than inferred from checkbox
# wording. A source-complete package must cite both a current production path and a
# focused verification path. It never establishes provider, live, or recovery proof.
PACKAGE_EVIDENCE = {
 "R1":{"production":{"path":"scripts/service-state.sh","lines":"1-80","claim":"Canonical service-state selection and recovery entry point."},"verification":{"path":"tests/test_service_state.py","lines":"1-80","claim":"Focused service-state regression coverage."}},
 "R2":{"production":{"path":"scripts/workspace-preflight.py","lines":"1-80","claim":"Canonical fresh-site preflight and projection handling."},"verification":{"path":"tests/test_workspace_preflight.py","lines":"1-100","claim":"Focused fresh-site preflight regression coverage."}},
 "S1":{"production":{"path":"scripts/tfplan-metadata.py","lines":"1-120","claim":"Canonical plan metadata and stateful selection boundary."},"verification":{"path":"tests/test_tfplan_metadata.py","lines":"1-140","claim":"Focused plan metadata and canonical selection regression coverage."}},
 "S2":{"production":{"path":"scripts/secret_delivery.py","lines":"1-120","claim":"Scoped canonical secret delivery boundary."},"verification":{"path":"tests/test_secret_delivery.py","lines":"1-210","claim":"Focused secret-delivery and least-privilege regression coverage."}},
 "S3":{"production":{"path":"scripts/execution-snapshot.py","lines":"1-120","claim":"Immutable execution snapshot verification boundary."},"verification":{"path":"tests/test_tfplan_metadata.py","lines":"180-300","claim":"Focused immutable plan and execution metadata regression coverage."}},
 "O1":{"production":{"path":"infra/ansible/roles/hermes_control/tasks/main.yml","lines":"1-120","claim":"Hermes Control role readiness and typed contract path."},"verification":{"path":"tests/test_hermes_control_role.py","lines":"1-130","claim":"Focused Hermes Control role regression coverage."}},
 "O2":{"production":{"path":"scripts/apply-ansible-services.py","lines":"84-155","claim":"Execution-resource-aware Ansible scheduling."},"verification":{"path":"tests/test_apply_ansible_services.py","lines":"20-70","claim":"Focused shared-host scheduling regression coverage."}},
 "O3":{"production":{"path":"infra/ansible/tasks/reviewed-artifact-cache.yml","lines":"1-62","claim":"Fail-closed controller checksum verification and versioned staging contract."},"verification":{"path":"tests/test_artifact_projection.py","lines":"1-130","claim":"Typed canonical artifact ownership, catalog projection, and role-input regression coverage."}},
 "Q1":{"production":{"path":"scripts/check-direct-service-ansible.py","lines":"1-120","claim":"Static Ansible convergence contract enforcement."},"verification":{"path":"tests/test_ansible_convergence_contract.py","lines":"1-100","claim":"Focused tags, idempotence, and check-mode regression coverage."}},
 "Q2":{"production":{"path":"infra/opentofu/services.tf","lines":"1-170","claim":"Typed service-runtime and OpenTofu precondition contract."},"verification":{"path":"tests/test_canonical_mapping_inventory.py","lines":"1-100","claim":"Focused mapping and consumer parity regression coverage."}},
 "Q3":{"production":{"path":"scripts/update.py","lines":"1-100","claim":"Catalog-driven non-mutating update workflow."},"verification":{"path":"tests/test_update.py","lines":"1-230","claim":"Focused update dry-run and managed-pin regression coverage."}},
 "DOCS":{"production":{"path":"docs/service-operations.md","lines":"1-70","claim":"Catalog-derived day-two operations guidance."},"verification":{"path":"tests/test_documentation_contract.py","lines":"39-245","claim":"Focused documentation inventory, link, command, and operations-matrix coverage."}},
 "CI":{"production":{"path":"tools/Dockerfile","lines":"1-60","claim":"Hash-locked tooling image contract."},"verification":{"path":"tests/test_phase7_tooling_contract.py","lines":"1-80","claim":"Focused tooling reproducibility regression coverage."}},
}

def git_files() -> list[str]:
    return subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()

def source_paths() -> list[str]:
    generated = {"docs/design-implementation-backlog.md"}
    return sorted(p for p in git_files() if p not in generated and not p.startswith(".hermes/reconciliation/") and (p.endswith(".md") or p in {"AGENTS.md", "docs/documentation-inventory.json"}))

def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".")

def stable_id(relative: str, kind: str, summary: str, occurrence: int) -> str:
    return "recon-{}-{}".format(kind, hashlib.sha256(f"{relative}|{kind}|{normalized(summary).lower()}|{occurrence}".encode()).hexdigest()[:16])

def stable_source_identity(relative: str, section: str, summary: str, occurrence: int) -> str:
    """Keep source identity independent of adjudicated kind and line position."""
    material = (
        f"{relative}|{normalized(section).lower()}|"
        f"{normalized(summary).lower()}|{occurrence}"
    )
    return "source-{}".format(hashlib.sha256(material.encode()).hexdigest()[:16])

def authority_for(relative: str, inventory: dict[str, Any]) -> str:
    return inventory.get("documents", {}).get(relative, "historical-report" if relative.startswith(".hermes/plans/") and ("audit" in relative or "report" in relative) else "active-implementation-tracker" if relative.startswith(".hermes/plans/") else "contributor-current" if relative == "AGENTS.md" else "unclassified")

def status_for(text: str) -> str | None:
    match = re.search(r"^\*\*Status:\*\*\s*(.+)$", text, re.M)
    return match.group(1).strip() if match else None

def kind_for_line(line: str, *, heading: str = "", authority: str = "") -> str | None:
    listed = LIST_ITEM.match(line)
    if (
        listed
        and normalized(heading).lower() in OPEN_QUESTION_HEADINGS
        and authority in OPEN_QUESTION_AUTHORITIES
    ):
        return "open-question"
    if CHECKBOX.match(line): return "task"
    if not EXPLICIT.search(line): return None
    low = line.lower()
    # A decision package is reserved for an explicit unresolved question, not for
    # headings, decision history, instructions, or generic uses of the word.
    if re.search(r"\bopen question\s*:", low) and "?" in line:
        return "open-question"
    if "blocked" in low or "deferred" in low: return "blocker"
    if any(x in low for x in ("acceptance", "success criteria", "definition of done", "exit gate")): return "acceptance"
    return "requirement"

def domain_for(relative: str, text: str) -> str:
    lower = f"{relative} {text}".lower()
    for token, domain in (("secret","secrets"),("sops","secrets"),("ansible","ansible"),("opentofu","opentofu"),("terraform","opentofu"),("state","state"),("backup","state"),("projection","projection"),("migration","migration"),("catalog","catalog"),("service","service"),("operator","operator"),("documentation","documentation"),("doc","documentation"),("ci","ci"),("tool","tooling")):
        if token in lower: return domain
    return "canonical-model"

def extract_items(relative: str, text: str, authority: str = "") -> list[dict[str, Any]]:
    items=[]; section="Document preamble"; occurrences=Counter(); source_occurrences=Counter(); question_section=False
    for line_no,line in enumerate(text.splitlines(), 1):
        heading=HEADING.match(line)
        if heading:
            section=heading.group(2)
            question_section=normalized(section).lower() in OPEN_QUESTION_HEADINGS
        label=OPEN_QUESTION_LABEL.match(line)
        if label:
            section=label.group(1)
            question_section=True
        audit=AUDIT_HEADING.match(line)
        if audit:
            finding,summary=audit.groups(); occurrences[("finding",summary)]+=1; source_occurrences[(section,summary)]+=1
            items.append(make_record(relative,line_no,section,"finding",summary,finding,occurrences[("finding",summary)],source_occurrences[(section,summary)])); continue
        # A plain-text label has no Markdown structural boundary.  It governs only
        # its immediately following list, not later verification/checklist lists.
        kind=kind_for_line(line, heading=section if question_section else "", authority=authority)
        if kind:
            checkbox=CHECKBOX.match(line); listed=LIST_ITEM.match(line)
            summary=checkbox.group(2) if checkbox else listed.group(1) if listed else line.strip()
            occurrences[(kind,summary)]+=1
            source_occurrences[(section,summary)]+=1
            items.append(make_record(relative,line_no,section,kind,summary,None,occurrences[(kind,summary)],source_occurrences[(section,summary)]))
        if question_section and line.strip() and not heading and not label and not LIST_ITEM.match(line):
            question_section=False
    return items

def package_for(record: dict[str, Any]) -> str:
    if record["source"]["kind"] == "finding": return AUDIT_PACKAGE[record["id"].upper()]
    if record["source"]["kind"] == "open-question": return "DECISIONS"
    locator = (record["source"]["path"] + "\n" + record["source"]["heading"]).lower()
    for package, needles in PACKAGE_RULES:
        if any(needle in locator for needle in needles): return package
    # Explicit fallback rule: all remaining tracked historical/current documentation claims
    # are retained in the DOCS package; no source claim is dropped or inferred complete.
    return "DOCS"

def make_record(relative: str,line: int,section: str,kind: str,summary: str,audit_id: str|None,occurrence: int,source_occurrence: int|None=None) -> dict[str, Any]:
    ident=audit_id.lower() if audit_id else stable_id(relative,kind,summary,occurrence)
    decision_contract={"owner":"unassigned","options":[],"trigger":"","deadline":"","dependency_ids":[]} if kind=="open-question" else None
    semantic_key=DECISION_SEMANTIC_KEYS.get(normalized(summary)) if kind=="open-question" else None
    record={"id":ident,"source_identity":stable_source_identity(relative,section,summary,source_occurrence or occurrence),"source":{"path":relative,"heading":section,"line":line,"kind":kind},"summary":normalized(summary),"semantic_identity":{"path":relative,"kind":kind,"normalized_summary":semantic_key or normalized(summary).lower(),"occurrence":occurrence},"domain":domain_for(relative,summary),"scope":"repository","priority":({"H":"high","M":"medium","L":"low"}.get(audit_id[0],"none") if audit_id else "none"),"recommended_action":"cite production and focused verification evidence; do not treat tracker status or checkbox as proof","target_artifact":"","notes":"Losslessly extracted source claim under the declared extraction contract. Adjudicated conservatively without private, provider, live, or recovery access.","evidence":[{"path":relative,"lines":str(line),"role":"source-claim","claim":normalized(summary)}],"missing_evidence":["Production-path and focused verification citations are required before a static implementation claim; provider/live/recovery are separate gates."],"dependencies":[],"duplicates":[],"superseded_by":[],"decision_contract":decision_contract}
    record["package"]=package_for(record)
    low=summary.lower()
    record["disposition"]="blocked-external" if kind=="open-question" else "superseded" if ("superseded" in low or "succeeded by" in low) else "evidence-required"
    record["evidence_level"]="source"
    return record

def duplicate_edges(records: list[dict[str, Any]]) -> None:
    grouped=defaultdict(list)
    for r in records:
        semantic = r["semantic_identity"]["normalized_summary"]
        grouped[(r["source"]["kind"], semantic)].append(r)
    for group in grouped.values():
        if len(group)>1:
            primary=group[0]
            for duplicate in group[1:]:
                duplicate["disposition"]="duplicate"; duplicate["duplicate_of"]=primary["id"]
                duplicate["duplicates"]=[]; primary["duplicates"].append(duplicate["id"])

def build() -> tuple[dict[str,Any],dict[str,Any],dict[str,Any],str]:
    inventory=json.loads((ROOT/"docs/documentation-inventory.json").read_text())
    sources=[]; records=[]
    for rel in source_paths():
        raw=(ROOT/rel).read_bytes(); text=raw.decode("utf-8")
        authority=authority_for(rel,inventory)
        extracted=extract_items(rel,text,authority) if rel.endswith(".md") or rel=="AGENTS.md" else []
        records.extend(extracted)
        sources.append({"path":rel,"sha256":hashlib.sha256(raw).hexdigest(),"authority":authority,"stated_status":status_for(text),"extracted_item_count":len(extracted)})
    records.sort(key=lambda r:(r["source"]["path"],r["source"]["line"],r["id"]))
    duplicate_edges(records)
    source_complete_packages=set(PACKAGE_EVIDENCE)
    for record in records:
        # Package evidence is intentionally sufficient only for the audit finding
        # itself. Other extracted prose and checklist claims remain source claims
        # until they receive record-specific evidence.
        if record["source"]["kind"] == "finding" and record["package"] in source_complete_packages:
            record["disposition"]="implemented-static"
            record["evidence_level"]="static"
            record["evidence"].extend([
                {**citation, "role": role}
                for role, citation in PACKAGE_EVIDENCE[record["package"]].items()
            ])
            record["missing_evidence"]=["Provider, live, and recovery acceptance remain blocked-external."]
    # Preserve explicit historical supersession source records; only connect them to
    # named successor records when that successor exists in the same lossless ledger.
    by_path=defaultdict(list)
    for r in records: by_path[r["source"]["path"]].append(r)
    for r in records:
        if r["disposition"]=="superseded":
            candidates=[x for x in by_path[r["source"]["path"]] if x["id"]!=r["id"] and x["disposition"]!="superseded"]
            if candidates: r["superseded_by"]=[candidates[0]["id"]]
    source_register={"schema_version":5,"generated_from":"tracked public sources; generated reconciliation outputs excluded","sources":sources}
    ledger={"schema_version":6,"phase":"lossless-extraction-and-conservative-adjudication","identity_policy":"record IDs use path + kind + normalized source statement + occurrence; source_identity omits adjudicated kind so source identity remains stable across classification changes","evidence_policy":"checkboxes and tracker statuses are source claims only","decision_policy":"only list items under exact authoritative Open questions or Decisions that must not be guessed headings enter DECISIONS; owner/options/trigger/deadline/dependencies stay unassigned/empty unless source supplies them","records":records}
    memberships=defaultdict(list)
    for r in records: memberships[r["package"]].append(r["id"])
    packages=[]
    for p in PACKAGES:
        q=dict(p)
        package_evidence=PACKAGE_EVIDENCE.get(p["id"])
        q["included_record_ids"]=memberships[p["id"]]
        q["source_status"]="source-complete" if package_evidence else "evidence-required"
        q["source_disposition"]="implemented-static" if package_evidence else "blocked-external" if p["id"] in {"DECISIONS", "ACCEPTANCE"} else "evidence-required"
        q["external_status"]="blocked-external"
        q["evidence_registry"]=package_evidence or {}
        q["evidence_citations"]=sorted({f"{r['source']['path']}:{r['source']['line']}" for r in records if r['package']==p['id']})
        packages.append(q)
    backlog={"schema_version":5,"adjudication_rule":"source-complete is allowed only with current production-path and focused verification citations; provider/live/recovery remain blocked-external","packages":packages,"frontier":[p["id"] for p in packages if p["id"] not in {"ACCEPTANCE","DOCS","CI"} and not p["depends_on"]],"external_acceptance":["ACCEPTANCE"]}
    counts=Counter(r["source"]["path"] for r in records)
    coverage="\n".join(["# Reconciliation extraction coverage","","Generated losslessly from tracked source records; generated artifacts are excluded from discovery.","","| Source | Extracted records |","| --- | ---: |",*[f"| `{s['path']}` | {counts[s['path']]} |" for s in sources],"",f"Total extracted records: **{len(records)}**.",f"Audit finding IDs present: **{sum(r['id'].upper() in AUDIT_IDS for r in records)} / {len(AUDIT_IDS)}**.",""])
    return source_register,ledger,backlog,coverage

def citation_errors(citation:dict[str,Any],sources:dict[str,Any])->list[str]:
    path=citation.get("path", "")
    role=citation.get("role", "source-claim")
    if role == "source-claim" and path not in sources:
        return [f"unregistered source-claim citation path: {path}"]
    candidate=ROOT/path
    if not candidate.is_file():
        return [f"missing citation path: {path}"]
    try:
        parts=citation["lines"].split("-"); start=int(parts[0]); end=int(parts[-1])
        limit=len(candidate.read_text().splitlines())
        return [] if 1<=start<=end<=limit else [f"invalid citation range: {path}:{citation['lines']}"]
    except (ValueError, KeyError):
        return [f"invalid citation syntax: {path}:{citation.get('lines', '')}"]

def cycle_errors(packages:list[dict[str,Any]])->list[str]:
    graph={p['id']:p['depends_on'] for p in packages}; errors=[]; visiting=set(); done=set()
    def visit(node:str):
        if node in visiting: errors.append(f"package dependency cycle: {node}"); return
        if node in done:return
        visiting.add(node)
        for child in graph[node]:
            if child not in graph: errors.append(f"dangling package dependency: {node} -> {child}")
            else: visit(child)
        visiting.remove(node); done.add(node)
    for key in graph:visit(key)
    return errors

def validate(register:dict[str,Any],ledger:dict[str,Any],backlog:dict[str,Any])->list[str]:
    errors=[]; sources={s['path']:s for s in register['sources']}; records=ledger['records']; ids={r['id'] for r in records}
    if len(ids)!=len(records):errors.append("duplicate ledger IDs")
    if set(source_paths())!=set(sources):errors.append("source register does not exactly cover source universe")
    if sum(s['extracted_item_count'] for s in register['sources'])!=len(records):errors.append("source extraction totals do not equal ledger count")
    if any(r['disposition']=="unreconciled" for r in records):errors.append("unreconciled disposition is forbidden")
    required={"source_identity","source","semantic_identity","summary","domain","scope","priority","recommended_action","target_artifact","notes","evidence","missing_evidence","dependencies","duplicates","superseded_by","decision_contract","package","disposition","evidence_level"}
    for r in records:
        missing=required-set(r)
        if missing:errors.append(f"missing record schema fields {r['id']}: {sorted(missing)}")
        if r['disposition'] not in DISPOSITIONS:errors.append(f"invalid disposition: {r['id']}")
        if r['evidence_level'] not in EVIDENCE_LEVELS:errors.append(f"invalid evidence level: {r['id']}")
        if r['source']['path'] not in sources:errors.append(f"record source missing from register: {r['id']}")
        for ev in r['evidence']:errors.extend(citation_errors(ev,sources))
        for ref in r['dependencies']+r['duplicates']+r['superseded_by']:
            if ref not in ids:errors.append(f"dangling record reference: {r['id']} -> {ref}")
        if r['disposition']=="duplicate" and r.get("duplicate_of") not in ids:errors.append(f"duplicate lacks primary edge: {r['id']}")
        if r["source"]["kind"] == "open-question":
            contract=r["decision_contract"]
            if not isinstance(contract, dict) or set(contract) != {"owner", "options", "trigger", "deadline", "dependency_ids"}:
                errors.append(f"invalid decision contract: {r['id']}")
            elif contract["owner"] != "unassigned" or contract["options"] or contract["trigger"] or contract["deadline"] or contract["dependency_ids"]:
                errors.append(f"decision contract must not invent ownership, options, trigger, deadline, or dependencies: {r['id']}")
        elif r["decision_contract"] is not None:
            errors.append(f"non-decision record has decision contract: {r['id']}")
    findings={r['id'].upper() for r in records if r['source']['kind']=='finding'}
    if findings!=set(AUDIT_IDS):errors.append("audit finding coverage incomplete")
    for source in register['sources']:
        actual=hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest()
        if source['sha256']!=actual:errors.append(f"stale source hash: {source['path']}")
    packages=backlog['packages']; package_ids={p['id'] for p in packages}; errors.extend(cycle_errors(packages))
    if any(r['package'] not in package_ids for r in records):errors.append("record has missing backlog package")
    members=[rid for p in packages for rid in p['included_record_ids']]
    if Counter(members)!=Counter(r['id'] for r in records):errors.append("every record must appear exactly once in package membership")
    for p in packages:
        for field in ("files","contracts","criteria","safety","commands","included_record_ids","evidence_citations","source_status","source_disposition","external_status","evidence_registry"):
            if field not in p or (not p[field] and field not in {"included_record_ids","evidence_citations","evidence_registry"}):errors.append(f"package lacks {field}: {p['id']}")
        if p["source_status"] == "source-complete":
            registry=p["evidence_registry"]
            if set(registry) != {"production", "verification"}:
                errors.append(f"source-complete package lacks production/verification evidence: {p['id']}")
            else:
                for role, citation in registry.items():
                    if citation.get("role", role) not in {role, ""}:
                        errors.append(f"invalid package evidence role: {p['id']} -> {role}")
                    errors.extend(citation_errors({**citation, "role": role}, sources))
        if p["external_status"] != "blocked-external":errors.append(f"external evidence must remain blocked: {p['id']}")
        for path in p['files']:
            if not (ROOT/path).exists():errors.append(f"dangling package file reference: {p['id']} -> {path}")
    for finding in (r for r in records if r["source"]["kind"] == "finding"):
        package=next(p for p in packages if p["id"] == finding["package"])
        if finding["disposition"] == "implemented-static":
            if package["source_status"] != "source-complete" or finding["evidence_level"] != "static":
                errors.append(f"implemented finding lacks source-complete package: {finding['id']}")
            roles={citation.get("role") for citation in finding["evidence"]}
            if not {"production", "verification"} <= roles:
                errors.append(f"implemented finding lacks package evidence: {finding['id']}")
    return errors

def artifacts(register:dict[str,Any],ledger:dict[str,Any],backlog:dict[str,Any],coverage:str)->dict[Path,str]:
    src_md=["# Reconciliation source register","","Hashes and source totals are generated from the tracked public source universe.","","| Source | Authority | SHA-256 | Extracted |","| --- | --- | --- | ---: |",*[f"| `{s['path']}` | {s['authority']} | `{s['sha256']}` | {s['extracted_item_count']} |" for s in register['sources']],""]
    docs=["# Evidence-backed canonical backlog","","Every package enumerates its lossless ledger membership. Checked boxes/tracker status remain source claims, not completion evidence.",""]
    waves={}
    for i,p in enumerate(backlog['packages'],1):
        docs += [f"## {p['id']} — {p['title']}",f"- **Source status:** {p['source_status']}",f"- **Source disposition:** {p['source_disposition']}",f"- **External status:** {p['external_status']}",f"- **Priority:** {p['priority']}",f"- **Dependencies:** {', '.join(p['depends_on']) or 'none'}",f"- **Files:** {', '.join('`'+x+'`' for x in p['files'])}",f"- **Contracts:** {'; '.join(p['contracts'])}",f"- **Criteria:** {'; '.join(p['criteria'])}",f"- **Safety:** {'; '.join(p['safety'])}",f"- **Ledger records:** {', '.join('`'+x+'`' for x in p['included_record_ids']) or 'none'}",f"- **Package evidence:** {'; '.join('`'+role+': '+citation['path']+':'+citation['lines']+'`' for role,citation in p['evidence_registry'].items()) or 'none; evidence required'}",f"- **Evidence citations:** {', '.join('`'+x+'`' for x in p['evidence_citations']) or 'none'}","- **Commands:**",*[f"  - `{x}`" for x in p['commands']],""]
        waves[RECON/f"waves/{i:02d}-{p['id'].lower()}.md"]="\n".join([f"# Wave {i}: {p['id']} — {p['title']}",f"Source status: **{p['source_status']}**. Source disposition: **{p['source_disposition']}**. External status: **{p['external_status']}**.",f"Dependencies: {', '.join(p['depends_on']) or 'none'}.",f"Ledger records: {', '.join(p['included_record_ids']) or 'none'}.",f"Package evidence: {'; '.join(role+': '+citation['path']+':'+citation['lines'] for role,citation in p['evidence_registry'].items()) or 'evidence required'}.",f"Evidence citations: {', '.join(p['evidence_citations']) or 'none'}."])+"\n"
    dep=["# Canonical package dependency graph","","```mermaid","graph LR",*[f"  {dep} --> {p['id']}" for p in backlog['packages'] for dep in p['depends_on']],"```","",f"Immediate source frontier: {', '.join('`'+x+'`' for x in backlog['frontier'])}. External acceptance is separately gated.",""]
    decisions=[r for r in ledger['records'] if r['package']=='DECISIONS']
    canonical=[r for r in decisions if r['disposition']!='duplicate']
    duplicates=[r for r in decisions if r['disposition']=='duplicate']
    question_row=lambda r: f"- `{r['id']}` — **{r['summary']}**\n  Source: `{r['source']['path']}:{r['source']['line']}`; owner: `{r['decision_contract']['owner']}`; options: `{r['decision_contract']['options']}`; trigger: `{r['decision_contract']['trigger']}`; deadline: `{r['decision_contract']['deadline']}`; dependency IDs: `{r['decision_contract']['dependency_ids']}`"
    dec=["# Explicit source questions and decisions","","Only list items under exact authoritative **Open questions** or **Decisions that must not be guessed** headings belong here. Historical approvals, headings, instructions, acceptance language, and generic decision wording remain in their source packages.","","## Canonical unresolved questions","",*( [question_row(r) for r in canonical] or ["No explicit unresolved operator/product questions were extracted."]),"","## Duplicate source provenance","",*( [f"- `{r['id']}` duplicates canonical `{r['duplicate_of']}`: {r['summary']}\n  Source: `{r['source']['path']}:{r['source']['line']}`" for r in duplicates] or ["No duplicate source questions."]),""]
    audit_rows=[]
    for r in ledger['records']:
        if r['source']['kind'] != 'finding':
            continue
        package=next(p for p in backlog['packages'] if p['id'] == r['package'])
        package_evidence=package['evidence_registry']
        evidence_text='; '.join(f"{role}: {citation['path']}:{citation['lines']}" for role,citation in package_evidence.items()) or 'external evidence required'
        audit_rows.append(f"| {r['id'].upper()} | `{r['package']}` | `{r['disposition']}` | `{r['id']}` | `{r['source']['path']}:{r['source']['line']}` | {evidence_text} |")
    audit=["# Audit finding package evidence registry", "", "Every audit finding has a package and final disposition. `implemented-static` rows cite a current production path and focused verification; provider, live, and recovery remain blocked-external.", "", "| Finding | Package | Disposition | Ledger record | Source claim | Package evidence |", "| --- | --- | --- | --- | --- | --- |", *audit_rows, ""]
    contradictions=["# Source-status and supersession register", "", "Historical and superseded source records remain in the ledger; duplicate and supersession edges are validated against ledger IDs. Tracker wording does not establish implementation completion.", "", f"- Superseded records: **{sum(r['disposition'] == 'superseded' for r in ledger['records'])}**.", f"- Exact duplicate records: **{sum(r['disposition'] == 'duplicate' for r in ledger['records'])}**.", ""]
    package_registry={"schema_version":1,"policy":"source-complete requires current production-path and focused verification citations; provider/live/recovery are blocked-external","packages":[{"id":p["id"],"source_status":p["source_status"],"source_disposition":p["source_disposition"],"external_status":p["external_status"],"evidence":p["evidence_registry"]} for p in backlog["packages"]]}
    result={RECON/"source-register.json":json.dumps(register,indent=2)+"\n",RECON/"design-implementation-ledger.json":json.dumps(ledger,indent=2)+"\n",RECON/"backlog.json":json.dumps(backlog,indent=2)+"\n",RECON/"audit-package-evidence-registry.json":json.dumps(package_registry,indent=2)+"\n",RECON/"extraction-coverage.md":coverage,RECON/"source-register.md":"\n".join(src_md),RECON/"decision-register.md":"\n".join(dec),RECON/"contradiction-register.md":"\n".join(contradictions),RECON/"audit-package-evidence-registry.md":"\n".join(audit),RECON/"dependency-graph.md":"\n".join(dep),ROOT/"docs/design-implementation-backlog.md":"\n".join(docs)}
    result.update(waves); return result

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--write",action="store_true"); parser.add_argument("--check",action="store_true"); parser.add_argument("--check-extraction",action="store_true"); args=parser.parse_args()
    register,ledger,backlog,coverage=build(); errors=validate(register,ledger,backlog); expected=artifacts(register,ledger,backlog,coverage)
    if args.write:
        for path,content in expected.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    if args.check or args.check_extraction:
        for path,content in expected.items():
            if not path.is_file() or path.read_text()!=content:errors.append(f"stale or missing generated artifact: {path.relative_to(ROOT)}; run --write")
    if errors:
        print("\n".join("ERROR: "+e for e in errors),file=sys.stderr); return 1
    counts=Counter(r['disposition'] for r in ledger['records'])
    print(f"reconciliation valid: {len(register['sources'])} sources, {len(ledger['records'])} records, {len(AUDIT_IDS)} audit findings; dispositions: {dict(sorted(counts.items()))}")
    return 0
if __name__=="__main__":raise SystemExit(main())

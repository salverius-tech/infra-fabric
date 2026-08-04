#!/usr/bin/env python3
"""Generate and validate the public design-to-implementation reconciliation ledger.

The extractor intentionally records source claims before it evaluates implementation.
It is safe to run in a public checkout: it only reads tracked repository files and
writes value-free reconciliation artifacts under ``.hermes/reconciliation``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_DIR = ROOT / ".hermes" / "reconciliation"
AUDIT_IDS = tuple([f"H{number}" for number in range(1, 13)] + [f"M{number}" for number in range(1, 19)] + [f"L{number}" for number in range(1, 9)])
CHECKBOX = re.compile(r"^\s*- \[([ xX])\]\s+(.+?)\s*$")
AUDIT_HEADING = re.compile(r"^###\s+((?:H|M|L)\d+)\.\s+(.+?)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BACKLOG_LANGUAGE = re.compile(
    r"\b(remaining|partial|deferred|blocked|outstanding|open question|open questions|"
    r"decision|required verification|acceptance criteria|success criteria|definition of done|exit gate)\b",
    re.IGNORECASE,
)
LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+?)\s*$")


def git_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.STDOUT
    )
    return [path for path in output.splitlines() if path]


def source_paths() -> list[str]:
    paths: list[str] = []
    for relative in git_files():
        if relative.startswith(".hermes/reconciliation/"):
            continue
        path = Path(relative)
        if path.suffix.lower() == ".md" or relative in {"AGENTS.md", "docs/documentation-inventory.json"}:
            paths.append(relative)
    return sorted(paths)


def authority_for(relative: str, inventory: dict[str, Any]) -> str:
    documented = inventory.get("documents", {}).get(relative)
    if documented:
        return documented
    if relative.startswith(".hermes/plans/"):
        if "audit" in relative or "report" in relative:
            return "historical-report"
        return "active-implementation-tracker"
    if relative == "AGENTS.md":
        return "contributor-current"
    return "unclassified"


def status_for(text: str) -> str | None:
    match = re.search(r"^\*\*Status:\*\*\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def stable_id(relative: str, kind: str, summary: str, occurrence: int) -> str:
    # Identity follows the source and normalized claim. Occurrence is only a collision
    # discriminator for repeated identical claims, so ordinary line movement is stable.
    digest = hashlib.sha256(
        f"{relative}|{kind}|{normalized(summary).lower()}|{occurrence}".encode()
    ).hexdigest()[:16]
    return f"recon-{kind}-{digest}"


def domain_for(relative: str, text: str) -> str:
    lower = f"{relative} {text}".lower()
    for token, domain in (
        ("secret", "secrets"), ("sops", "secrets"), ("ansible", "ansible"),
        ("opentofu", "opentofu"), ("terraform", "opentofu"), ("state", "state"),
        ("backup", "state"), ("projection", "projection"), ("migration", "migration"),
        ("catalog", "catalog"), ("service", "service"), ("operator", "operator"),
        ("documentation", "documentation"), ("doc", "documentation"), ("ci", "ci"),
        ("tool", "tooling"),
    ):
        if token in lower:
            return domain
    return "canonical-model"


def kind_for_line(line: str) -> str | None:
    if CHECKBOX.match(line):
        return "task"
    if BACKLOG_LANGUAGE.search(line):
        if "decision" in line.lower() or "open question" in line.lower():
            return "decision"
        if "blocked" in line.lower() or "deferred" in line.lower():
            return "blocker"
        if "acceptance" in line.lower() or "success" in line.lower() or "exit gate" in line.lower():
            return "acceptance"
        return "requirement"
    return None


def extract_items(relative: str, text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    section = "Document preamble"
    seen: set[tuple[int, str, str]] = set()
    occurrences: Counter[tuple[str, str]] = Counter()
    for number, line in enumerate(text.splitlines(), start=1):
        heading = HEADING.match(line)
        if heading:
            section = heading.group(2)
        audit = AUDIT_HEADING.match(line)
        if audit:
            finding_id, summary = audit.groups()
            key = (number, "finding", summary)
            seen.add(key)
            occurrences[("finding", summary)] += 1
            items.append(record(relative, number, section, "finding", summary, finding_id, occurrences[("finding", summary)]))
            continue
        kind = kind_for_line(line)
        if not kind:
            continue
        checkbox = CHECKBOX.match(line)
        list_item = LIST_ITEM.match(line)
        summary = checkbox.group(2) if checkbox else (list_item.group(1) if list_item else line.strip())
        key = (number, kind, summary)
        if key not in seen:
            seen.add(key)
            occurrences[(kind, summary)] += 1
            items.append(record(relative, number, section, kind, summary, None, occurrences[(kind, summary)]))
    return items


def record(relative: str, line: int, section: str, kind: str, summary: str, audit_id: str | None, occurrence: int) -> dict[str, Any]:
    identifier = audit_id.lower() if audit_id else stable_id(relative, kind, summary, occurrence)
    return {
        "id": identifier,
        "source": {"path": relative, "section": section, "line": line, "kind": kind},
        "summary": normalized(summary),
        "domain": domain_for(relative, summary),
        "scope": "repository",
        "disposition": "unreconciled",
        "evidence_level": "design",
        "evidence": [],
        "missing_evidence": ["Source-level reconciliation has not yet assigned a disposition."],
        "superseded_by": [],
        "duplicates": [],
        "dependencies": [],
        "priority": ({"H": "high", "M": "medium", "L": "low"}.get(audit_id[0], "none") if audit_id else "none"),
        "recommended_action": "none",
        "target_artifact": "",
        "notes": "Extracted claim; implementation and acceptance evidence are intentionally not inferred during extraction.",
    }


def build() -> tuple[dict[str, Any], dict[str, Any], str]:
    inventory_path = ROOT / "docs" / "documentation-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    sources: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for relative in source_paths():
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        extracted = extract_items(relative, text) if path.suffix == ".md" else []
        records.extend(extracted)
        sources.append({
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "authority": authority_for(relative, inventory),
            "stated_status": status_for(text),
            "extracted_item_count": len(extracted),
        })
    # Finding IDs are authoritative, unique IDs and should not be folded merely by wording.
    records.sort(key=lambda item: (item["source"]["path"], item["source"]["line"], item["id"]))
    source_register = {"schema_version": 1, "generated_from": "tracked public sources", "sources": sources}
    ledger = {"schema_version": 1, "phase": "extraction", "records": records}
    counts = Counter(record["source"]["path"] for record in records)
    coverage = ["# Reconciliation extraction coverage", "", "This artifact is generated by `scripts/validate-design-reconciliation.py`.", "", "| Source | Extracted records |", "| --- | ---: |"]
    coverage.extend(f"| `{source['path']}` | {counts[source['path']]} |" for source in sources)
    coverage.extend(["", f"Total extracted records: **{len(records)}**.", f"Audit finding IDs present: **{sum(1 for record in records if record['id'].upper() in AUDIT_IDS)} / {len(AUDIT_IDS)}**."])
    return source_register, ledger, "\n".join(coverage) + "\n"


def validate(register: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tracked_markdown = {path for path in source_paths() if path.endswith(".md")}
    registered = {source["path"] for source in register["sources"]}
    missing = sorted(tracked_markdown - registered)
    if missing:
        errors.append(f"unregistered tracked Markdown sources: {', '.join(missing)}")
    ids = [record["id"] for record in ledger["records"]]
    duplicate_ids = sorted(identifier for identifier, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate ledger IDs: {', '.join(duplicate_ids)}")
    findings = {record["id"].upper() for record in ledger["records"] if record["source"]["kind"] == "finding"}
    missing_findings = sorted(set(AUDIT_IDS) - findings)
    if missing_findings:
        errors.append(f"missing audit findings: {', '.join(missing_findings)}")
    if any(record["disposition"] != "unreconciled" for record in ledger["records"]):
        errors.append("extraction ledger assigned a disposition before evidence reconciliation")
    return errors


def write_artifacts(register: dict[str, Any], ledger: dict[str, Any], coverage: str) -> None:
    RECONCILIATION_DIR.mkdir(parents=True, exist_ok=True)
    (RECONCILIATION_DIR / "source-register.json").write_text(json.dumps(register, indent=2) + "\n", encoding="utf-8")
    (RECONCILIATION_DIR / "design-implementation-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    (RECONCILIATION_DIR / "extraction-coverage.md").write_text(coverage, encoding="utf-8")
    lines = ["# Reconciliation source register", "", "Generated from tracked public sources. Hashes make the extraction baseline reproducible.", "", "| Source | Authority | SHA-256 | Extracted |", "| --- | --- | --- | ---: |"]
    lines.extend(f"| `{source['path']}` | {source['authority']} | `{source['sha256']}` | {source['extracted_item_count']} |" for source in register["sources"])
    (RECONCILIATION_DIR / "source-register.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-extraction", action="store_true", help="validate extraction artifacts without rewriting them")
    parser.add_argument("--write", action="store_true", help="regenerate reconciliation artifacts")
    args = parser.parse_args()
    register, ledger, coverage = build()
    if args.write:
        write_artifacts(register, ledger, coverage)
    errors = validate(register, ledger)
    if args.check_extraction:
        expected = {
            "source-register.json": json.dumps(register, indent=2) + "\n",
            "design-implementation-ledger.json": json.dumps(ledger, indent=2) + "\n",
            "extraction-coverage.md": coverage,
        }
        for name, content in expected.items():
            path = RECONCILIATION_DIR / name
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                errors.append(f"stale or missing generated artifact: .hermes/reconciliation/{name}; run with --write")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"reconciliation extraction valid: {len(register['sources'])} sources, {len(ledger['records'])} records, {len(AUDIT_IDS)} audit findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import copy
import importlib.util
import json
import subprocess
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-design-reconciliation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("design_reconciliation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesignReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.register, cls.ledger, cls.backlog, cls.coverage = cls.module.build()

    def test_generated_lossless_ledger_is_current(self):
        result = subprocess.run(
            ["python3", "-B", str(SCRIPT), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("38 audit findings", result.stdout)

    def test_total_lossless_coverage_and_no_source_record_loss(self):
        expected = []
        for path in self.module.source_paths():
            if path.endswith(".md") or path == "AGENTS.md":
                expected.extend(
                    self.module.extract_items(
                        path,
                        (ROOT / path).read_text(),
                        self.module.authority_for(
                            path,
                            json.loads(
                                (
                                    ROOT / "docs" / "documentation-inventory.json"
                                ).read_text()
                            ),
                        ),
                    )
                )
        actual = self.ledger["records"]
        self.assertGreater(len(actual), 0)
        self.assertEqual(
            Counter(r["id"] for r in expected), Counter(r["id"] for r in actual)
        )
        self.assertEqual(
            sum(s["extracted_item_count"] for s in self.register["sources"]),
            len(actual),
        )

    def test_no_unreconciled_and_required_provenance(self):
        required = {"path", "heading", "line", "kind"}
        for record in self.ledger["records"]:
            self.assertNotEqual(record["disposition"], "unreconciled")
            self.assertIn(record["disposition"], self.module.DISPOSITIONS)
            self.assertTrue(required.issubset(record["source"]))
            self.assertTrue(record["semantic_identity"])
            self.assertTrue(record["evidence"])

    def test_ids_are_stable_under_line_shifts(self):
        original = self.module.make_record(
            "docs/example.md", 12, "Heading", "requirement", "A requirement", None, 1
        )
        shifted = self.module.make_record(
            "docs/example.md", 99, "Heading", "requirement", "A requirement", None, 1
        )
        self.assertEqual(original["id"], shifted["id"])
        self.assertNotEqual(original["source"]["line"], shifted["source"]["line"])

    def test_source_identity_is_stable_when_adjudicated_classification_changes(self):
        requirement = self.module.make_record(
            "docs/example.md", 12, "Heading", "requirement", "A source claim", None, 1
        )
        question = self.module.make_record(
            "docs/example.md", 12, "Heading", "open-question", "A source claim", None, 1
        )
        self.assertEqual(requirement["source_identity"], question["source_identity"])
        self.assertNotEqual(requirement["id"], question["id"])

    def test_checkbox_is_only_source_evidence(self):
        checked = self.module.make_record(
            "docs/example.md", 1, "Heading", "task", "checked task", None, 1
        )
        self.assertEqual(checked["disposition"], "evidence-required")
        self.assertEqual(checked["evidence_level"], "source")
        self.assertEqual(checked["evidence"][0]["role"], "source-claim")

    def test_decision_word_false_positives_remain_non_decision_source_claims(self):
        cases = (
            ("## Approved architectural decision ledger", "requirement"),
            ("## Decision log", "requirement"),
            ("Prepare a decision register before implementation.", "requirement"),
            ("The acceptance decision must be recorded.", "acceptance"),
            ("A blocked task requires an operator decision.", "blocker"),
        )
        for line, expected in cases:
            with self.subTest(line=line):
                self.assertEqual(self.module.kind_for_line(line), expected)
                record = self.module.make_record(
                    "docs/example.md", 1, "Example", expected, line, None, 1
                )
                self.assertNotEqual(record["package"], "DECISIONS")
                self.assertNotEqual(record["disposition"], "blocked-external")

    def test_authoritative_open_question_heading_accepts_list_items_without_literal_prefix(
        self,
    ):
        cases = (
            (
                "docs/hermes-operator-pilot-prd.md",
                "working design",
                "Open questions",
                "Which Hermes actions are in scope for the first pilot: status only, validate, plan, apply, private values commits, or Forgejo workflow monitoring?",
            ),
            (
                ".hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md",
                "implementation tracker",
                "Decisions that must not be guessed",
                "durable local-state single-controller policy versus remote locking backend;",
            ),
        )
        for path, authority, heading, summary in cases:
            with self.subTest(path=path, summary=summary):
                self.assertEqual(
                    self.module.kind_for_line(
                        f"- {summary}", heading=heading, authority=authority
                    ),
                    "open-question",
                )
                record = self.module.make_record(
                    path, 1, heading, "open-question", summary, None, 1
                )
                self.assertEqual(record["package"], "DECISIONS")
                self.assertEqual(record["disposition"], "blocked-external")
                self.assertEqual(
                    record["decision_contract"],
                    {
                        "owner": "unassigned",
                        "options": [],
                        "trigger": "",
                        "deadline": "",
                        "dependency_ids": [],
                    },
                )

    def test_open_question_heading_rejects_false_positive_authority_and_non_list_text(
        self,
    ):
        for authority, line in (
            ("historical-report", "- What did the historical decision choose?"),
            ("working design", "Open questions"),
            (
                "working design",
                "The Open questions heading is an instruction, not a source choice.",
            ),
        ):
            with self.subTest(authority=authority, line=line):
                self.assertNotEqual(
                    self.module.kind_for_line(
                        line, heading="Open questions", authority=authority
                    ),
                    "open-question",
                )

    def test_approved_decisions_are_retained_without_unresolved_questions(self):
        unresolved = [
            record
            for record in self.ledger["records"]
            if record["source"]["kind"] == "open-question"
            or record["package"] == "DECISIONS"
        ]
        self.assertEqual(unresolved, [])
        approved = [
            record
            for record in self.ledger["records"]
            if record["source"]["path"]
            == ".hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md"
            and record["source"]["heading"] == "Approved decision record — 2026-08-06"
            and record["summary"].startswith("**Decision D")
        ]
        self.assertEqual(len(approved), 10)
        self.assertEqual(
            {record["summary"].split(" — ", 1)[0] for record in approved},
            {f"**Decision D{number}" for number in range(1, 11)},
        )
        self.assertTrue(all(record["decision_contract"] is None for record in approved))

    def test_decision_register_records_that_no_questions_remain(self):
        register = self.module.artifacts(
            self.register, self.ledger, self.backlog, self.coverage
        )[self.module.RECON / "decision-register.md"]
        self.assertIn("## Canonical unresolved questions", register)
        self.assertIn("## Duplicate source provenance", register)
        self.assertIn(
            "No explicit unresolved operator/product questions were extracted.",
            register,
        )
        self.assertIn("No duplicate source questions.", register)
        self.assertNotIn(
            "Which Hermes actions are in scope for the first pilot", register
        )

    def test_historical_decision_with_named_successor_is_superseded_not_open(self):
        record = self.module.make_record(
            "docs/example.md",
            1,
            "History",
            "requirement",
            "Historical source decision record: the retired review is succeeded by canonical readiness.",
            None,
            1,
        )
        self.assertEqual(record["package"], "DOCS")
        self.assertEqual(record["disposition"], "superseded")
        self.assertIsNone(record["decision_contract"])

    def test_current_extraction_count_and_source_identities_are_preserved(self):
        # Approved decision records replace the former open-question records while
        # preserving the declared extraction universe and stable source identities.
        self.assertEqual(len(self.ledger["records"]), 917)
        source_paths = {source["path"] for source in self.register["sources"]}
        self.assertIn("docs/service-operations.md", source_paths)
        self.assertIn("docs/tooling-reproducibility.md", source_paths)
        self.assertNotIn("docs/design-implementation-backlog.md", source_paths)
        self.assertEqual(
            len({record["source_identity"] for record in self.ledger["records"]}),
            len(self.ledger["records"]),
        )
        self.assertFalse(
            [
                record
                for record in self.ledger["records"]
                if record["package"] == "DECISIONS"
                and record["source"]["kind"] != "open-question"
            ]
        )

    def test_hashes_and_all_audit_findings_are_covered(self):
        findings = {
            r["id"].upper()
            for r in self.ledger["records"]
            if r["source"]["kind"] == "finding"
        }
        self.assertEqual(findings, set(self.module.AUDIT_IDS))
        audit_records = [
            r for r in self.ledger["records"] if r["source"]["kind"] == "finding"
        ]
        self.assertEqual(
            {
                r["package"]
                for r in audit_records
                if r["id"].upper() in self.module.AUDIT_IDS
            },
            set(self.module.AUDIT_PACKAGE.values()),
        )
        self.assertFalse(self.module.validate(self.register, self.ledger, self.backlog))
        mutated = copy.deepcopy(self.register)
        mutated["sources"][0]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                "stale source hash" in error
                for error in self.module.validate(mutated, self.ledger, self.backlog)
            )
        )

    def test_no_dangling_references_or_cycles(self):
        self.assertFalse(self.module.validate(self.register, self.ledger, self.backlog))
        cyclic = copy.deepcopy(self.backlog)
        cyclic["packages"][0]["depends_on"].append(cyclic["packages"][0]["id"])
        self.assertTrue(
            any(
                "cycle" in error
                for error in self.module.validate(self.register, self.ledger, cyclic)
            )
        )
        dangling = copy.deepcopy(self.ledger)
        dangling["records"][0]["dependencies"] = ["not-a-record"]
        self.assertTrue(
            any(
                "dangling record reference" in error
                for error in self.module.validate(self.register, dangling, self.backlog)
            )
        )

    def test_every_record_is_in_exactly_one_backlog_package(self):
        membership = [
            rid
            for package in self.backlog["packages"]
            for rid in package["included_record_ids"]
        ]
        self.assertEqual(
            Counter(membership),
            Counter(record["id"] for record in self.ledger["records"]),
        )
        self.assertEqual(self.backlog["external_acceptance"], ["ACCEPTANCE"])
        for package in self.backlog["packages"]:
            self.assertEqual(package["external_status"], "blocked-external")
            if package["source_status"] == "source-complete":
                self.assertEqual(
                    set(package["evidence_registry"]), {"production", "verification"}
                )

    def test_source_complete_package_requires_both_current_citations(self):
        incomplete = copy.deepcopy(self.backlog)
        package = next(
            item
            for item in incomplete["packages"]
            if item["source_status"] == "source-complete"
        )
        del package["evidence_registry"]["verification"]
        self.assertTrue(
            any(
                "lacks production/verification evidence" in error
                for error in self.module.validate(
                    self.register, self.ledger, incomplete
                )
            )
        )

    def test_implemented_audit_findings_have_package_evidence_without_promoting_all_claims(
        self,
    ):
        findings = [
            record
            for record in self.ledger["records"]
            if record["source"]["kind"] == "finding"
        ]
        self.assertTrue(
            all(record["disposition"] == "implemented-static" for record in findings)
        )
        self.assertTrue(
            all(
                {"production", "verification"}
                <= {item.get("role") for item in record["evidence"]}
                for record in findings
            )
        )
        non_findings = [
            record
            for record in self.ledger["records"]
            if record["source"]["kind"] != "finding"
        ]
        self.assertFalse(
            any(
                record["disposition"] == "implemented-static" for record in non_findings
            )
        )

    def test_invalid_package_citation_range_fails_closed(self):
        invalid = copy.deepcopy(self.backlog)
        package = next(
            item
            for item in invalid["packages"]
            if item["source_status"] == "source-complete"
        )
        package["evidence_registry"]["production"]["lines"] = "999999"
        self.assertTrue(
            any(
                "invalid citation range" in error
                for error in self.module.validate(self.register, self.ledger, invalid)
            )
        )


if __name__ == "__main__":
    unittest.main()

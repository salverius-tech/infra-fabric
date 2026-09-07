import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
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
        cls.completion, cls.audit, cls.backlog, cls.coverage = cls.module.build()

    def test_generated_compact_authorities_are_current(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("38 audit findings", result.stdout)
        self.assertIn("external acceptance only", result.stdout)

    def test_active_artifacts_are_only_compact_authorities(self):
        artifacts = self.module.artifacts(
            self.completion, self.audit, self.backlog, self.coverage
        )
        self.assertEqual(
            set(artifacts),
            {
                self.module.RECON / "package-completion.json",
                self.module.RECON / "package-completion.md",
                self.module.RECON / "audit-dispositions.json",
                self.module.RECON / "audit-dispositions.md",
                self.module.RECON / "explicit-decisions.md",
                self.module.RECON / "acceptance-matrix.json",
                self.module.RECON / "acceptance-matrix.md",
            },
        )

    def test_all_original_audit_findings_retain_disposition_and_evidence(self):
        findings = self.audit["findings"]
        self.assertEqual(
            {finding["id"] for finding in findings}, set(self.module.AUDIT_IDS)
        )
        self.assertTrue(
            all(
                finding["package"]
                in {package["id"] for package in self.completion["packages"]}
                and finding["title"] != f"Finding {finding['id']}"
                and finding["source"]["git_ref"]
                == "db51a30f635f6b41fc9d5d546b896bdcd22b8f03"
                and finding["disposition"] == "implemented-static"
                and set(finding["evidence"]) == {"production", "verification"}
                for finding in findings
            )
        )

    def test_frontier_contains_only_incomplete_source_packages(self):
        package_by_id = {
            package["id"]: package for package in self.completion["packages"]
        }
        self.assertEqual(self.completion["frontier"], [])
        self.assertTrue(
            all(
                package_by_id[package_id]["source_status"] == "incomplete"
                for package_id in self.completion["frontier"]
            )
        )
        self.assertNotIn("DECISIONS", package_by_id)

    def test_closed_decisions_are_explicit_without_a_decisions_package(self):
        self.assertEqual(len(self.completion["explicit_decisions"]), 10)
        self.assertEqual(
            {decision["id"] for decision in self.completion["explicit_decisions"]},
            {f"D{number}" for number in range(1, 11)},
        )
        self.assertFalse(self.completion["unresolved_decisions"])

    def test_acceptance_matrix_separates_environments(self):
        matrix = self.completion["acceptance_matrix"]
        self.assertEqual(
            set(matrix["environments"]),
            {"development", "isolated-recovery", "production"},
        )
        self.assertEqual(set(matrix["columns"]), set(self.module.MATRIX_COLUMNS))
        self.assertEqual(
            matrix["rows"]["development"]["service-restore"],
            "evidenced",
        )
        self.assertEqual(
            matrix["rows"]["development"]["infrastructure-recovery"],
            "evidenced",
        )
        self.assertEqual(
            matrix["rows"]["development"]["hermes-integration"],
            "evidenced",
        )
        self.assertEqual(matrix["rows"]["development"]["rollback"], "evidenced")
        self.assertEqual(
            matrix["rows"]["isolated-recovery"]["service-restore"],
            "not-evidenced",
        )
        self.assertEqual(
            matrix["rows"]["production"]["service-restore"], "not-evidenced"
        )
        self.assertEqual(
            set(matrix["evidence"]),
            {
                "development/plan",
                "development/apply",
                "development/health-idempotence",
                "development/service-restore",
                "development/infrastructure-recovery",
                "development/hermes-integration",
                "development/rollback",
            },
        )
        for cell, evidence in matrix["evidence"].items():
            environment, category = cell.split("/", 1)
            self.assertEqual(evidence["environment"], environment)
            self.assertEqual(evidence["category"], category)
            self.assertRegex(evidence["audited_commit"], r"^[0-9a-f]{40}$")
            self.assertEqual(
                evidence["citation"]["git_ref"], evidence["audited_commit"]
            )
            self.assertEqual(evidence["result"], "passed")
            self.assertTrue(evidence["boundary"])

    def test_frozen_lossless_history_is_a_resolvable_git_reference(self):
        reference = self.completion["historical_ledger"]
        self.assertRegex(reference["git_ref"], r"^[0-9a-f]{40}$")
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{reference['git_ref']}:" + reference["path"]],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_validation_fails_closed_for_stale_or_mismatched_audit_provenance(self):
        invalid = copy.deepcopy(self.audit)
        invalid["findings"][0]["evidence"]["production"]["lines"] = "999999"
        invalid["findings"][0]["title"] = "Invented finding"
        errors = self.module.validate(self.completion, invalid, self.backlog)
        self.assertTrue(any("invalid citation" in error for error in errors))
        self.assertTrue(any("provenance does not match" in error for error in errors))

    def test_validation_requires_immutable_audit_and_decision_references(self):
        invalid_completion = copy.deepcopy(self.completion)
        invalid_audit = copy.deepcopy(self.audit)
        invalid_audit["findings"][0]["source"].pop("git_ref")
        invalid_completion["explicit_decisions"][0]["source"].pop("git_ref")

        errors = self.module.validate(invalid_completion, invalid_audit, self.backlog)

        self.assertEqual(
            sum("historical citation must use" in error for error in errors), 2
        )

    def test_validation_rejects_historical_provenance_substituted_with_working_tree(
        self,
    ):
        invalid = copy.deepcopy(self.audit)
        invalid["findings"][0]["source"] = {
            "path": "scripts/validate-design-reconciliation.py",
            "lines": "1",
        }

        errors = self.module.validate(self.completion, invalid, self.backlog)

        self.assertTrue(
            any("historical citation must use" in error for error in errors)
        )

    def test_validation_rejects_altered_or_shortened_historical_titles(self):
        invalid_completion = copy.deepcopy(self.completion)
        invalid_audit = copy.deepcopy(self.audit)
        invalid_audit["findings"][0][
            "title"
        ] = "Stateful destructive-change classification"
        invalid_completion["explicit_decisions"][0]["title"] = "State and locking"

        errors = self.module.validate(invalid_completion, invalid_audit, self.backlog)

        self.assertTrue(
            any(
                "audit finding provenance does not match: H1" in error
                for error in errors
            )
        )
        self.assertTrue(
            any(
                "explicit decision provenance does not match: D1" in error
                for error in errors
            )
        )

    def test_validation_rejects_duplicate_historical_authority_ids(self):
        invalid_completion = copy.deepcopy(self.completion)
        invalid_audit = copy.deepcopy(self.audit)
        invalid_audit["findings"].append(copy.deepcopy(invalid_audit["findings"][0]))
        invalid_completion["explicit_decisions"].append(
            copy.deepcopy(invalid_completion["explicit_decisions"][0])
        )

        errors = self.module.validate(invalid_completion, invalid_audit, self.backlog)

        self.assertTrue(
            any(
                "audit finding coverage incomplete or duplicated" in error
                for error in errors
            )
        )
        self.assertTrue(any("explicit decision authority" in error for error in errors))

    def test_authority_rejects_duplicate_ids_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            authority_path = Path(temporary_directory) / "authority.json"
            invalid = self.module.authority()
            invalid["audit"]["findings"].append(
                copy.deepcopy(invalid["audit"]["findings"][0])
            )
            authority_path.write_text(json.dumps(invalid), encoding="utf-8")
            original_authority_path = self.module.AUTHORITY_PATH
            setattr(self.module, "AUTHORITY_PATH", authority_path)
            try:
                with self.assertRaisesRegex(ValueError, "audit IDs are incomplete"):
                    self.module.authority()
            finally:
                setattr(self.module, "AUTHORITY_PATH", original_authority_path)

    def test_generation_is_idempotent_and_never_uses_generated_output_as_input(self):
        artifacts = self.module.artifacts(
            self.completion, self.audit, self.backlog, self.coverage
        )
        before = {path: path.read_text(encoding="utf-8") for path in artifacts}
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "reconciliation"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--write",
                    "--check",
                    "--reconciliation-dir",
                    str(output_directory),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for path, content in artifacts.items():
                generated = output_directory / path.relative_to(self.module.RECON)
                self.assertEqual(generated.read_text(encoding="utf-8"), content)

        after = {path: path.read_text(encoding="utf-8") for path in artifacts}
        self.assertEqual(after, before)

    def test_validation_fails_closed_for_promoted_recovery_evidence(self):
        invalid = copy.deepcopy(self.completion)
        invalid["acceptance_matrix"]["rows"]["isolated-recovery"][
            "service-restore"
        ] = "evidenced"
        self.assertTrue(self.module.validate(invalid, self.audit, self.backlog))

    def test_validation_rejects_evidenced_cell_without_record(self):
        invalid = copy.deepcopy(self.completion)
        del invalid["acceptance_matrix"]["evidence"]["development/plan"]
        self.assertTrue(self.module.validate(invalid, self.audit, self.backlog))

    def test_validation_rejects_wrong_environment_or_commit(self):
        invalid = copy.deepcopy(self.completion)
        record = invalid["acceptance_matrix"]["evidence"]["development/plan"]
        record["environment"] = "production"
        record["audited_commit"] = "0" * 40
        errors = self.module.validate(invalid, self.audit, self.backlog)
        self.assertTrue(any("identity mismatch" in error for error in errors))
        self.assertTrue(any("commit is not resolvable" in error for error in errors))

    def test_validation_rejects_dangling_or_private_evidence(self):
        invalid = copy.deepcopy(self.completion)
        record = invalid["acceptance_matrix"]["evidence"]["development/plan"]
        record["citation"] = {"path": "missing.md", "lines": "1"}
        record["boundary"] = "see /home/operator/values/site.yaml"
        errors = self.module.validate(invalid, self.audit, self.backlog)
        self.assertTrue(any("invalid citation" in error for error in errors))
        self.assertTrue(any("not public-safe" in error for error in errors))

    def test_validation_fails_closed_for_frontier_or_decision_regression(self):
        invalid = copy.deepcopy(self.completion)
        invalid["frontier"] = ["R1"]
        invalid["unresolved_decisions"] = ["new-question"]
        self.assertTrue(self.module.validate(invalid, self.audit, self.backlog))

    def test_retire_declared_artifacts_deletes_only_declared_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            reconciliation = Path(temporary_directory)
            declared_artifact = reconciliation / self.module.RETIRED_ARTIFACTS[0]
            declared_wave = (
                reconciliation / "waves" / self.module.RETIRED_WAVE_OUTPUTS[0]
            )
            undeclared_artifact = reconciliation / "operator-notes.md"
            undeclared_wave = reconciliation / "waves" / "operator-notes.md"
            for path in (
                declared_artifact,
                declared_wave,
                undeclared_artifact,
                undeclared_wave,
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("preserve or retire\n", encoding="utf-8")

            self.module.retire_declared_artifacts(reconciliation)

            self.assertFalse(declared_artifact.exists())
            self.assertFalse(declared_wave.exists())
            self.assertTrue(undeclared_artifact.is_file())
            self.assertTrue(undeclared_wave.is_file())

    def test_validation_rejects_retired_generated_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            reconciliation = Path(temporary_directory)
            retired = reconciliation / "backlog.json"
            retired.write_text("{}\n", encoding="utf-8")
            original_reconciliation = self.module.RECON
            setattr(self.module, "RECON", reconciliation)
            try:
                self.assertTrue(
                    self.module.validate(self.completion, self.audit, self.backlog)
                )
            finally:
                setattr(self.module, "RECON", original_reconciliation)


if __name__ == "__main__":
    unittest.main()

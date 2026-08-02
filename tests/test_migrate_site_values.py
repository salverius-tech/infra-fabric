from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "migrate_site_values", ROOT / "scripts" / "migrate-site-values.py"
)
assert spec and spec.loader
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class SiteMigrationTests(unittest.TestCase):
    def make_legacy_values(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        values = root / "values"
        (values / "ansible" / "inventory").mkdir(parents=True)
        (values / ".env").write_text("PVE_HOST=proxmox.example.internal\n", encoding="utf-8")
        (values / "terraform.tfvars").write_text("x = 1\n", encoding="utf-8")
        (values / "dns-records.local.json").write_text("{}\n", encoding="utf-8")
        (values / "ansible" / "inventory" / "local.yml").write_text("---\n", encoding="utf-8")
        (root / "settings.local.json").write_text(
            json.dumps({"values_repo": {"remote": ""}, "services": ["hermes"]}),
            encoding="utf-8",
        )
        return temp, values

    def test_dry_run_does_not_mutate_legacy_values(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            actions = migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, False)
            self.assertTrue(any(action.startswith("move ") for action in actions))
            self.assertFalse((values / "sites" / "dev").exists())
            self.assertIn('"services"', (values.parent / "settings.local.json").read_text())

    def test_apply_moves_files_and_site_services(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True)
            site = values / "sites" / "dev"
            self.assertEqual(json.loads((site / "site.json").read_text())["services"], ["hermes"])
            manifest = json.loads((site / "migration-manifest.json").read_text())
            self.assertFalse(manifest["secret_values_included"])
            self.assertEqual(manifest["backup_id"], "dev")
            backup = values.parent / ".migration-backups" / "dev"
            self.assertTrue((backup / "manifest.json").is_file())
            self.assertTrue((backup / "tree" / ".env").is_file())
            dotenv_operation = next(item for item in manifest["operations"] if item["source"] == ".env")
            self.assertTrue(dotenv_operation["source_sha256"])
            self.assertEqual(dotenv_operation["source_sha256"], dotenv_operation["destination_sha256"])
            self.assertEqual(manifest["canonical_destination"], "sites/dev")
            self.assertEqual(
                {item["disposition"] for item in manifest["operations"]},
                {
                    "generated-projection",
                    "operational-artifact",
                },
            )
            self.assertTrue((site / "terraform.tfvars").is_file())
            self.assertFalse((values / "terraform.tfvars").exists())
            self.assertNotIn("services", json.loads((values.parent / "settings.local.json").read_text()))

    def test_apply_moves_private_plans_backups_and_artifacts(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            for relative in ("plans/plan.txt", "backups/archive.tgz", "artifacts/debug.log"):
                path = values / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("private artifact", encoding="utf-8")
            migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True, None, True)
            site = values / "sites" / "dev"
            for relative in ("plans/plan.txt", "backups/archive.tgz", "artifacts/debug.log"):
                self.assertTrue((site / relative).is_file())
                self.assertFalse((values / relative).exists())

    def test_development_migration_refuses_sensitive_artifacts_without_opt_in(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            (values / "backups").mkdir()
            (values / "backups" / "prod.tgz").write_text("backup", encoding="utf-8")
            with self.assertRaisesRegex(migration.SiteMigrationError, "sensitive artifacts"):
                migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, False)
            self.assertFalse((values / "sites" / "dev").exists())
            self.assertTrue((values / "backups" / "prod.tgz").exists())

    def test_interrupted_move_is_rolled_back(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            original_settings = (values.parent / "settings.local.json").read_bytes()
            original_move = migration.shutil.move
            calls = 0

            def fail_on_second_move(source: str, destination: str) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated move failure")
                original_move(source, destination)

            with patch.object(migration.shutil, "move", side_effect=fail_on_second_move):
                with self.assertRaises(migration.SiteMigrationError):
                    migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True)
            self.assertFalse((values / "sites" / "dev").exists())
            self.assertTrue((values / "terraform.tfvars").is_file())
            self.assertEqual((values.parent / "settings.local.json").read_bytes(), original_settings)

    def test_apply_candidate_generation_remains_blocked_without_runtime_admission(self) -> None:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        values = root / "values"
        values.mkdir()
        (values / ".env").write_text("SERVER_NAME=DNS.Example.Internal.\n", encoding="utf-8")
        base = root / "base.yaml"
        base.write_text("schema_version: 1\nsite:\n  name: old\nservices: {}\n", encoding="utf-8")
        with temp:
            with self.assertRaises(migration.SiteMigrationError):
                migration.migrate(values, root, "dev", "development", "disposable", True, True, True, base)
            self.assertTrue((values / ".env").exists())
            self.assertFalse((values / "sites" / "dev").exists())

    def test_candidate_generation_blocks_unknown_legacy_input_before_mutation(self) -> None:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        values = root / "values"
        values.mkdir()
        (values / ".env").write_text("UNKNOWN_PUBLIC=review-me\n", encoding="utf-8")
        base = root / "base.yaml"
        base.write_text("schema_version: 1\nsite:\n  name: old\nservices: {}\n", encoding="utf-8")
        with temp:
            with self.assertRaises(migration.SiteMigrationError):
                migration.migrate(values, root, "dev", "development", "disposable", True, True, True, base)
            self.assertTrue((values / ".env").exists())
            self.assertFalse((values / "sites" / "dev").exists())

    def test_generated_candidate_is_validated_before_migration(self) -> None:
        invalid = {"schema_version": 1, "site": {"name": "dev"}}
        with self.assertRaisesRegex(migration.SiteMigrationError, "generated canonical candidate is invalid"):
            migration._validate_candidate(invalid, "dev")

    def test_existing_canonical_site_is_validated_during_dry_run(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            target = values / "sites" / "dev"
            target.mkdir(parents=True)
            metadata = migration.site_metadata(values.parent, "dev", "development", "disposable", True, True)
            (target / "site.json").write_text(json.dumps(metadata), encoding="utf-8")
            (target / "migration-manifest.json").write_text(
                json.dumps({"canonical_destination": "sites/dev", "secret_values_included": False}),
                encoding="utf-8",
            )
            (target / "site.yaml").write_text("schema_version: 1\nsite: {}\n", encoding="utf-8")
            with self.assertRaisesRegex(migration.SiteMigrationError, "invalid canonical site model"):
                migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, False)

    def test_existing_canonical_site_can_be_adopted_without_moving_legacy_files(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            target = values / "sites" / "dev"
            target.mkdir(parents=True)
            metadata = migration.site_metadata(values.parent, "dev", "development", "disposable", True, True)
            (target / "site.json").write_text(json.dumps(metadata), encoding="utf-8")
            (target / "site.yaml").write_text("canonical: existing\n", encoding="utf-8")
            with patch.object(migration, "load_site"):
                dry_run = migration.migrate(
                    values,
                    values.parent,
                    "dev",
                    "development",
                    "disposable",
                    True,
                    True,
                    False,
                    adopt_existing=True,
                )
                self.assertIn("no legacy files moved or removed", dry_run)
                self.assertFalse((target / "migration-manifest.json").exists())
                migration.migrate(
                    values,
                    values.parent,
                    "dev",
                    "development",
                    "disposable",
                    True,
                    True,
                    True,
                    adopt_existing=True,
                )
                rerun = migration.migrate(
                    values,
                    values.parent,
                    "dev",
                    "development",
                    "disposable",
                    True,
                    True,
                    False,
                    adopt_existing=True,
                )
                self.assertIn("adoption is already complete", rerun[1])
            manifest = json.loads((target / "migration-manifest.json").read_text())
            self.assertEqual(manifest["source"], "canonical-existing")
            self.assertEqual(manifest["operations"], [])
            self.assertFalse(manifest["secret_values_included"])
            self.assertTrue((values / ".env").exists())
            self.assertTrue((values / "terraform.tfvars").exists())

    def test_site_identifier_rejects_path_traversal(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            with self.assertRaises(migration.SiteMigrationError):
                migration.migrate(values, values.parent, "../prod", "production", "persistent", True, False, False)

    def test_existing_compatible_site_is_a_dry_run_noop(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            target = values / "sites" / "dev"
            target.mkdir(parents=True)
            metadata = migration.site_metadata(values.parent, "dev", "development", "disposable", True, True)
            (target / "site.json").write_text(json.dumps(metadata), encoding="utf-8")
            (target / "migration-manifest.json").write_text(
                json.dumps({"canonical_destination": "sites/dev", "secret_values_included": False}),
                encoding="utf-8",
            )
            (target / ".env").write_text("SERVER_NAME=dns.example.internal\n", encoding="utf-8")
            actions = migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, False)
            self.assertEqual(actions[2], "no-op: site migration is already complete")
            self.assertEqual(actions[1], "site artifact inventory: 1 files")
            self.assertTrue((values / ".env").exists())

    def test_existing_site_metadata_conflict_fails_closed_in_dry_run(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            target = values / "sites" / "dev"
            target.mkdir(parents=True)
            (target / "site.json").write_text("{\"name\": \"other\"}", encoding="utf-8")
            (target / "migration-manifest.json").write_text(
                json.dumps({"canonical_destination": "sites/dev", "secret_values_included": False}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(migration.SiteMigrationError, "metadata conflicts"):
                migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, False)

    def test_existing_site_is_never_overwritten(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            (values / "sites" / "dev").mkdir(parents=True)
            with self.assertRaises(migration.SiteMigrationError):
                migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True)


if __name__ == "__main__":
    unittest.main()

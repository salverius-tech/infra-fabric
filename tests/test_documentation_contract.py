import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def _heading_anchor(value: str) -> str:
    """Match GitHub-style Markdown fragment identifiers for local documents."""
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.lower()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    return re.sub(r"[\s-]+", "-", value).strip("-")


def _document_anchors(path: Path) -> set[str]:
    counts: dict[str, int] = {}
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if match is None:
            continue
        base = _heading_anchor(match.group(1))
        suffix = counts.get(base, 0)
        counts[base] = suffix + 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


class DocumentationContractTests(unittest.TestCase):
    def test_documentation_inventory_covers_every_tracked_markdown_file(self) -> None:
        inventory = json.loads((ROOT / "docs" / "documentation-inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(inventory["schema_version"], 2)
        self.assertEqual(
            inventory["classifications"],
            [
                "current authority",
                "operator guidance",
                "working design",
                "implementation tracker",
                "acceptance evidence",
                "historical reference",
                "superseded",
            ],
        )
        documents = inventory["documents"]
        if shutil.which("git"):
            tracked = {
                relative
                for relative in subprocess.check_output(
                    ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
                    text=True,
                ).splitlines()
                # A P10-A artifact can be deleted before its successor is staged.
                # Inventory validation must describe the actual working tree, not a
                # stale index entry that no longer has a document to classify.
                if (ROOT / relative).is_file()
            }
        else:
            ignored_roots = {".git", "values", ".venv", ".tmp", ".terraform"}
            tracked = {
                path.relative_to(ROOT).as_posix()
                for path in ROOT.rglob("*.md")
                if not ignored_roots.intersection(path.parts)
            }
        self.assertEqual(set(documents), tracked)
        self.assertTrue(set(inventory["classifications"]).issuperset(documents.values()))
        for relative, classification in documents.items():
            self.assertIn(classification, inventory["classifications"], relative)
            self.assertTrue((ROOT / relative).is_file(), relative)
        for relative, replacement in inventory["successors"].items():
            self.assertIn(relative, documents)
            self.assertIn(replacement, documents)
            self.assertNotEqual(relative, replacement)
        for relative, classification in documents.items():
            if classification == "superseded":
                self.assertIn(relative, inventory["successors"])
        for relative, replacement in inventory["historical_remove"].items():
            self.assertFalse((ROOT / relative).exists(), relative)
            self.assertTrue((ROOT / replacement).is_file(), replacement)

    def test_tracked_markdown_relative_links_and_anchors_resolve(self) -> None:
        inventory = json.loads((ROOT / "docs" / "documentation-inventory.json").read_text(encoding="utf-8"))
        maintained = {"current authority", "operator guidance", "working design", "implementation tracker"}
        for relative, classification in inventory["documents"].items():
            if classification not in maintained:
                continue
            source = ROOT / relative
            for raw_link in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
                if "://" in raw_link or raw_link.startswith(("mailto:", "#")):
                    if raw_link.startswith("#"):
                        self.assertIn(raw_link.removeprefix("#"), _document_anchors(source), f"{relative}: {raw_link}")
                    continue
                path_part, separator, fragment = raw_link.partition("#")
                target = (source.parent / path_part).resolve()
                self.assertTrue(target.is_file(), f"{relative}: {raw_link}")
                if separator and target.suffix == ".md":
                    self.assertIn(fragment, _document_anchors(target), f"{relative}: {raw_link}")

        index = ROOT / "docs" / "README.md"
        text = index.read_text(encoding="utf-8")
        for retired in ("upstream", "repository-audit", "phase0", "mapping-v1"):
            self.assertNotIn(retired, text.lower())

    def test_retired_implementation_trackers_are_not_active_backlog_authorities(self) -> None:
        inventory = json.loads((ROOT / "docs" / "documentation-inventory.json").read_text(encoding="utf-8"))
        matrix = json.loads((ROOT / "docs" / "governance" / "acceptance-matrix.json").read_text(encoding="utf-8"))
        development = matrix["rows"]["development"]
        self.assertEqual(
            {
                category
                for category, status in development.items()
                if status == "evidenced"
            },
            {"plan", "apply", "health-idempotence", "service-restore", "infrastructure-recovery", "hermes-integration", "rollback"},
        )
        self.assertTrue(all(status == "not-evidenced" for status in matrix["rows"]["isolated-recovery"].values()))
        self.assertTrue(all(status == "not-evidenced" for status in matrix["rows"]["production"].values()))

        prd = (ROOT / "docs" / "hermes-operator-pilot-prd.md").read_text(encoding="utf-8")
        for evidenced in (
            "plan, apply, health/idempotence, service restore, infrastructure recovery",
            "read-only Hermes integration",
            "Hermes rollback evidence",
        ):
            self.assertIn(evidenced, prd)
        for unevidenced in (
            "Provider-equivalence",
            "isolated-recovery",
            "production",
            "external audit durability",
            "authenticated dashboard/API and WebSocket acceptance",
            "mutation approval identity",
            "live search smoke",
        ):
            self.assertIn(unevidenced, prd)
        self.assertNotIn("not yet provider-equivalence, Hermes live-integration", prd)

    def test_installed_scaffold_readme_has_no_broken_relative_document_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / "values"
            shutil.copytree(ROOT / "scaffold", installed)
            readme = installed / "README.md"
            links = re.findall(r"\]\(([^)#]+)", readme.read_text(encoding="utf-8"))
            for link in links:
                if "://" not in link:
                    self.assertTrue((readme.parent / link).is_file(), link)

    def test_operator_onramps_declare_tool_and_platform_prerequisites(self) -> None:
        required = ("Linux `amd64`", "Git", "`just`", "Docker Engine", "Compose plugin")
        for relative in ("README.md", "docs/canonical-quick-start.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for marker in required:
                self.assertIn(marker, text, f"{marker!r} missing from {relative}")

    def test_current_operator_docs_are_canonical_first(self) -> None:
        required = (
            "values/sites/<site>/site.yaml",
            "values/sites/<site>/secrets.sops.yaml",
            "VALUES_SITE=<site>",
            "just validate",
            "just plan",
            "just apply",
        )
        for relative in ("README.md", "docs/canonical-quick-start.md", "docs/just-recipes.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for marker in required:
                self.assertIn(marker, text, f"{marker!r} missing from {relative}")

    def test_hermes_independent_recovery_doc_preserves_fail_closed_order(self) -> None:
        recovery = (ROOT / "docs" / "hermes-independent-recovery.md").read_text(encoding="utf-8")
        required = (
            "Hermes is an operator surface, not a recovery dependency",
            "This is a public-safe procedure",
            "Restore public source",
            "Restore private site inputs",
            "Restore audit continuity",
            "Restore state and trust metadata",
            "Run non-mutating checks",
            "Re-establish infrastructure control",
            "Converge services and recover Hermes last",
            "hash chain is a stop condition",
            "Never accept a changed guest host key from scanning alone",
            "canonical wrapper after separate approval",
        )
        for marker in required:
            self.assertIn(marker, recovery, marker)
        self.assertLess(recovery.index("Restore public source"), recovery.index("Restore private site inputs"))
        self.assertLess(recovery.index("Restore audit continuity"), recovery.index("Re-establish infrastructure control"))
        self.assertLess(recovery.index("Run non-mutating checks"), recovery.index("Re-establish infrastructure control"))
        self.assertLess(recovery.index("Re-establish infrastructure control"), recovery.index("Converge services and recover Hermes last"))

    def test_current_docs_do_not_teach_retired_authoring_surfaces(self) -> None:
        files = (
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "scaffold" / "README.md",
            ROOT / "docs" / "canonical-quick-start.md",
            ROOT / "docs" / "just-recipes.md",
            ROOT / "docs" / "canonical-service-authoring.md",
        )
        banned = (
            "values/terraform.tfvars",
            "values/.env",
            "values/ansible/inventory/local.yml",
            "settings.local.json",
        )
        for path in files:
            text = path.read_text(encoding="utf-8")
            for marker in banned:
                self.assertNotIn(marker, text, f"retired authoring path in {path}")

    def test_every_public_just_recipe_is_documented(self) -> None:
        docs = (ROOT / "docs" / "just-recipes.md").read_text(encoding="utf-8")
        recipes = (
            "apply",
            "default",
            "edit-secrets",
            "plan",
            "setup",
            "ssh-initialize",
            "teardown-apply",
            "teardown-plan",
            "update",
            "validate",
        )
        headings = {
            line.removeprefix("## ").strip().strip("`").split()[0]
            for line in docs.splitlines()
            if line.startswith("## ")
        }
        for recipe in recipes:
            self.assertIn(recipe, headings, recipe)

    def test_lifecycle_examples_have_site_context(self) -> None:
        docs = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in ("README.md", "docs/canonical-quick-start.md", "docs/just-recipes.md", "docs/service-update-policy.md")
        )
        for recipe in ("validate", "plan", "apply", "update"):
            self.assertRegex(docs, rf"VALUES_SITE=<site>[^\n]*just {recipe}|export VALUES_SITE=<site>", recipe)
        update_policy = (ROOT / "docs/service-update-policy.md").read_text(encoding="utf-8")
        for recipe in ("update", "validate", "plan", "apply"):
            self.assertRegex(update_policy, rf"VALUES_SITE=<site> just {recipe}", recipe)

    def test_apply_docs_distinguish_canonical_proxmox_identity_from_guest_bootstrap(self) -> None:
        for relative in ("docs/canonical-quick-start.md", "docs/just-recipes.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("secrets.providers.proxmox.ssh_private_key", text, relative)
            self.assertIn("platform.proxmox.management.ssh_public_key", text, relative)
            self.assertIn("guest bootstrap identity", text, relative)
            self.assertNotIn("INFRA_PVE_SSH_IDENTITY_FILE", text, relative)
            self.assertIn("guest bootstrap key", text.lower(), relative)

    def test_operator_bash_lifecycle_examples_establish_site_context(self) -> None:
        inventory = json.loads((ROOT / "docs" / "documentation-inventory.json").read_text(encoding="utf-8"))
        for relative, classification in inventory["documents"].items():
            if classification != "operator guidance":
                continue
            lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
            in_bash = False
            has_context = False
            for line in lines:
                if line.startswith("```bash"):
                    in_bash = True
                    has_context = False
                    continue
                if in_bash and line.startswith("```"):
                    in_bash = False
                    continue
                if not in_bash:
                    continue
                if "VALUES_SITE=<site>" in line or "export VALUES_SITE=" in line:
                    has_context = True
                if re.search(r"\bjust (validate|plan|apply|update)\b", line):
                    self.assertTrue(has_context, f"missing site context in {relative}: {line.strip()}")

    def test_service_operations_matrix_covers_the_catalog_and_day_two_contract(self) -> None:
        catalog = json.loads((ROOT / "infra" / "services.json").read_text(encoding="utf-8"))["services"]
        matrix = (ROOT / "docs" / "service-operations.md").read_text(encoding="utf-8")
        self.assertIn("infra/services.json", matrix)
        self.assertIn("external evidence required", matrix)
        self.assertIn("Health and logs", matrix)
        for service, metadata in catalog.items():
            rows = [line for line in matrix.splitlines() if line.startswith(f"| `{service}` |")]
            self.assertEqual(len(rows), 1, service)
            row = rows[0]
            self.assertIn("catalog:", row.lower(), service)
            if metadata["state_capable"]:
                self.assertIn("state-capable", row, service)
            else:
                self.assertIn("N/A/unsupported", row, service)

    def test_operator_command_snippets_preserve_supported_boundaries(self) -> None:
        matrix = (ROOT / "docs" / "service-operations.md").read_text(encoding="utf-8")
        migration = (ROOT / "docs" / "canonical-model-operations.md").read_text(encoding="utf-8")
        troubleshooting = (ROOT / "docs" / "canonical-troubleshooting.md").read_text(encoding="utf-8")
        for command in ("VALUES_SITE=<site> just validate", "VALUES_SITE=<site> just plan", "VALUES_SITE=<site> just apply"):
            self.assertIn(command, matrix)
            self.assertIn(command, migration)
        for prohibited in ("raw OpenTofu/Terraform", "site.yml"):
            self.assertIn(prohibited, matrix)
            self.assertIn(prohibited, migration)
        for stage in ("canonical-input", "provider-plan", "host-trust", "service-health", "state-recovery"):
            self.assertIn(stage, matrix)
            self.assertIn(stage, troubleshooting)

    def test_service_state_operator_docs_use_selected_site_paths(self) -> None:
        for relative in ("docs/service-operations.md", "docs/service-state-backup.md", "docs/hermes-state-backup.md", "docs/sssf.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("VALUES_SITE=<site> scripts/service-state.sh", text, relative)
            self.assertNotIn(" values/service-backups/", text, relative)
        hermes = (ROOT / "docs/hermes-state-backup.md").read_text(encoding="utf-8")
        self.assertIn("VALUES_SITE=<site> scripts/hermes-state.sh", hermes)
        shared = (ROOT / "docs/service-state-backup.md").read_text(encoding="utf-8")
        self.assertIn("values/sites/<site>/service-backups/", shared)

    def test_sssf_maintained_doc_preserves_upstream_and_runtime_boundaries(self) -> None:
        sssf = (ROOT / "docs" / "sssf.md").read_text(encoding="utf-8")
        required = (
            "Pinned upstream artifacts remain unmodified",
            "`install.py`",
            "`adws/`",
            "`.claude/skills/sssf/`",
            "`sssf.config.yaml`",
            "single provider",
            "`bun run server/index.ts`",
            "non-`--force` upstream install",
            "future pin-update compatibility workflow",
            "must not be treated as live acceptance evidence",
        )
        for marker in required:
            self.assertIn(marker, sssf, marker)
        self.assertIn("/usr/local/bin/sssf-init https://host/org/repo", sssf)
        self.assertIn("must not supply the optional workspace argument", sssf)

    def test_maintained_docs_do_not_present_legacy_or_ambient_authority_as_normal(self) -> None:
        prd = (ROOT / "docs/hermes-operator-pilot-prd.md").read_text(encoding="utf-8")
        self.assertIn("Private selected-site inputs", prd)
        self.assertNotIn("current tfvars, inventory, DNS records, environment values", prd)

        sssf = (ROOT / "docs/sssf.md").read_text(encoding="utf-8")
        self.assertIn("must not use an ambient inventory", sssf)
        self.assertNotRegex(sssf, r"(?m)^ansible\s+sssf\b")

        state = (ROOT / "docs/service-state-backup.md").read_text(encoding="utf-8")
        self.assertIn("generated inventory and variables", state)
        self.assertNotIn("normal direct Ansible inventory group", state)



if __name__ == "__main__":
    unittest.main()

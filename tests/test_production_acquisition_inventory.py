"""Source-only contract for production image and network-acquisition consumers."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/production-acquisition-inventory.json"
CANONICAL_VALUES = ROOT / "scripts/canonical_values.py"

# These patterns intentionally find consumer *files*, not every URL: one source file
# may contain a health probe and several downloads.  Every discovered file must have
# an explicit inventory record before it can be treated as reviewed.
ACQUISITION_PATTERNS = (
    re.compile(r"\bansible\.builtin\.(?:get_url|git|apt_repository)\b"),
    re.compile(r"\bgit clone\b"),
    re.compile(r"\bcurl\s+-[^\n]*\b(?:https?://|\$\{(?:[A-Za-z_][A-Za-z0-9_]*|[^}]+)\})"),
    re.compile(r"^FROM\s+", re.MULTILINE),
    re.compile(r"^\s*image:\s+", re.MULTILINE),
)
EXCLUDED_PREFIXES = ("tests/", "scaffold/", "docs/", ".hermes/", ".specs/")
DEPLOYMENT_PREFIXES = ("infra/", "tools/")
# OpenTofu resource declarations do not use one of the textual download primitives
# above, but they are production image-acquisition authorities.
REQUIRED_IMAGE_AUTHORITIES = {
    "infra/opentofu/services.tf",
    "infra/opentofu/onramp-host.tf",
    "infra/opentofu/variables.tf",
}
# These roles consume an executable from the reviewed controller cache rather than a
# URL, so the primitive discovery above intentionally cannot infer the boundary.
REQUIRED_REVIEWED_CACHE_AUTHORITIES = {
    "infra/ansible/roles/caddy_proxy/tasks/main.yml",
    "infra/ansible/roles/forgejo/tasks/caddy.yml",
    "infra/ansible/roles/hermes/tasks/main.yml",
    "infra/ansible/roles/infisical/tasks/main.yml",
    "infra/ansible/roles/onramp_host/tasks/main.yml",
    "infra/ansible/roles/forgejo_runner/tasks/main.yml",
}
# Setup can clone an operator-selected private values repository; it is a real
# network acquisition boundary even though its remote is intentionally not public.
ADDITIONAL_NETWORK_CONSUMERS = {"scripts/values.sh"}
EXPECTED_CONTRACTS = {
    "checksum",
    "immutable-commit",
    "immutable-digest",
    "canonical-digest-contract",
    "signed-repository",
    "distro-package-policy",
    "reviewed-controller-cache",
    "operator-private-boundary",
    "removed",
}


def tracked_deployment_sources() -> set[str]:
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.splitlines()
    candidates: set[str] = set()
    for relative in files:
        if relative.startswith(EXCLUDED_PREFIXES) or not relative.startswith(DEPLOYMENT_PREFIXES):
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in ACQUISITION_PATTERNS):
            candidates.add(relative)
    return candidates | REQUIRED_IMAGE_AUTHORITIES | REQUIRED_REVIEWED_CACHE_AUTHORITIES | ADDITIONAL_NETWORK_CONSUMERS


class ProductionAcquisitionInventoryTests(unittest.TestCase):
    def load_inventory(self) -> dict:
        return json.loads(INVENTORY.read_text(encoding="utf-8"))

    def test_inventory_covers_every_tracked_deployment_acquisition_source(self) -> None:
        inventory = self.load_inventory()
        recorded = {entry["source"] for entry in inventory["consumers"]}
        self.assertEqual(tracked_deployment_sources(), recorded)

    def test_records_are_explicit_about_integrity_and_unresolved_work(self) -> None:
        inventory = self.load_inventory()
        self.assertEqual(inventory["schema_version"], 2)
        self.assertTrue(inventory["consumers"])
        for entry in inventory["consumers"]:
            self.assertEqual(set(entry), {"source", "consumer", "acquisitions"})
            self.assertTrue(entry["consumer"])
            self.assertTrue(entry["acquisitions"])
            for acquisition in entry["acquisitions"]:
                self.assertEqual(
                    set(acquisition),
                    {"name", "contract", "evidence", "disposition"},
                )
                self.assertIn(acquisition["contract"], EXPECTED_CONTRACTS)
                self.assertTrue(acquisition["evidence"])
                self.assertTrue(acquisition["disposition"])
                if acquisition["contract"] == "unresolved":
                    self.assertIn("unresolved", acquisition["disposition"].lower())

    def test_canonical_digest_contract_is_backed_by_the_model(self) -> None:
        inventory = self.load_inventory()
        self.assertTrue(
            any(
                acquisition["contract"] == "canonical-digest-contract"
                for entry in inventory["consumers"]
                for acquisition in entry["acquisitions"]
            )
        )
        text = CANONICAL_VALUES.read_text(encoding="utf-8")
        self.assertIn("container image must use repository@sha256:digest", text)
        self.assertIn("container image digest must be lowercase sha256", text)

    def test_digest_and_checksum_claims_are_backed_by_source_syntax(self) -> None:
        inventory = self.load_inventory()
        for entry in inventory["consumers"]:
            text = (ROOT / entry["source"]).read_text(encoding="utf-8")
            for acquisition in entry["acquisitions"]:
                if acquisition["contract"] == "immutable-digest":
                    self.assertRegex(text, r"@sha256:[0-9a-f]{64}", entry["source"])
                if acquisition["contract"] == "checksum":
                    self.assertRegex(
                        text,
                        r"(?:checksum|sha256sum)[^\n]{0,180}(?:sha256|SHA256)|(?:sha256|SHA256)[^\n]{0,180}(?:checksum|sha256sum)",
                        entry["source"],
                    )


    def test_nodesource_key_contract_rejects_unpinned_or_wrong_fingerprint_inputs(self) -> None:
        task = (ROOT / "infra/ansible/roles/sssf/tasks/main.yml").read_text(encoding="utf-8")
        defaults = (ROOT / "infra/ansible/roles/sssf/defaults/main.yml").read_text(encoding="utf-8")
        self.assertIn("sssf_nodesource_key_sha256 is match('^[0-9a-f]{64}$')", task)
        self.assertIn("sssf_nodesource_key_fingerprint is match('^[0-9A-F]{40}$')", task)
        self.assertLess(task.index("sha256sum -c -"), task.index("gpg --dearmor"))
        self.assertLess(task.index("gpg --show-keys --with-colons"), task.index("gpg --dearmor"))
        self.assertRegex(defaults, r"sssf_nodesource_key_sha256: [0-9a-f]{64}")
        self.assertRegex(defaults, r"sssf_nodesource_key_fingerprint: [0-9A-F]{40}")

    def test_owned_acquisitions_are_resolved_and_only_private_boundaries_remain(self) -> None:
        inventory = self.load_inventory()
        contracts = [a["contract"] for e in inventory["consumers"] for a in e["acquisitions"]]
        self.assertNotIn("unresolved", contracts)
        self.assertEqual(contracts.count("operator-private-boundary"), 2)
        for source in REQUIRED_REVIEWED_CACHE_AUTHORITIES | {"infra/ansible/roles/forgejo_runner/tasks/main.yml"}:
            self.assertIn("reviewed-artifact-cache.yml", (ROOT / source).read_text(encoding="utf-8"))
        raw_installers = ("curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash", "curl -fsSL -o /usr/local/lib/docker/cli-plugins", "curl -fsSL -o \"${tmp}/just.tar.gz\"")
        deployment = "\n".join((ROOT / source).read_text(encoding="utf-8") for source in REQUIRED_REVIEWED_CACHE_AUTHORITIES | {"infra/ansible/roles/forgejo_runner/tasks/main.yml"})
        for forbidden in raw_installers:
            self.assertNotIn(forbidden, deployment)


if __name__ == "__main__":
    unittest.main()

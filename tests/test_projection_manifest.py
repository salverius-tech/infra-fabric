from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from projection_manifest import ManifestError, build_manifest, verify_manifest


class ProjectionManifestTests(unittest.TestCase):
    def manifest(self) -> tuple[dict, dict[str, object]]:
        projections = {
            "terraform.auto.tfvars.json": {"enabled_services": ["forgejo"]},
            "ansible-inventory.json": {"all": {"children": ["forgejo"]}},
            "dns-records.json": {"a_records": {"git.example.internal": "192.0.2.62"}},
        }
        return (
            build_manifest(
                site="dev",
                schema_version=1,
                model_digest="model-digest",
                secret_digest="secret-digest",
                projections=projections,
                renderer_version="canonical-renderer/0.1",
                source_commit="source-commit",
            ),
            projections,
        )

    def test_manifest_verifies_unchanged_projection_set(self) -> None:
        manifest, projections = self.manifest()
        verify_manifest(
            manifest,
            site="dev",
            model_digest="model-digest",
            secret_digest="secret-digest",
            projections=projections,
        )
        self.assertEqual(len(manifest["projection_digest"]), 64)

    def test_wrong_site_and_stale_model_fail_closed(self) -> None:
        manifest, projections = self.manifest()
        with self.assertRaisesRegex(ManifestError, "different site"):
            verify_manifest(
                manifest,
                site="production",
                model_digest="model-digest",
                secret_digest="secret-digest",
                projections=projections,
            )
        with self.assertRaisesRegex(ManifestError, "stale model"):
            verify_manifest(
                manifest,
                site="dev",
                model_digest="new-model",
                secret_digest="secret-digest",
                projections=projections,
            )

    def test_altered_projection_fails_closed(self) -> None:
        manifest, projections = self.manifest()
        altered = {**projections, "dns-records.json": {"a_records": {"git.example.internal": "192.0.2.63"}}}
        with self.assertRaisesRegex(ManifestError, "stale or altered"):
            verify_manifest(
                manifest,
                site="dev",
                model_digest="model-digest",
                secret_digest="secret-digest",
                projections=altered,
            )

    def test_secret_identity_change_fails_closed(self) -> None:
        manifest, projections = self.manifest()
        with self.assertRaisesRegex(ManifestError, "stale secret"):
            verify_manifest(
                manifest,
                site="dev",
                model_digest="model-digest",
                secret_digest="rotated-secret",
                projections=projections,
            )


if __name__ == "__main__":
    unittest.main()

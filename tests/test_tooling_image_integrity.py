"""Static integrity contract for the repository tooling image."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "tools/Dockerfile"


class ToolingImageIntegrityTests(unittest.TestCase):
    def test_base_image_is_multi_arch_digest_pinned(self) -> None:
        first_line = DOCKERFILE.read_text(encoding="utf-8").splitlines()[0]
        self.assertRegex(first_line, r"^FROM debian:bookworm-slim@sha256:[0-9a-f]{64}$")

    def test_direct_tool_downloads_keep_checksum_verification(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        for checksum_arg in (
            "OPENTOFU_LINUX_AMD64_SHA256",
            "TFLINT_LINUX_AMD64_SHA256",
            "SOPS_LINUX_AMD64_SHA256",
        ):
            self.assertRegex(text, rf"ARG {checksum_arg}=[0-9a-f]{{64}}")
            self.assertIn(f'"${{{checksum_arg}}}"', text)
        self.assertEqual(len(re.findall(r"sha256sum -c -", text)), 3)


if __name__ == "__main__":
    unittest.main()

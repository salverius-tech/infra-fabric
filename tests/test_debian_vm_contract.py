"""Static regression coverage for verified Debian VM image ownership."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_MAIN = ROOT / "infra/opentofu/modules/debian-vm/main.tf"
MODULE_VARIABLES = ROOT / "infra/opentofu/modules/debian-vm/variables.tf"
FORGEJO = ROOT / "infra/opentofu/forgejo.tf"
ROOT_TOFU = ROOT / "infra/opentofu/main.tf"


class DebianVmImageContractTests(unittest.TestCase):
    def test_vm_module_accepts_only_externally_verified_image_file_ids(self) -> None:
        main = MODULE_MAIN.read_text(encoding="utf-8")
        variables = MODULE_VARIABLES.read_text(encoding="utf-8")

        self.assertNotIn('resource "proxmox_download_file"', main)
        self.assertIn("image_file_id = var.image.file_id", main)
        self.assertIn("image.file_id must reference a separately checksum-verified Proxmox image.", variables)
        self.assertIn("debian-vm does not download images", variables)
        self.assertIn("condition     = !var.image.create", variables)

    def test_forgejo_vm_reuses_the_checksum_verified_shared_image(self) -> None:
        forgejo = FORGEJO.read_text(encoding="utf-8")
        root_tofu = ROOT_TOFU.read_text(encoding="utf-8")

        self.assertIn('resource "proxmox_download_file" "debian_13_service_vm_image"', root_tofu)
        self.assertIn("checksum            = var.guest_vm_image_checksum", root_tofu)
        self.assertIn("checksum_algorithm  = var.guest_vm_image_checksum_algorithm", root_tofu)
        self.assertIn("proxmox_download_file.debian_13_service_vm_image[0].id", forgejo)
        self.assertIn("create       = false", forgejo)
        self.assertNotIn("forgejo_vm_image_url", forgejo)


if __name__ == "__main__":
    unittest.main()

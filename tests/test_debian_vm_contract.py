"""Static regression coverage for verified Debian VM image ownership."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_MAIN = ROOT / "infra/opentofu/modules/debian-vm/main.tf"
MODULE_VARIABLES = ROOT / "infra/opentofu/modules/debian-vm/variables.tf"
LXC_MODULE_VARIABLES = ROOT / "infra/opentofu/modules/debian-lxc/variables.tf"
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

    def test_vm_module_rejects_invalid_resource_and_network_shapes(self) -> None:
        variables = MODULE_VARIABLES.read_text(encoding="utf-8")
        for contract in (
            "vm_id must be an integer in the Proxmox VMID range",
            "disk requires a non-empty datastore_id and a positive size_gb.",
            "extra_disks interfaces must be unique.",
            "cores must be a positive integer.",
            "memory_mb must be a positive integer.",
            "ipv4_address must be dhcp or an IPv4 CIDR address.",
            "ipv4_gateway must be null or an IPv4 address.",
            "vlan_id must be 1 through 4094.",
        ):
            self.assertIn(contract, variables)

    def test_lxc_module_matches_vm_identity_and_compute_validation(self) -> None:
        variables = LXC_MODULE_VARIABLES.read_text(encoding="utf-8")
        for contract in (
            "vm_id must be an integer in the Proxmox VMID range",
            "cores must be a positive integer.",
            "memory_mb must be a positive integer.",
            "disk requires a non-empty datastore_id and a positive size_gb.",
            "mount_points require non-empty volumes and absolute unique guest paths.",
            "ipv4_address must be dhcp or an IPv4 CIDR address.",
            "ipv4_gateway must be an IPv4 address.",
            "vlan_id must be 1 through 4094.",
        ):
            self.assertIn(contract, variables)

    def test_service_refactor_preserves_legacy_state_addresses(self) -> None:
        services = (ROOT / "infra/opentofu/services.tf").read_text(encoding="utf-8")
        for source, destination in (
            ("proxmox_virtual_environment_container.technitium_dns[0]", "module.technitium_dns[0].proxmox_virtual_environment_container.this"),
            ("proxmox_virtual_environment_container.forgejo[0]", "module.forgejo[0].proxmox_virtual_environment_container.this"),
            ("proxmox_virtual_environment_container.tailscale_client[0]", "module.tailscale_client[0].proxmox_virtual_environment_container.this"),
            ("proxmox_virtual_environment_container.forgejo_runner[0]", "module.forgejo_runner[0].proxmox_virtual_environment_container.this"),
            ("proxmox_virtual_environment_container.infisical[0]", "module.infisical[0].proxmox_virtual_environment_container.this"),
            ("proxmox_virtual_environment_container.hermes[0]", "module.hermes[0].proxmox_virtual_environment_container.this"),
        ):
            self.assertIn(f"from = {source}", services)
            self.assertIn(f"to   = {destination}", services)


if __name__ == "__main__":
    unittest.main()

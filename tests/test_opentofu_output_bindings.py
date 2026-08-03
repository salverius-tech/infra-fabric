"""Regression coverage for canonical network-backed OpenTofu outputs."""

from pathlib import Path
import unittest


class OpenTofuOutputBindingsTests(unittest.TestCase):
    def test_static_lan_outputs_derive_from_resource_address_variables(self) -> None:
        outputs = (Path(__file__).resolve().parents[1] / "infra" / "opentofu" / "outputs.tf").read_text()

        self.assertIn(
            'var.infisical_container_ipv4_address == "dhcp" ? var.infisical_lan_ip : split("/", var.infisical_container_ipv4_address)[0]',
            outputs,
        )
        self.assertIn(
            'var.hermes_container_ipv4_address == "dhcp" ? var.hermes_lan_ip : split("/", var.hermes_container_ipv4_address)[0]',
            outputs,
        )


if __name__ == "__main__":
    unittest.main()

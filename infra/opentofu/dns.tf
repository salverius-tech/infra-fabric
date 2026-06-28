locals {
  dns_records_path = abspath("${path.module}/${var.dns_records_file}")
}

resource "terraform_data" "technitium_dns" {
  count = local.technitium_enabled ? 1 : 0

  input            = local.dns_records_path
  triggers_replace = filesha256(local.dns_records_path)

  provisioner "local-exec" {
    working_dir = path.module
    interpreter = ["/usr/bin/env", "bash", "-c"]
    command     = "set -euo pipefail; exec python scripts/apply-technitium-dns.py \"$DNS_RECORDS_FILE\""

    environment = {
      DNS_RECORDS_FILE     = local.dns_records_path
      TECHNITIUM_API_URL   = var.technitium_api_url
      TECHNITIUM_API_TOKEN = var.technitium_api_token
    }
  }
}

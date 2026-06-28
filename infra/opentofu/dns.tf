resource "terraform_data" "technitium_dns" {
  input = filesha256("${path.module}/${var.dns_records_file}")

  provisioner "local-exec" {
    command = "python scripts/apply-technitium-dns.py ${var.dns_records_file}"

    environment = {
      TECHNITIUM_API_URL   = var.technitium_api_url
      TECHNITIUM_API_TOKEN = var.technitium_api_token
    }
  }
}

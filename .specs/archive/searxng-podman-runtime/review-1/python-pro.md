[
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "Wave 1 validation can be impossible before Ansible inventory/playbook work exists.",
    "evidence": "Plan runs V1 after T1-T3 and before T4, but tests/test_service_registry_parity.py requires set(settings_script.SERVICES) == set(tfvars_inventory.SERVICE_HOSTS) and every all_ansible_playbooks() path to exist. Adding onramp_host in scripts/settings.py at T1 without infra/ansible/inventory/tfvars.py and onramp-host.yml until T4 will fail repo validation.",
    "required_fix": "Move minimal onramp_host inventory mapping and playbook path/file creation into Wave 1, or change wave gates so parity tests/just validate run only after T4.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "Migration may never add onramp_host defaults for real enabled settings, leaving private values incomplete.",
    "evidence": "scripts/migrate-values.py enabled_optional_services() currently returns only services in (\"infisical\", \"hermes\") and only when values_dir == Path(\"values\"). Plan T3 says add onramp-host migration defaults but does not require changing this service filter or testing onramp_host enabled/disabled behavior.",
    "required_fix": "Add explicit T3 criteria/tests: onramp_host in settings.local.json triggers onramp_host tfvars/env/DNS additions, absence does not, and a second migrate run returns no changes.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "medium",
    "severity_rationale": "Service dependency behavior is unspecified, so executors may change Hermes/onramp_host selection semantics accidentally.",
    "evidence": "scripts/settings.py encodes dependencies in SERVICES; only forgejo_runner currently depends on forgejo. The plan says Hermes consumes SearXNG on onramp_host, but T1/T7 never state whether hermes requires onramp_host or remains independently selectable when HERMES_WEB_SEARXNG_URL points elsewhere.",
    "required_fix": "Add acceptance tests documenting the intended contract: either hermes without onramp_host still validates, or hermes requires onramp_host with updated settings.example.json and error-message tests.",
    "confidence": "medium"
  },
  {
    "category": "process defect",
    "severity": "medium",
    "severity_rationale": "Non-secret output checks are too weak for this repo's privacy model.",
    "evidence": "AGENTS.md forbids printing real domains/IPs/hostnames. Plan T3 only says migrations should avoid printing secrets. scripts/migrate-values.py main prints each change string verbatim, so any new onramp_host/HERMES_WEB_SEARXNG_URL change message containing a value would leak private inventory.",
    "required_fix": "Require migration stdout tests proving change messages contain only key names/generic labels, not URL, hostname, IP, token, or generated value content.",
    "confidence": "high"
  }
]

#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

api_url = os.environ["TECHNITIUM_API_URL"].rstrip("/")
token = os.environ["TECHNITIUM_API_TOKEN"]
headers = {"Authorization": f"Bearer {token}"}
config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
zones = config["zones"]


def call(path: str, params: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(
        f"{api_url}{path}", data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode()
    result = json.loads(body)
    if result.get("status") != "ok":
        raise RuntimeError(result)
    return result


def zone_for(domain: str) -> str:
    matches = [zone for zone in zones if domain == zone or domain.endswith(f".{zone}")]
    if not matches:
        raise ValueError(f"No configured zone for {domain}")
    return max(matches, key=len)


def bool_param(value: bool) -> str:
    return "true" if value else "false"


settings = config.get("settings")
if settings:
    call(
        "/settings/set",
        {
            "forwarders": ",".join(settings["forwarders"]),
            "forwarderProtocol": settings["forwarderProtocol"],
            "concurrentForwarding": bool_param(settings["concurrentForwarding"]),
            "dnssecValidation": bool_param(settings["dnssecValidation"]),
            "preferIPv6": bool_param(settings["preferIPv6"]),
        },
    )
    print("configured upstream DNS forwarders")


for zone, forwarders in zones.items():
    try:
        call(
            "/zones/create",
            {"zone": zone, "type": "Forwarder", "initializeForwarder": "false"},
        )
        print(f"created zone {zone}")
    except RuntimeError as error:
        message = str(error).lower()
        if "already" in message or "exists" in message:
            print(f"zone exists {zone}")
        else:
            raise

    for index, forwarder in enumerate(forwarders):
        call(
            "/zones/records/add",
            {
                "zone": zone,
                "domain": zone,
                "type": "FWD",
                "ttl": "300",
                "overwrite": "true" if index == 0 else "false",
                "protocol": "Udp",
                "forwarder": forwarder,
                "forwarderPriority": "1",
                "dnssecValidation": "false",
                "proxyType": "NoProxy",
            },
        )
    print(f"configured forwarders {zone}")

for domain, ip_address in config["a_records"].items():
    call(
        "/zones/records/add",
        {
            "zone": zone_for(domain),
            "domain": domain,
            "type": "A",
            "ttl": "300",
            "overwrite": "true",
            "ipAddress": ip_address,
        },
    )
    print(f"upserted A {domain}")

for domain, cname in config["cname_records"].items():
    call(
        "/zones/records/add",
        {
            "zone": zone_for(domain),
            "domain": domain,
            "type": "CNAME",
            "ttl": "300",
            "overwrite": "true",
            "cname": cname,
        },
    )
    print(f"upserted CNAME {domain}")

"""
checker.py
----------
Deterministic, rule-based network error checker.

This module NEVER calls an LLM. It uses plain Python string matching
and regular expressions to detect common, well-known Cisco
troubleshooting signatures inside "show" command output.

Because it is deterministic, its results are reproducible and are used
as trustworthy "ground evidence" that is later handed to the AI engine
(engine.py) to build its diagnosis on top of.

IMPORTANT:
The absence of a detected rule does NOT mean the network is correct.
It only means this checker did not recognize a known pattern. The
AI diagnosis step and the human reviewer are still responsible for
further analysis.
"""

from __future__ import annotations

import re
from typing import TypedDict


class CheckerError(TypedDict):
    type: str
    severity: str
    message: str
    evidence: str


class CheckerResult(TypedDict):
    status: str
    errors: list[CheckerError]


# ---------------------------------------------------------------------------
# Individual rule functions.
# Each rule receives the raw show_output text and returns a list of
# CheckerError dicts (possibly empty).
# ---------------------------------------------------------------------------


def _rule_admin_down(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    for match in re.finditer(
        r"^(?P<iface>\S+)\s+is\s+administratively down.*$", text, re.MULTILINE | re.IGNORECASE
    ):
        line = match.group(0).strip()
        errors.append(
            {
                "type": "INTERFACE_ADMIN_DOWN",
                "severity": "HIGH",
                "message": f"{match.group('iface')} is administratively down.",
                "evidence": line,
            }
        )
    return errors


def _rule_interface_down(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    for match in re.finditer(
        r"^(?P<iface>\S+)\s+is\s+down,\s+line protocol is down.*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    ):
        line = match.group(0).strip()
        errors.append(
            {
                "type": "INTERFACE_DOWN",
                "severity": "HIGH",
                "message": f"{match.group('iface')} is down (line protocol down).",
                "evidence": line,
            }
        )
    # Switch "status" table style: "Fa0/3 notconnect"
    for match in re.finditer(
        r"^(?P<iface>\S+)\s+notconnect\b.*$", text, re.MULTILINE | re.IGNORECASE
    ):
        line = match.group(0).strip()
        errors.append(
            {
                "type": "INTERFACE_DOWN",
                "severity": "HIGH",
                "message": f"{match.group('iface')} shows notconnect status.",
                "evidence": line,
            }
        )
    return errors


def _rule_duplicate_ip(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    ip_addresses = re.findall(r"IP Address:\s*(\d{1,3}(?:\.\d{1,3}){3})", text, re.IGNORECASE)
    seen: dict[str, int] = {}
    for ip in ip_addresses:
        seen[ip] = seen.get(ip, 0) + 1
    for ip, count in seen.items():
        if count > 1:
            errors.append(
                {
                    "type": "DUPLICATE_IP",
                    "severity": "HIGH",
                    "message": f"IP address {ip} appears to be assigned to more than one host.",
                    "evidence": f"IP Address: {ip} (seen {count} times)",
                }
            )
    return errors


def _rule_subnet_mask_mismatch(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    masks = re.findall(r"Subnet Mask:\s*(\d{1,3}(?:\.\d{1,3}){3})", text, re.IGNORECASE)
    unique_masks = set(masks)
    if len(unique_masks) > 1:
        errors.append(
            {
                "type": "SUBNET_MASK_MISMATCH",
                "severity": "MEDIUM",
                "message": "Multiple different subnet masks were found among hosts that appear to be on the same segment.",
                "evidence": f"Subnet masks found: {', '.join(sorted(unique_masks))}",
            }
        )
    return errors


def _rule_gateway_mismatch(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    gateways = re.findall(r"Default Gateway:\s*(\d{1,3}(?:\.\d{1,3}){3})", text, re.IGNORECASE)
    router_ips = re.findall(
        r"GigabitEthernet\S*\s+(\d{1,3}(?:\.\d{1,3}){3})\s+", text, re.IGNORECASE
    )
    for gw in gateways:
        if router_ips and gw not in router_ips:
            errors.append(
                {
                    "type": "GATEWAY_MISMATCH",
                    "severity": "MEDIUM",
                    "message": f"Configured default gateway {gw} does not match any router interface address found in the evidence.",
                    "evidence": f"Default Gateway: {gw}",
                }
            )
    return errors


def _rule_missing_vlan(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    if re.search(r"vlan\s+\d+\s+not listed", text, re.IGNORECASE) or re.search(
        r"\(VLAN \d+ not listed\)", text, re.IGNORECASE
    ):
        errors.append(
            {
                "type": "MISSING_VLAN",
                "severity": "HIGH",
                "message": "A referenced VLAN does not appear in the VLAN database.",
                "evidence": "VLAN not listed in 'show vlan brief' output.",
            }
        )
    return errors


def _rule_vlan_mismatch(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    if re.search(r"encapsulation dot1Q\s+\d+", text, re.IGNORECASE):
        tags = re.findall(r"encapsulation dot1Q\s+(\d+)", text, re.IGNORECASE)
        iface_vlan_hints = re.findall(r"GigabitEthernet\S*\.(\d+)", text)
        for tag, hint in zip(tags, iface_vlan_hints):
            if tag != hint:
                errors.append(
                    {
                        "type": "VLAN_MISMATCH",
                        "severity": "HIGH",
                        "message": f"Sub-interface number (.{hint}) does not match its dot1Q encapsulation tag ({tag}).",
                        "evidence": f"encapsulation dot1Q {tag} on a .{hint} sub-interface",
                    }
                )
    return errors


def _rule_missing_route(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    if re.search(r"\(no route to [\d./]+\)", text, re.IGNORECASE) or re.search(
        r"not present\)", text, re.IGNORECASE
    ) or re.search(r"\(no other routes present\)", text, re.IGNORECASE):
        for match in re.finditer(r"\(no route to ([\d./]+)\)", text, re.IGNORECASE):
            errors.append(
                {
                    "type": "MISSING_ROUTE",
                    "severity": "HIGH",
                    "message": f"No route was found to network {match.group(1)}.",
                    "evidence": match.group(0),
                }
            )
        if re.search(r"\(no other routes present\)", text, re.IGNORECASE):
            errors.append(
                {
                    "type": "MISSING_ROUTE",
                    "severity": "HIGH",
                    "message": "Routing table only contains directly connected networks; remote routes are missing.",
                    "evidence": "(no other routes present)",
                }
            )
    return errors


def _rule_dhcp_failure(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    if re.search(r"169\.254\.\d{1,3}\.\d{1,3}", text):
        errors.append(
            {
                "type": "DHCP_FAILURE",
                "severity": "HIGH",
                "message": "A host has an APIPA address (169.254.x.x), indicating it failed to obtain an address from DHCP.",
                "evidence": "APIPA-range address (169.254.x.x) found in evidence.",
            }
        )
    if re.search(r"no ip dhcp pool", text, re.IGNORECASE) or re.search(
        r"\(no ip dhcp pool \S+ found\)", text, re.IGNORECASE
    ):
        errors.append(
            {
                "type": "DHCP_FAILURE",
                "severity": "HIGH",
                "message": "Expected DHCP pool was not found in the router configuration.",
                "evidence": "DHCP pool missing from configuration output.",
            }
        )
    leased = re.search(r"Leased addresses\s*:\s*(\d+)", text, re.IGNORECASE)
    total = re.search(r"Total addresses\s*:\s*(\d+)", text, re.IGNORECASE)
    if leased and total and leased.group(1) == total.group(1):
        errors.append(
            {
                "type": "DHCP_FAILURE",
                "severity": "MEDIUM",
                "message": "DHCP pool shows leased addresses equal to total addresses (scope exhausted).",
                "evidence": f"Leased addresses: {leased.group(1)} / Total addresses: {total.group(1)}",
            }
        )
    if re.search(r"no ip helper-address configured", text, re.IGNORECASE):
        errors.append(
            {
                "type": "DHCP_FAILURE",
                "severity": "HIGH",
                "message": "No 'ip helper-address' is configured, so DHCP requests are likely not being relayed across subnets.",
                "evidence": "(no ip helper-address configured)",
            }
        )
    return errors


def _rule_dns_failure(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    if re.search(r"DNS request timed out", text, re.IGNORECASE):
        errors.append(
            {
                "type": "DNS_FAILURE",
                "severity": "HIGH",
                "message": "A DNS request timeout was found in the evidence.",
                "evidence": "DNS request timed out",
            }
        )
    if re.search(r"no dns-server line present", text, re.IGNORECASE) or re.search(
        r"\(no dns-server", text, re.IGNORECASE
    ):
        errors.append(
            {
                "type": "DNS_FAILURE",
                "severity": "MEDIUM",
                "message": "DHCP pool does not advertise a DNS server option.",
                "evidence": "(no dns-server line present)",
            }
        )
    if re.search(r"no dns forwarder configured", text, re.IGNORECASE):
        errors.append(
            {
                "type": "DNS_FAILURE",
                "severity": "LOW",
                "message": "No DNS forwarding/upstream server is configured for external resolution.",
                "evidence": "(no dns forwarder configured)",
            }
        )
    return errors


def _rule_acl_deny(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    for match in re.finditer(
        r"^\s*\d+\s+deny\s+\S+.*$", text, re.MULTILINE | re.IGNORECASE
    ):
        line = match.group(0).strip()
        errors.append(
            {
                "type": "ACL_DENY",
                "severity": "MEDIUM",
                "message": "An access-list rule explicitly denies matching traffic.",
                "evidence": line,
            }
        )
    if re.search(r"implicit deny any any", text, re.IGNORECASE):
        errors.append(
            {
                "type": "ACL_DENY",
                "severity": "HIGH",
                "message": "ACL has no explicit permit statements, so the implicit deny-any-any blocks all traffic.",
                "evidence": "(implicit deny any any at end of list)",
            }
        )
    return errors


def _rule_nat_problem(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    if re.search(r"missing 'ip nat inside'", text, re.IGNORECASE):
        errors.append(
            {
                "type": "NAT_PROBLEM",
                "severity": "HIGH",
                "message": "An internal-facing interface is missing the 'ip nat inside' command.",
                "evidence": "(GigabitEthernet0/0 missing 'ip nat inside')",
            }
        )
    if re.search(r"no static nat entry", text, re.IGNORECASE):
        errors.append(
            {
                "type": "NAT_PROBLEM",
                "severity": "MEDIUM",
                "message": "No static NAT / port-forwarding entry exists for the referenced internal server.",
                "evidence": "(no static NAT entry for internal web server present)",
            }
        )
    if re.search(r"access-list 1 not found|access-list \d+ not found", text, re.IGNORECASE):
        errors.append(
            {
                "type": "NAT_PROBLEM",
                "severity": "MEDIUM",
                "message": "The access list referenced by the NAT configuration does not exist.",
                "evidence": "(access-list not found)",
            }
        )
    if re.search(r"no translations present", text, re.IGNORECASE):
        errors.append(
            {
                "type": "NAT_PROBLEM",
                "severity": "MEDIUM",
                "message": "NAT translation table is empty, suggesting NAT is not actively translating traffic.",
                "evidence": "(no translations present)",
            }
        )
    return errors


def _rule_trunk_problem(text: str) -> list[CheckerError]:
    errors: list[CheckerError] = []
    allowed_match = re.search(
        r"switchport trunk allowed vlan\s+([\d,\s]+)", text, re.IGNORECASE
    )
    if allowed_match:
        allowed_vlans = {v.strip() for v in allowed_match.group(1).split(",")}
        vlan_refs = set(re.findall(r"\bVLAN\s*(\d+)\b", text, re.IGNORECASE))
        missing = vlan_refs - allowed_vlans
        for vlan in missing:
            errors.append(
                {
                    "type": "TRUNK_PROBLEM",
                    "severity": "HIGH",
                    "message": f"VLAN {vlan} is referenced in the case but is not included in the trunk's allowed VLAN list.",
                    "evidence": allowed_match.group(0),
                }
            )
    if re.search(r"ssid.*broadcast-ssid disabled", text, re.IGNORECASE | re.DOTALL):
        pass  # handled as wireless, not trunk - intentionally not double counted
    return errors


# Registry of all rule functions to run, in a stable order.
_RULES = [
    _rule_admin_down,
    _rule_interface_down,
    _rule_duplicate_ip,
    _rule_subnet_mask_mismatch,
    _rule_gateway_mismatch,
    _rule_missing_vlan,
    _rule_vlan_mismatch,
    _rule_missing_route,
    _rule_dhcp_failure,
    _rule_dns_failure,
    _rule_acl_deny,
    _rule_nat_problem,
    _rule_trunk_problem,
]


def run_checks(show_output: str) -> CheckerResult:
    """
    Run all deterministic rule checks against the supplied Cisco
    show-command output text.

    Args:
        show_output: Raw text pasted/loaded from a Cisco 'show' command
            (or similar diagnostic output).

    Returns:
        A CheckerResult dict with a "status" of either
        "ERRORS_DETECTED" or "NO_KNOWN_ERRORS", and an "errors" list.
    """
    if not show_output or not show_output.strip():
        return {"status": "NO_KNOWN_ERRORS", "errors": []}

    all_errors: list[CheckerError] = []
    for rule in _RULES:
        try:
            all_errors.extend(rule(show_output))
        except re.error:
            # A single faulty regex should never crash the whole checker.
            continue

    if all_errors:
        return {"status": "ERRORS_DETECTED", "errors": all_errors}
    return {"status": "NO_KNOWN_ERRORS", "errors": []}

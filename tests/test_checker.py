"""Tests for src/checker.py - the deterministic rule checker."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.checker import run_checks


def test_empty_input_returns_no_known_errors():
    result = run_checks("")
    assert result["status"] == "NO_KNOWN_ERRORS"
    assert result["errors"] == []


def test_admin_down_interface_is_detected():
    text = "GigabitEthernet0/0.30 is administratively down, line protocol is down"
    result = run_checks(text)
    assert result["status"] == "ERRORS_DETECTED"
    types = [e["type"] for e in result["errors"]]
    assert "INTERFACE_ADMIN_DOWN" in types


def test_interface_down_notconnect_is_detected():
    text = "Fa0/3 notconnect 10 auto auto 10/100BaseTX"
    result = run_checks(text)
    assert result["status"] == "ERRORS_DETECTED"
    types = [e["type"] for e in result["errors"]]
    assert "INTERFACE_DOWN" in types


def test_missing_route_is_detected():
    text = "C 192.168.1.0/24 is directly connected, GigabitEthernet0/0\n(no route to 192.168.2.0/24)"
    result = run_checks(text)
    assert result["status"] == "ERRORS_DETECTED"
    types = [e["type"] for e in result["errors"]]
    assert "MISSING_ROUTE" in types


def test_missing_vlan_is_detected():
    text = "VLAN Name Status Ports\n1 default active Fa0/1, Fa0/2\n(VLAN 20 not listed)"
    result = run_checks(text)
    assert result["status"] == "ERRORS_DETECTED"
    types = [e["type"] for e in result["errors"]]
    assert "MISSING_VLAN" in types


def test_duplicate_ip_is_detected():
    text = "IP Address: 192.168.10.25\nIP Address: 192.168.10.25"
    result = run_checks(text)
    assert result["status"] == "ERRORS_DETECTED"
    types = [e["type"] for e in result["errors"]]
    assert "DUPLICATE_IP" in types


def test_dhcp_apipa_is_detected():
    text = "PC1 has address 169.254.12.4"
    result = run_checks(text)
    assert result["status"] == "ERRORS_DETECTED"
    types = [e["type"] for e in result["errors"]]
    assert "DHCP_FAILURE" in types


def test_acl_deny_is_detected():
    text = "10 deny ip 192.168.10.0 0.0.0.255 192.168.30.0 0.0.0.255 (25 matches)\n20 permit ip any any"
    result = run_checks(text)
    assert result["status"] == "ERRORS_DETECTED"
    types = [e["type"] for e in result["errors"]]
    assert "ACL_DENY" in types


def test_no_known_pattern_returns_no_known_errors():
    text = "This is just plain unrelated text with no recognizable pattern."
    result = run_checks(text)
    assert result["status"] == "NO_KNOWN_ERRORS"
    assert result["errors"] == []


def test_result_shape_is_always_valid():
    for text in ["", "random text", "GigabitEthernet0/0.30 is administratively down"]:
        result = run_checks(text)
        assert "status" in result
        assert "errors" in result
        assert isinstance(result["errors"], list)
        for err in result["errors"]:
            assert {"type", "severity", "message", "evidence"} <= set(err.keys())

"""Tests for src/engine.py - AI diagnosis engine (demo mode + validation)."""

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.engine import (
    diagnose_case,
    is_live_mode_available,
    parse_and_validate_response,
)


def test_missing_api_key_triggers_demo_mode(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert is_live_mode_available() is False


def test_api_key_present_enables_live_mode_flag(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake-key-for-test")
    assert is_live_mode_available() is True


def test_diagnose_case_demo_mode_returns_valid_structure(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    checker_result, diagnosis = diagnose_case(
        symptom="PC1 cannot reach Server1 in VLAN 30.",
        topology_note="Router-on-a-stick topology.",
        show_outputs="GigabitEthernet0/0.30 is administratively down, line protocol is down",
    )
    assert checker_result["status"] == "ERRORS_DETECTED"
    assert diagnosis.is_demo_mode is True
    assert 0.0 <= diagnosis.confidence <= 1.0
    assert isinstance(diagnosis.evidence, list)
    assert isinstance(diagnosis.fix_steps, list)
    assert diagnosis.root_cause


def test_diagnose_case_demo_mode_no_errors_still_returns_structure(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    checker_result, diagnosis = diagnose_case(
        symptom="Something vague happened.",
        topology_note="Unclear topology.",
        show_outputs="",
    )
    assert checker_result["status"] == "NO_KNOWN_ERRORS"
    assert diagnosis.is_demo_mode is True
    assert diagnosis.confidence <= 0.5


def test_parse_valid_json_response():
    raw = """
    {
        "root_cause": "Interface is down",
        "osi_layer": "Layer 3",
        "confidence": 0.9,
        "evidence": ["GigabitEthernet0/0.30 is administratively down"],
        "next_command": "show interfaces GigabitEthernet0/0.30",
        "fix_steps": ["no shutdown"]
    }
    """
    diagnosis = parse_and_validate_response(raw)
    assert diagnosis.root_cause == "Interface is down"
    assert diagnosis.confidence == 0.9
    assert diagnosis.evidence == ["GigabitEthernet0/0.30 is administratively down"]
    assert diagnosis.validation_warnings == []


def test_parse_invalid_json_is_handled_safely():
    raw = "This is not JSON at all { broken"
    diagnosis = parse_and_validate_response(raw)
    assert diagnosis.confidence == 0.0
    assert "not valid JSON" in diagnosis.validation_warnings[0]


def test_parse_json_missing_fields_is_handled_safely():
    raw = '{"root_cause": "Something is wrong"}'
    diagnosis = parse_and_validate_response(raw)
    assert diagnosis.root_cause == "Something is wrong"
    assert diagnosis.evidence == []
    assert len(diagnosis.validation_warnings) > 0


def test_parse_json_with_code_fences_is_handled():
    raw = """```json
    {
        "root_cause": "X",
        "osi_layer": "Layer 2",
        "confidence": 0.5,
        "evidence": ["some evidence"],
        "next_command": "show vlan brief",
        "fix_steps": ["step 1"]
    }
    ```"""
    diagnosis = parse_and_validate_response(raw)
    assert diagnosis.root_cause == "X"
    assert diagnosis.confidence == 0.5


def test_parse_json_confidence_out_of_range_is_clamped():
    raw = '{"root_cause": "X", "osi_layer": "L3", "confidence": 5.0, "evidence": ["e"], "next_command": "c", "fix_steps": ["f"]}'
    diagnosis = parse_and_validate_response(raw)
    assert diagnosis.confidence == 1.0
    assert any("clamped" in w for w in diagnosis.validation_warnings)

"""
engine.py
---------
The AI diagnosis engine.

Responsibilities:
1. Load case information (via utils.py).
2. Run the deterministic rule checker (checker.py).
3. Build a structured prompt (using prompts/diagnose_prompt.md as the
   system prompt).
4. Send the prompt to the Gemini API (or use DEMO MODE if no API key
   is configured).
5. Parse and validate the LLM's JSON response.
6. Return a safe, structured AIDiagnosis object.

SAFETY:
This module NEVER executes any command against a real or simulated
network device. It only produces text recommendations that a human
must review in the Streamlit UI (see app.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .checker import run_checks
from .models import REQUIRED_AI_FIELDS, AIDiagnosis
from .utils import get_project_root

# Load variables from a local .env file (if present) into the process
# environment. This must happen before any os.environ.get() calls below.
# Safe to call even if .env does not exist, and safe to call multiple
# times (e.g. once from app.py's import and once here).
load_dotenv(get_project_root() / ".env")

# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


class LLMProviderError(Exception):
    """Raised when the LLM provider fails to return a usable response."""


def _get_prompt_template() -> str:
    """Load the system prompt Markdown file."""
    prompt_path = get_project_root() / "prompts" / "diagnose_prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found at '{prompt_path}'. It is required to run diagnoses."
        )
    return prompt_path.read_text(encoding="utf-8")


def is_live_mode_available() -> bool:
    """Return True if a Gemini API key is configured in the environment."""
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _call_llm_live(user_prompt: str) -> str:
    """
    Call the configured Gemini model and return its raw text response.

    Reads GEMINI_API_KEY and GEMINI_MODEL from the environment via the
    official google-genai SDK. The system prompt (prompts/diagnose_prompt.md)
    is passed as a system_instruction so the model's safety rules and JSON
    schema requirements are enforced on every call.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest").strip()

    if not api_key:
        raise LLMProviderError("GEMINI_API_KEY is not set.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise LLMProviderError(
            "The 'google-genai' package is not installed. Run "
            "'pip install -r requirements.txt', or use demo mode."
        ) from exc

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_get_prompt_template(),
                temperature=0.2,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise LLMProviderError("Gemini returned an empty response.")
        return text
    except LLMProviderError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error upstream
        raise LLMProviderError(f"Gemini API call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_user_prompt(
    symptom: str,
    topology_note: str,
    show_outputs: str,
    checker_result: dict,
) -> str:
    """Build the case-specific user prompt sent alongside the system prompt."""
    return (
        "Analyze the following networking case and respond with STRICT JSON "
        "only, following the schema and rules in the system prompt.\n\n"
        f"SYMPTOM:\n{symptom}\n\n"
        f"TOPOLOGY NOTE:\n{topology_note}\n\n"
        f"SHOW COMMAND OUTPUT:\n{show_outputs}\n\n"
        f"DETERMINISTIC RULE CHECKER RESULT (Python-generated, not from you):\n"
        f"{json.dumps(checker_result, indent=2)}\n"
    )


# ---------------------------------------------------------------------------
# JSON parsing / validation
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the model added them despite instructions."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if cleaned.count("```") >= 2 else cleaned
        cleaned = cleaned.removeprefix("json").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[: cleaned.rfind("```")].strip()
    return cleaned


def parse_and_validate_response(raw_text: str) -> AIDiagnosis:
    """
    Parse raw LLM text into a validated AIDiagnosis.

    This function must NEVER raise on malformed input from the LLM;
    instead it returns a safe, low-confidence AIDiagnosis with
    validation_warnings explaining what went wrong. This keeps the
    Streamlit app from crashing on unpredictable model output.
    """
    warnings: list[str] = []
    cleaned = _strip_code_fences(raw_text)

    try:
        data: dict[str, Any] = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return AIDiagnosis(
            root_cause="AI response could not be parsed as valid JSON.",
            osi_layer="Unknown - parsing error",
            confidence=0.0,
            evidence=[],
            next_command="Re-run diagnosis or collect additional evidence.",
            fix_steps=["Review the raw AI response manually before proceeding."],
            raw_response=raw_text,
            validation_warnings=["Response was not valid JSON."],
        )

    for field_name in REQUIRED_AI_FIELDS:
        if field_name not in data:
            warnings.append(f"Missing required field '{field_name}' in AI response.")

    root_cause = str(data.get("root_cause", "Not provided by AI response."))
    osi_layer = str(data.get("osi_layer", "Unknown"))
    next_command = str(data.get("next_command", "Not provided by AI response."))

    confidence_raw = data.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
        if not (0.0 <= confidence <= 1.0):
            warnings.append("Confidence out of expected 0.0-1.0 range; clamped.")
            confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        warnings.append("Confidence field was not a valid number; defaulted to 0.0.")
        confidence = 0.0

    evidence_raw = data.get("evidence", [])
    if isinstance(evidence_raw, list):
        evidence = [str(item) for item in evidence_raw]
    elif isinstance(evidence_raw, str):
        evidence = [evidence_raw]
        warnings.append("Evidence field was a string instead of a list; wrapped automatically.")
    else:
        evidence = []
        warnings.append("Evidence field had an unexpected type; defaulted to empty list.")

    fix_steps_raw = data.get("fix_steps", [])
    if isinstance(fix_steps_raw, list):
        fix_steps = [str(item) for item in fix_steps_raw]
    elif isinstance(fix_steps_raw, str):
        fix_steps = [fix_steps_raw]
        warnings.append("fix_steps field was a string instead of a list; wrapped automatically.")
    else:
        fix_steps = []
        warnings.append("fix_steps field had an unexpected type; defaulted to empty list.")

    if not evidence:
        warnings.append("No evidence was provided; treat this diagnosis with caution.")
        confidence = min(confidence, 0.4)

    return AIDiagnosis(
        root_cause=root_cause,
        osi_layer=osi_layer,
        confidence=confidence,
        evidence=evidence,
        next_command=next_command,
        fix_steps=fix_steps,
        raw_response=raw_text,
        validation_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Demo / mock mode
# ---------------------------------------------------------------------------


def _demo_diagnosis_from_checker(checker_result: dict, symptom: str) -> AIDiagnosis:
    """
    Build a deterministic, reasonable "mock AI" diagnosis using only the
    rule checker's output. Used when no live LLM API key is configured,
    so the whole application remains demonstrable offline.
    """
    errors = checker_result.get("errors", [])

    if not errors:
        return AIDiagnosis(
            root_cause=(
                "No deterministic rule pattern was detected in the supplied "
                "evidence. Insufficient evidence to identify a specific root cause."
            ),
            osi_layer="Unknown - insufficient evidence",
            confidence=0.2,
            evidence=[],
            next_command="Collect additional 'show' command output relevant to the symptom.",
            fix_steps=[
                "Gather more diagnostic evidence from the affected device(s).",
                "Re-run diagnosis once more evidence is available.",
            ],
            is_demo_mode=True,
        )

    primary = errors[0]
    error_type = primary.get("type", "UNKNOWN")

    layer_map = {
        "INTERFACE_ADMIN_DOWN": "Layer 3",
        "INTERFACE_DOWN": "Layer 1",
        "DUPLICATE_IP": "Layer 3",
        "SUBNET_MASK_MISMATCH": "Layer 3",
        "GATEWAY_MISMATCH": "Layer 3",
        "MISSING_VLAN": "Layer 2",
        "VLAN_MISMATCH": "Layer 2",
        "MISSING_ROUTE": "Layer 3",
        "DHCP_FAILURE": "Layer 7",
        "DNS_FAILURE": "Layer 7",
        "ACL_DENY": "Layer 3",
        "NAT_PROBLEM": "Layer 3",
        "TRUNK_PROBLEM": "Layer 2",
    }

    next_command_map = {
        "INTERFACE_ADMIN_DOWN": "show interfaces",
        "INTERFACE_DOWN": "show interfaces status",
        "DUPLICATE_IP": "show arp",
        "SUBNET_MASK_MISMATCH": "show ip interface brief",
        "GATEWAY_MISMATCH": "show ip interface brief",
        "MISSING_VLAN": "show vlan brief",
        "VLAN_MISMATCH": "show run interface (affected sub-interface)",
        "MISSING_ROUTE": "show ip route",
        "DHCP_FAILURE": "show ip dhcp pool",
        "DNS_FAILURE": "show run | include dns",
        "ACL_DENY": "show access-lists",
        "NAT_PROBLEM": "show ip nat translations",
        "TRUNK_PROBLEM": "show interfaces trunk",
    }

    fix_steps_map = {
        "INTERFACE_ADMIN_DOWN": [
            "Enter configuration mode",
            "Select the affected interface",
            "Run 'no shutdown'",
        ],
        "INTERFACE_DOWN": [
            "Verify the physical cable and that the end device is powered on",
            "Reseat or replace the cable if necessary",
        ],
        "DUPLICATE_IP": [
            "Reassign a unique IP address to the conflicting host",
            "Clear ARP caches on affected devices and retest",
        ],
        "SUBNET_MASK_MISMATCH": [
            "Correct the subnet mask on the misconfigured host",
            "Verify connectivity across the intended subnet range",
        ],
        "GATEWAY_MISMATCH": [
            "Update the default gateway to match the router's LAN interface address",
        ],
        "MISSING_VLAN": [
            "Create the missing VLAN in the VLAN database",
            "Assign the correct access ports to the VLAN",
        ],
        "VLAN_MISMATCH": [
            "Correct the dot1Q encapsulation tag on the sub-interface",
        ],
        "MISSING_ROUTE": [
            "Add the missing static route, or verify the dynamic routing protocol configuration",
        ],
        "DHCP_FAILURE": [
            "Verify the DHCP pool configuration (network, default-router, dns-server)",
            "Verify ip helper-address is configured if DHCP is centralized",
        ],
        "DNS_FAILURE": [
            "Verify the DNS server address configured on the client or DHCP pool",
            "Verify DNS forwarding if external resolution is required",
        ],
        "ACL_DENY": [
            "Review the access list for unintended deny statements",
            "Adjust or reorder ACL entries to match intended policy",
        ],
        "NAT_PROBLEM": [
            "Verify 'ip nat inside' / 'ip nat outside' are applied to the correct interfaces",
            "Verify the NAT access-list and any static translations",
        ],
        "TRUNK_PROBLEM": [
            "Add the missing VLAN to the trunk's allowed VLAN list",
        ],
    }

    return AIDiagnosis(
        root_cause=primary.get("message", "A deterministic rule violation was detected."),
        osi_layer=layer_map.get(error_type, "Unknown"),
        confidence=0.75 if primary.get("severity") == "HIGH" else 0.6,
        evidence=[e.get("evidence", "") for e in errors[:3]],
        next_command=next_command_map.get(error_type, "show running-config"),
        fix_steps=fix_steps_map.get(
            error_type, ["Review the affected configuration manually."]
        ),
        is_demo_mode=True,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def diagnose_case(
    symptom: str,
    topology_note: str,
    show_outputs: str,
) -> tuple[dict, AIDiagnosis]:
    """
    Run the full diagnostic pipeline for a single case:
    rule checker -> (LLM or demo mode) -> validated AIDiagnosis.

    Returns:
        A tuple of (checker_result, ai_diagnosis).
    """
    checker_result = run_checks(show_outputs)

    if is_live_mode_available():
        try:
            user_prompt = build_user_prompt(
                symptom, topology_note, show_outputs, checker_result
            )
            raw_response = _call_llm_live(user_prompt)
            diagnosis = parse_and_validate_response(raw_response)
            diagnosis.is_demo_mode = False
            return checker_result, diagnosis
        except LLMProviderError as exc:
            # Fail gracefully into demo mode rather than crashing the app.
            diagnosis = _demo_diagnosis_from_checker(checker_result, symptom)
            diagnosis.validation_warnings.append(
                f"Live LLM call failed, fell back to demo mode: {exc}"
            )
            return checker_result, diagnosis

    diagnosis = _demo_diagnosis_from_checker(checker_result, symptom)
    return checker_result, diagnosis
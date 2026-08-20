"""
models.py
---------
Shared data structures used across the NetSage AI application.

Keeping these in one place makes it easy for a reviewer (or a student
during a viva) to see exactly what shape of data flows between
checker.py -> engine.py -> app.py -> audit.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


REQUIRED_AI_FIELDS = [
    "root_cause",
    "osi_layer",
    "confidence",
    "evidence",
    "next_command",
    "fix_steps",
]


@dataclass
class NetworkCase:
    """A single troubleshooting case loaded from data/cases.csv."""

    case_id: str
    symptom: str
    topology_note: str
    concept_tag: str
    severity: str
    show_outputs: str
    expected_fault: str
    osi_layer: str
    expected_next_command: str
    expected_fix_steps: str


@dataclass
class AIDiagnosis:
    """A validated, structured diagnosis returned by the AI engine."""

    root_cause: str
    osi_layer: str
    confidence: float
    evidence: list[str]
    next_command: str
    fix_steps: list[str]
    is_demo_mode: bool = False
    raw_response: str | None = None
    validation_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "root_cause": self.root_cause,
            "osi_layer": self.osi_layer,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "next_command": self.next_command,
            "fix_steps": self.fix_steps,
            "is_demo_mode": self.is_demo_mode,
            "validation_warnings": self.validation_warnings,
        }


@dataclass
class AuditRecord:
    """One row of the human-in-the-loop audit trail."""

    case_id: str
    ai_diagnosis: dict
    ai_confidence: float
    checker_result: dict
    human_decision: str  # ACCEPTED | EDITED | REJECTED
    edited_commands: str | None = None
    rejection_reason: str | None = None
    final_status: str = "RECORDED"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "case_id": self.case_id,
            "ai_diagnosis": self.ai_diagnosis,
            "ai_confidence": self.ai_confidence,
            "checker_result": self.checker_result,
            "human_decision": self.human_decision,
            "edited_commands": self.edited_commands,
            "rejection_reason": self.rejection_reason,
            "final_status": self.final_status,
        }

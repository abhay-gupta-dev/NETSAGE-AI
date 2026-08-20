"""
audit.py
--------
Records AI and human decisions for the human-in-the-loop workflow.

Every time a human reviewer Approves, Edits, or Rejects an AI
diagnosis, a record is appended to a local JSONL audit log
(data/audit_log.jsonl). This module also provides helper functions to
summarize the log for the Streamlit statistics dashboard.

Design note: JSONL (one JSON object per line) is used instead of a
single JSON array so that records can be appended safely without
re-parsing/re-writing the whole file every time.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import AuditRecord
from .utils import get_project_root

DECISION_ACCEPTED = "ACCEPTED"
DECISION_EDITED = "EDITED"
DECISION_REJECTED = "REJECTED"

VALID_DECISIONS = {DECISION_ACCEPTED, DECISION_EDITED, DECISION_REJECTED}


def get_audit_log_path() -> Path:
    """Return the path to the JSONL audit log file (created on first write)."""
    return get_project_root() / "data" / "audit_log.jsonl"


def record_decision(record: AuditRecord) -> None:
    """
    Append a single audit record to the audit log file.

    Args:
        record: An AuditRecord describing the case, AI diagnosis, and
            the human reviewer's decision.

    Raises:
        ValueError: if the decision is not one of the recognized values.
    """
    if record.human_decision not in VALID_DECISIONS:
        raise ValueError(
            f"Invalid human_decision '{record.human_decision}'. "
            f"Must be one of {sorted(VALID_DECISIONS)}."
        )

    log_path = get_audit_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")


def load_audit_log() -> list[dict]:
    """
    Load all audit records from the log file.

    Returns an empty list (not an error) if the log does not exist yet,
    since that simply means no decisions have been recorded.
    """
    log_path = get_audit_log_path()
    if not log_path.exists():
        return []

    records: list[dict] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip corrupted lines instead of crashing the dashboard.
                continue
    return records


def compute_statistics() -> dict:
    """
    Compute summary statistics from the audit log for the dashboard.

    Returns a dict with counts and an AI-human agreement rate, where
    "agreement" means the human ACCEPTED the AI's diagnosis outright
    (i.e. did not need to edit or reject it).
    """
    records = load_audit_log()
    total = len(records)
    accepted = sum(1 for r in records if r.get("human_decision") == DECISION_ACCEPTED)
    edited = sum(1 for r in records if r.get("human_decision") == DECISION_EDITED)
    rejected = sum(1 for r in records if r.get("human_decision") == DECISION_REJECTED)

    agreement_rate = (accepted / total) if total > 0 else 0.0

    return {
        "total_cases_reviewed": total,
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "ai_human_agreement_rate": round(agreement_rate, 3),
    }

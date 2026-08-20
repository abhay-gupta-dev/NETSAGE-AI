"""
utils.py
--------
Small shared helper functions used across the project: locating the
project root, loading the case dataset, and other lightweight utilities.

Kept deliberately small and dependency-light so it is easy to read
during a college viva/demo.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .models import NetworkCase

REQUIRED_CASE_COLUMNS = [
    "case_id",
    "symptom",
    "topology_note",
    "concept_tag",
    "severity",
    "show_outputs",
    "expected_fault",
    "osi_layer",
    "expected_next_command",
    "expected_fix_steps",
]


def get_project_root() -> Path:
    """Return the project root directory (the folder containing src/)."""
    return Path(__file__).resolve().parent.parent


def get_cases_csv_path() -> Path:
    """Return the absolute path to data/cases.csv using pathlib (Windows-safe)."""
    return get_project_root() / "data" / "cases.csv"


class CaseLoadError(Exception):
    """Raised when the case dataset cannot be loaded or is invalid."""


def load_cases(csv_path: Path | None = None) -> pd.DataFrame:
    """
    Load and validate the case dataset from CSV.

    Args:
        csv_path: Optional override path (mainly used by tests).

    Returns:
        A pandas DataFrame with all required columns.

    Raises:
        CaseLoadError: if the file is missing, empty, or missing columns.
    """
    path = csv_path or get_cases_csv_path()

    if not path.exists():
        raise CaseLoadError(
            f"Case dataset not found at '{path}'. "
            "Make sure data/cases.csv exists (see README for setup)."
        )

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise CaseLoadError(f"Case dataset at '{path}' is empty.") from exc
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        raise CaseLoadError(f"Failed to read case dataset '{path}': {exc}") from exc

    if df.empty:
        raise CaseLoadError(f"Case dataset at '{path}' contains no rows.")

    missing_columns = [c for c in REQUIRED_CASE_COLUMNS if c not in df.columns]
    if missing_columns:
        raise CaseLoadError(
            f"Case dataset is missing required columns: {missing_columns}"
        )

    return df


def dataframe_row_to_case(row: pd.Series) -> NetworkCase:
    """Convert a pandas row into a NetworkCase dataclass instance."""
    return NetworkCase(
        case_id=str(row["case_id"]),
        symptom=str(row["symptom"]),
        topology_note=str(row["topology_note"]),
        concept_tag=str(row["concept_tag"]),
        severity=str(row["severity"]),
        show_outputs=str(row["show_outputs"]),
        expected_fault=str(row["expected_fault"]),
        osi_layer=str(row["osi_layer"]),
        expected_next_command=str(row["expected_next_command"]),
        expected_fix_steps=str(row["expected_fix_steps"]),
    )


def get_case_by_id(df: pd.DataFrame, case_id: str) -> NetworkCase | None:
    """Look up a single case by its case_id. Returns None if not found."""
    matches = df[df["case_id"] == case_id]
    if matches.empty:
        return None
    return dataframe_row_to_case(matches.iloc[0])

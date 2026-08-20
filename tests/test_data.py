"""Tests for the case dataset (data/cases.csv)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.utils import (
    REQUIRED_CASE_COLUMNS,
    CaseLoadError,
    get_case_by_id,
    load_cases,
)


def test_cases_csv_loads_successfully():
    df = load_cases()
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


def test_at_least_30_cases_exist():
    df = load_cases()
    assert len(df) >= 30


def test_required_columns_exist():
    df = load_cases()
    for col in REQUIRED_CASE_COLUMNS:
        assert col in df.columns


def test_case_ids_are_unique():
    df = load_cases()
    assert df["case_id"].is_unique


def test_net_001_demo_case_exists_and_matches_spec():
    df = load_cases()
    case = get_case_by_id(df, "NET-001")
    assert case is not None
    assert "VLAN 30" in case.symptom
    assert "administratively down" in case.show_outputs


def test_get_case_by_id_returns_none_for_unknown_case():
    df = load_cases()
    assert get_case_by_id(df, "NET-999") is None


def test_missing_csv_raises_case_load_error(tmp_path):
    missing_path = tmp_path / "does_not_exist.csv"
    with pytest.raises(CaseLoadError):
        load_cases(csv_path=missing_path)


def test_empty_csv_raises_case_load_error(tmp_path):
    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("", encoding="utf-8")
    with pytest.raises(CaseLoadError):
        load_cases(csv_path=empty_path)


def test_csv_missing_columns_raises_case_load_error(tmp_path):
    bad_path = tmp_path / "bad.csv"
    bad_path.write_text("case_id,symptom\nNET-001,test\n", encoding="utf-8")
    with pytest.raises(CaseLoadError):
        load_cases(csv_path=bad_path)


def test_category_distribution_covers_required_concepts():
    df = load_cases()
    tags = set(df["concept_tag"].unique())
    expected_present = {"VLAN", "Routing", "DHCP", "DNS", "ACL", "NAT", "Gateway", "Wireless"}
    assert expected_present.issubset(tags)

"""
app.py
------
Streamlit user interface for NetSage AI.

Provides the dashboard, the human-in-the-loop review workflow
(Approve / Edit / Reject), and live statistics. This file focuses on
presentation and wiring; the actual logic lives in checker.py,
engine.py, and audit.py.

Run with:
    streamlit run src/app.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# Allow running as `streamlit run src/app.py` (i.e. not as a package)
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src import audit  # noqa: E402
from src.engine import diagnose_case, is_live_mode_available  # noqa: E402
from src.models import AuditRecord  # noqa: E402
from src.utils import CaseLoadError, get_case_by_id, load_cases  # noqa: E402

st.set_page_config(
    page_title="NetSage AI",
    page_icon="🛰️",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _load_case_dataframe() -> pd.DataFrame:
    return load_cases()


def _reset_diagnosis_state() -> None:
    for key in ("checker_result", "ai_diagnosis", "review_submitted"):
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def render_sidebar(df: pd.DataFrame) -> str:
    st.sidebar.title("NetSage AI")
    st.sidebar.caption("Automated Network Diagnostic Platform")

    mode_label = "🟢 LIVE MODE" if is_live_mode_available() else "🟡 DEMO MODE"
    st.sidebar.markdown(f"**AI Mode:** {mode_label}")
    if not is_live_mode_available():
        st.sidebar.caption(
            "No LLM_API_KEY detected. Using deterministic demo responses. "
            "See .env.example to enable live mode."
        )

    st.sidebar.divider()

    categories = ["All"] + sorted(df["concept_tag"].unique().tolist())
    selected_category = st.sidebar.selectbox("Issue category", categories)

    severities = ["All"] + sorted(df["severity"].unique().tolist())
    selected_severity = st.sidebar.selectbox("Severity", severities)

    filtered = df.copy()
    if selected_category != "All":
        filtered = filtered[filtered["concept_tag"] == selected_category]
    if selected_severity != "All":
        filtered = filtered[filtered["severity"] == selected_severity]

    if filtered.empty:
        st.sidebar.warning("No cases match the selected filters.")
        filtered = df

    case_ids = filtered["case_id"].tolist()
    default_index = case_ids.index("NET-001") if "NET-001" in case_ids else 0
    selected_case_id = st.sidebar.selectbox(
        "Case selector", case_ids, index=default_index
    )

    st.sidebar.divider()
    st.sidebar.caption(
        "⚠️ Educational tool only. No commands are ever executed on a "
        "real or simulated device."
    )

    return selected_case_id


# ---------------------------------------------------------------------------
# Section 1 & 2: Case info + show output
# ---------------------------------------------------------------------------


def render_case_information(case) -> None:
    st.subheader("1️⃣ Case Information")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Case ID", case.case_id)
    col2.metric("Concept", case.concept_tag)
    col3.metric("Severity", case.severity)
    col4.metric("OSI Layer (expected)", case.osi_layer)

    st.markdown(f"**Symptom:** {case.symptom}")
    st.markdown(f"**Topology note:** {case.topology_note}")


def render_show_output(case) -> None:
    st.subheader("2️⃣ Show Command Output")
    st.code(case.show_outputs, language="text")


# ---------------------------------------------------------------------------
# Section 3: Rule checker
# ---------------------------------------------------------------------------


def render_checker_results(checker_result: dict) -> None:
    st.subheader("3️⃣ Deterministic Rule Checker")

    if checker_result["status"] == "ERRORS_DETECTED":
        st.error(f"Status: {checker_result['status']} "
                  f"({len(checker_result['errors'])} finding(s))")
        for err in checker_result["errors"]:
            icon = "🔴" if err["severity"] == "HIGH" else "🟠" if err["severity"] == "MEDIUM" else "🟡"
            with st.expander(f"{icon} {err['type']} — {err['severity']}"):
                st.write(err["message"])
                st.code(err["evidence"], language="text")
    else:
        st.warning(
            "Status: NO_KNOWN_ERRORS — no deterministic rule pattern matched. "
            "This does NOT guarantee the network is correct; further AI and "
            "human analysis is still required."
        )


# ---------------------------------------------------------------------------
# Section 4: AI diagnosis
# ---------------------------------------------------------------------------


def render_ai_diagnosis(diagnosis) -> None:
    st.subheader("4️⃣ AI Diagnosis")

    if diagnosis.is_demo_mode:
        st.info("🟡 DEMO MODE — No live LLM API is being used. "
                 "This response was generated deterministically from the rule checker.")
    else:
        st.success("🟢 LIVE MODE — Response generated by the configured LLM.")

    if diagnosis.validation_warnings:
        with st.expander("⚠️ Validation warnings", expanded=False):
            for w in diagnosis.validation_warnings:
                st.write(f"- {w}")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Root Cause**")
        st.write(diagnosis.root_cause)
        st.markdown("**OSI Layer**")
        st.write(diagnosis.osi_layer)
    with col2:
        st.markdown("**Confidence**")
        st.progress(min(max(diagnosis.confidence, 0.0), 1.0))
        st.caption(f"{diagnosis.confidence:.0%}")
        st.markdown("**Next Command**")
        st.code(diagnosis.next_command, language="text")

    st.markdown("**Evidence**")
    if diagnosis.evidence:
        for item in diagnosis.evidence:
            st.markdown(f"- `{item}`")
    else:
        st.caption("No evidence was returned — treat this diagnosis with caution.")

    st.markdown("**Suggested Fix Steps**")
    if diagnosis.fix_steps:
        for i, step in enumerate(diagnosis.fix_steps, start=1):
            st.markdown(f"{i}. {step}")
    else:
        st.caption("No fix steps were returned.")


# ---------------------------------------------------------------------------
# Section 5: Human review
# ---------------------------------------------------------------------------


def render_human_review(case, checker_result: dict, diagnosis) -> None:
    st.subheader("5️⃣ Human Review")
    st.warning(
        "⚠️ Safety notice: No network device is automatically modified by "
        "this application. 'Approve & Deploy' only records approval for "
        "lab use — it does not execute anything."
    )

    proposed_commands = "\n".join(diagnosis.fix_steps)

    tab_approve, tab_edit, tab_reject = st.tabs(
        ["✅ Approve & Deploy", "✏️ Edit Commands", "❌ Reject"]
    )

    with tab_approve:
        st.caption("Approve the suggested remediation for lab use (simulation only).")
        if st.button("Confirm Approve", key="approve_btn"):
            record = AuditRecord(
                case_id=case.case_id,
                ai_diagnosis=diagnosis.to_dict(),
                ai_confidence=diagnosis.confidence,
                checker_result=checker_result,
                human_decision=audit.DECISION_ACCEPTED,
                final_status="Approved for lab use (not deployed to any real device).",
            )
            audit.record_decision(record)
            st.session_state["review_submitted"] = "ACCEPTED"
            st.success("Decision recorded: ACCEPTED.")

    with tab_edit:
        st.caption("Modify the proposed commands before recording your decision.")
        edited_text = st.text_area(
            "Edited commands", value=proposed_commands, height=150, key="edit_area"
        )
        if st.button("Save Edited Decision", key="edit_btn"):
            record = AuditRecord(
                case_id=case.case_id,
                ai_diagnosis=diagnosis.to_dict(),
                ai_confidence=diagnosis.confidence,
                checker_result=checker_result,
                human_decision=audit.DECISION_EDITED,
                edited_commands=edited_text,
                final_status="Edited remediation approved for lab use (not deployed).",
            )
            audit.record_decision(record)
            st.session_state["review_submitted"] = "EDITED"
            st.success("Decision recorded: EDITED.")

    with tab_reject:
        st.caption("Explain why the AI diagnosis was incorrect or unusable.")
        reason = st.text_area(
            "Rejection reason",
            placeholder="e.g. AI incorrectly identified an ACL issue. The actual problem was a missing route.",
            key="reject_reason",
        )
        if st.button("Confirm Reject", key="reject_btn"):
            if not reason.strip():
                st.error("Please provide a rejection reason before submitting.")
            else:
                record = AuditRecord(
                    case_id=case.case_id,
                    ai_diagnosis=diagnosis.to_dict(),
                    ai_confidence=diagnosis.confidence,
                    checker_result=checker_result,
                    human_decision=audit.DECISION_REJECTED,
                    rejection_reason=reason,
                    final_status="Rejected by human reviewer.",
                )
                audit.record_decision(record)
                st.session_state["review_submitted"] = "REJECTED"
                st.success("Decision recorded: REJECTED.")

    if st.session_state.get("review_submitted"):
        st.info(
            f"Latest decision for {case.case_id}: "
            f"**{st.session_state['review_submitted']}** "
            "(see Dashboard Statistics below / docs/model_audit_log.md)."
        )


# ---------------------------------------------------------------------------
# Section 6: Dashboard statistics
# ---------------------------------------------------------------------------


def render_statistics() -> None:
    st.subheader("📊 Dashboard Statistics")
    stats = audit.compute_statistics()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Cases Reviewed", stats["total_cases_reviewed"])
    col2.metric("Accepted", stats["accepted"])
    col3.metric("Edited", stats["edited"])
    col4.metric("Rejected", stats["rejected"])
    col5.metric("AI-Human Agreement", f"{stats['ai_human_agreement_rate']:.0%}")

    records = audit.load_audit_log()
    if records:
        df = pd.DataFrame(records)
        st.markdown("**Decisions by category**")
        decision_counts = df["human_decision"].value_counts()
        st.bar_chart(decision_counts)

        with st.expander("View raw audit log"):
            st.dataframe(
                df[["timestamp", "case_id", "human_decision", "ai_confidence", "final_status"]],
                use_container_width=True,
            )
    else:
        st.caption("No decisions recorded yet. Run a diagnosis and submit a review above.")


def render_category_overview(df: pd.DataFrame) -> None:
    st.markdown("**Case dataset composition**")
    counts = df["concept_tag"].value_counts()
    st.bar_chart(counts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("NetSage AI")
    st.caption("Automated Network Diagnostic Platform — Applied AI + Network Troubleshooting")

    try:
        df = _load_case_dataframe()
    except CaseLoadError as exc:
        st.error(f"Could not load case dataset: {exc}")
        st.stop()
        return

    selected_case_id = render_sidebar(df)
    case = get_case_by_id(df, selected_case_id)

    if case is None:
        st.error(f"Case '{selected_case_id}' not found in the dataset.")
        st.stop()
        return

    if st.session_state.get("last_case_id") != case.case_id:
        _reset_diagnosis_state()
        st.session_state["last_case_id"] = case.case_id

    render_case_information(case)
    render_show_output(case)

    st.divider()
    run_clicked = st.button("▶️ Run Diagnosis", type="primary")

    if run_clicked:
        with st.spinner("Running deterministic checks and AI diagnosis..."):
            try:
                checker_result, diagnosis = diagnose_case(
                    symptom=case.symptom,
                    topology_note=case.topology_note,
                    show_outputs=case.show_outputs,
                )
                st.session_state["checker_result"] = checker_result
                st.session_state["ai_diagnosis"] = diagnosis
                st.session_state["review_submitted"] = None
            except Exception as exc:  # noqa: BLE001 - user-friendly error surface
                st.error(f"Diagnosis failed unexpectedly: {exc}")

    if "checker_result" in st.session_state and "ai_diagnosis" in st.session_state:
        st.divider()
        render_checker_results(st.session_state["checker_result"])
        st.divider()
        render_ai_diagnosis(st.session_state["ai_diagnosis"])
        st.divider()
        render_human_review(
            case, st.session_state["checker_result"], st.session_state["ai_diagnosis"]
        )

    st.divider()
    tab_stats, tab_categories = st.tabs(["📊 Statistics", "🗂️ Case Categories"])
    with tab_stats:
        render_statistics()
    with tab_categories:
        render_category_overview(df)

    st.divider()
    st.caption(
        f"NetSage AI · Educational lab tool · Rendered {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )


if __name__ == "__main__":
    main()

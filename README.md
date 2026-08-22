# NetSage AI — Automated Network Diagnostic Platform

An Applied AI + Network Troubleshooting college project. NetSage AI
combines a **deterministic Python rule checker** with an **LLM-based
diagnosis engine** and a **human-in-the-loop review workflow** to help
students troubleshoot Cisco Packet Tracer-style networking labs.

---

## 1. Project Overview

Given a symptom, a topology note, and pasted Cisco `show` command
output, NetSage AI:

1. Runs deterministic rule checks (no AI involved) to catch known
   error signatures.
2. Sends the evidence + rule checker output to an LLM (or a demo/mock
   engine if no API key is configured) to produce a structured
   diagnosis: root cause, OSI layer, confidence, evidence, next
   command, and fix steps.
3. Displays the diagnosis to a human reviewer, who must **Approve**,
   **Edit**, or **Reject** it.
4. Records every decision in an audit log for later analysis of
   AI-human agreement.

**No command is ever executed on a real or simulated network device.**
This is strictly a diagnostic/recommendation tool for lab education.

## 2. Problem Statement

Students in introductory networking courses often struggle to connect
symptoms ("PC1 can't reach Server1") to root causes buried in verbose
`show` command output. NetSage AI demonstrates how a rule-based system
and an AI model can work together — with mandatory human oversight —
to make that connection faster and more educational.

## 3. Objectives

- Build a working, demonstrable Applied AI project using Streamlit.
- Combine deterministic logic (rule checker) with generative AI
  (LLM diagnosis) responsibly.
- Implement a full human-in-the-loop review workflow.
- Maintain an auditable record of AI vs. human decisions.
- Document real examples of AI being wrong and corrected by a human
  (Responsible AI).

## 4. Architecture

```
DATA TIER
  data/cases.csv
        |
        v
DIAGNOSTIC CORE
  src/checker.py   (deterministic rules, no AI)
        |
        v
  src/engine.py    (builds prompt, calls LLM or demo mode, validates JSON)
        |
        v
  prompts/diagnose_prompt.md  (system prompt + worked examples)
        |
        v
  LLM  ->  JSON validation
        |
        v
HUMAN-IN-THE-LOOP
  src/app.py       (Streamlit UI: Approve / Edit / Reject)
        |
        v
AUDIT
  src/audit.py  ->  data/audit_log.jsonl
  docs/model_audit_log.md (Responsible AI documentation)
```

## 5. Features

- 35 realistic, hand-written Packet Tracer-style troubleshooting cases
  across VLAN, routing, DHCP, DNS, ACL, NAT, gateway/subnet, and
  wireless categories.
- Deterministic rule checker (regex/string based, 13 rule types).
- LLM diagnosis engine with strict JSON schema validation and
  graceful error handling.
- **Demo/Mock mode** — the entire app works with zero API key or
  internet access, using deterministic mock AI responses derived from
  the rule checker.
- Streamlit dashboard with case selector, rule checker results, AI
  diagnosis, and a 3-way human review workflow (Approve / Edit /
  Reject).
- JSONL audit log with AI-human agreement statistics and charts.
- Documented Responsible AI examples (5+ corrected AI diagnoses) in
  `docs/model_audit_log.md`.
- Automated test suite (`pytest`) covering the checker, engine, and
  dataset.

## 6. Technologies

- Python 3.10+
- Streamlit (UI)
- Pandas (case dataset handling)
- Standard library: `json`, `re`, `pathlib`, `csv`
- Google Gemini API (optional, for live mode) via `GEMINI_API_KEY`
- `python-dotenv` for local environment variable loading
- `pytest` for testing

## 7. Folder Structure

```
NetSage-AI/
│
├── data/
│   ├── cases.csv              # 35 troubleshooting cases
│   └── generate_cases.py      # script used to (re)generate cases.csv
│
├── prompts/
│   └── diagnose_prompt.md     # LLM system prompt + worked examples
│
├── src/
│   ├── __init__.py
│   ├── checker.py             # deterministic rule checker
│   ├── engine.py               # AI diagnosis engine (live + demo mode)
│   ├── app.py                  # Streamlit dashboard
│   ├── models.py               # shared dataclasses
│   ├── audit.py                 # audit log read/write + statistics
│   └── utils.py                 # CSV loading, path helpers
│
├── docs/
│   └── model_audit_log.md      # Responsible AI documentation
│
├── tests/
│   ├── test_checker.py
│   ├── test_engine.py
│   └── test_data.py
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── run.bat
```

### What each module does (plain language)

- **checker.py**: Checks known networking errors using deterministic
  rules (no AI). Always returns the same result for the same input.
- **engine.py**: Sends structured networking evidence to the AI model
  and validates its JSON response, falling back to demo mode if no API
  key is present or the API call fails.
- **app.py**: Provides the Streamlit interface and human review
  workflow.
- **audit.py**: Records AI and human decisions to a local JSONL file
  and computes dashboard statistics.
- **models.py**: Defines the shared data shapes (`NetworkCase`,
  `AIDiagnosis`, `AuditRecord`) used across the app.
- **utils.py**: Loads and validates `cases.csv`, and resolves
  Windows-safe file paths using `pathlib`.

## 8. Installation

```bash
git clone <this-repository>
cd NetSage-AI
```

## 9. Virtual Environment Setup

```bash
python -m venv .venv
```

**Windows:**
```
.venv\Scripts\activate
```

**macOS/Linux:**
```
source .venv/bin/activate
```

Then install dependencies:

```bash
pip install -r requirements.txt
```

## 10. Environment Variables

Copy `.env.example` to `.env` and fill in your own values if you want
**live** AI mode:

```
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-flash-latest
```

If `.env` is missing or `GEMINI_API_KEY` is empty, the app automatically
runs in **Demo Mode** — no code changes required.

## 11. Demo Mode

Demo Mode requires no API key and no internet access. It uses the
deterministic rule checker's output to build a reasonable mock AI
diagnosis, and clearly labels every result:

> 🟡 DEMO MODE — No live LLM API is being used.

This lets you fully demonstrate the project (including the NET-001
walkthrough) without any external dependency.

## 12. Live AI Mode

Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`) in your `.env` file.
Get a free Gemini API key at https://aistudio.google.com/apikey.
When a key is present, `src/engine.py` sends the structured prompt to
the Google Gemini API and validates the JSON response. If the
live call fails for any reason (bad key, network error, malformed
response), the app **automatically and safely falls back to Demo
Mode** instead of crashing.

## 13. How to Run

```bash
streamlit run src/app.py
```

On Windows, you can also just double-click / run:

```
run.bat
```

Then open the URL Streamlit prints (usually `http://localhost:8501`).

## 14. How the Rule Checker Works

`src/checker.py` scans the raw `show` command text with regular
expressions for well-known signatures: administratively down
interfaces, `notconnect` ports, duplicate IPs, subnet mask mismatches,
gateway mismatches, missing/mismatched VLANs, missing routes, DHCP/DNS
failure indicators, ACL deny statements, NAT misconfiguration, and
trunk VLAN pruning issues. It never uses an LLM and always returns the
same result for the same input. If nothing matches, it explicitly
returns `NO_KNOWN_ERRORS` — this does **not** mean the network is
correct, only that no known pattern was recognized.

## 15. How AI Diagnosis Works

`src/engine.py`:
1. Runs the rule checker first.
2. Builds a prompt combining the symptom, topology note, show output,
   and rule checker result.
3. Sends it to the LLM (or uses demo mode) using the system prompt in
   `prompts/diagnose_prompt.md`.
4. Parses the response as strict JSON and validates every required
   field (`root_cause`, `osi_layer`, `confidence`, `evidence`,
   `next_command`, `fix_steps`).
5. Never crashes on malformed AI output — it returns a safe,
   low-confidence diagnosis with `validation_warnings` instead.

## 16. Human-in-the-Loop Workflow

After a diagnosis is produced, the reviewer chooses one of three
actions in the Streamlit UI:

- **Approve & Deploy** — records approval for lab use only. **Nothing
  is deployed to any real device.**
- **Edit Commands** — lets the reviewer modify the proposed fix steps
  before recording the decision.
- **Reject** — requires a written reason, which is saved to the audit
  log.

## 17. Audit Logging

Every decision is appended to `data/audit_log.jsonl` via
`src/audit.py`. The Statistics tab in the dashboard reads this file to
show total cases reviewed, accepted/edited/rejected counts, and the
AI-human agreement rate (percentage of diagnoses accepted with zero
changes).

See `docs/model_audit_log.md` for five fully documented examples of
the AI being wrong and corrected by a human reviewer (Responsible AI
requirement).

## 18. Testing

```bash
pytest tests/ -v
```

The test suite (29 tests) covers:
- CSV loading and validation (missing file, empty file, missing
  columns, at least 30 cases, unique case IDs).
- Rule checker detection for administratively-down interfaces, missing
  routes, missing VLANs, duplicate IPs, DHCP/ACL indicators, and more.
- AI engine JSON parsing/validation, including malformed JSON, missing
  fields, code-fenced responses, and out-of-range confidence values.
- Demo mode activation when no API key is present.

## 19. Limitations

- The AI diagnosis is only as good as the text evidence supplied; it
  cannot inspect a real device.
- The rule checker is intentionally narrow (13 rule types) and will
  not catch every possible networking fault — `NO_KNOWN_ERRORS` is not
  proof of correctness.
- Demo mode diagnoses are derived only from the rule checker, so cases
  with `NO_KNOWN_ERRORS` will always produce a low-confidence, generic
  demo response.
- This is an educational prototype, not a production monitoring tool.

## 20. Safety Considerations

- The application **never** connects to a real router, never SSHes
  into any device, and never executes AI-generated or Cisco CLI
  commands automatically.
- "Approve & Deploy" only records a human decision; it does not touch
  any device.
- No API keys are hard-coded; they are read from environment variables
  and the app fails gracefully into Demo Mode if one is missing.

## 21. Future Improvements

- Add a second LLM provider option behind the same `engine.py`
  abstraction.
- Expand the rule checker with more Cisco IOS error signatures.
- Add authentication for multi-user classroom deployments.
- Export the audit log to CSV/PDF for grading or reporting.

## 22. Demo Instructions (NET-001 Walkthrough)

1. Run `streamlit run src/app.py`.
2. In the sidebar, confirm the case selector defaults to **NET-001**.
3. Review the displayed symptom ("PC1 cannot reach Server1 in VLAN
   30") and the raw show output.
4. Click **▶️ Run Diagnosis**.
5. Observe the Rule Checker section flag `INTERFACE_ADMIN_DOWN` on
   `GigabitEthernet0/0.30`.
6. Observe the AI Diagnosis section: root cause, OSI Layer 3,
   confidence, evidence, next command
   (`show interfaces GigabitEthernet0/0.30`), and fix steps
   (`no shutdown`).
7. In the Human Review section, try **Approve & Deploy**, or switch to
   **Edit Commands** to see the editable text area, or **Reject** with
   a reason.
8. Open the **Statistics** tab to see the decision recorded and the
   AI-human agreement rate update.

# NetSage AI — Model Audit Log & Responsible AI Documentation

This document explains how NetSage AI records human-in-the-loop
decisions, and demonstrates **Responsible AI** by documenting real
example cases where a human reviewer corrected an AI diagnosis.

## How the audit log works

Every time a reviewer clicks **Approve & Deploy**, **Edit Commands**, or
**Reject** in the Streamlit app, `src/audit.py` appends one JSON record
to `data/audit_log.jsonl` (created automatically on first use, and
excluded from version control via `.gitignore`). Each record contains:

- `timestamp` — when the decision was made
- `case_id` — which case was reviewed
- `ai_diagnosis` — the full structured AI output
- `ai_confidence` — the AI's self-reported confidence
- `checker_result` — the deterministic rule checker output
- `human_decision` — `ACCEPTED`, `EDITED`, or `REJECTED`
- `edited_commands` — present only for `EDITED` decisions
- `rejection_reason` — present only for `REJECTED` decisions
- `final_status` — a human-readable summary of the outcome

`audit.compute_statistics()` aggregates this log to calculate total
cases, accepted/edited/rejected counts, and an **AI-human agreement
rate** (the percentage of diagnoses accepted with no changes at all).

## Why human review matters here

The AI diagnosis engine only sees text evidence (symptom description,
topology notes, and pasted `show` command output). It cannot verify
anything against a real device, and it can misread ambiguous or
incomplete evidence — exactly like a junior network engineer working
from a trouble ticket. The rule checker in `checker.py` catches many
common patterns deterministically, but it is intentionally narrow, so
the AI (and ultimately the human reviewer) must fill the gaps.

The five cases below are **documented, worked examples** showing how a
human reviewer would correct a plausible-but-wrong AI diagnosis. They
are written to be added to the audit log via the "Reject" or "Edit"
workflow during a live class demonstration, and they illustrate the
kind of reasoning error a reviewer should watch for.

---

## Corrected AI Diagnosis #1

**Case:** NET-035

**AI Answer:** "An access-list is actively blocking traffic from VLAN
10 to VLAN 30."

**Human Decision:** REJECTED

**Correct Answer:** The ACL referenced by the interface is empty /
already cleared; the real issue is a stale `ip access-group` reference
left applied to the interface, not active deny rules.

**Why AI Was Wrong:** The AI over-weighted the presence of an
`ip access-group 101 in` line without checking that ACL 101 itself had
no entries. It inferred an active block from a reference alone.

**Evidence:** `show access-lists 101` returned no entries, meaning the
access list was empty — the AI should have flagged this contradiction
instead of asserting an active deny.

**Lesson:** Always check whether a referenced object (ACL, route-map,
VLAN) actually still exists/has content before concluding it is the
active cause of a symptom.

---

## Corrected AI Diagnosis #2

**Case:** NET-014

**AI Answer:** "The ACL is blocking DHCP-related traffic to VLAN 10."

**Human Decision:** REJECTED

**Correct Answer:** The DHCP pool named `VLAN10` was bound to the wrong
network (`192.168.99.0` instead of `192.168.10.0`), which is a scope
misconfiguration, not an ACL problem.

**Why AI Was Wrong:** No ACL evidence was present in the supplied show
output at all; the AI defaulted to a common failure pattern (ACL
blocking) instead of grounding its answer in the actual DHCP pool
configuration text that was provided.

**Evidence:** `show ip dhcp pool VLAN10` output showed
`network 192.168.99.0 255.255.255.0` under a pool intended for the
`192.168.10.0/24` subnet.

**Lesson:** The AI must ground every claim in the literal evidence
supplied, not in a generic assumption about which fault "usually"
causes a given symptom.

---

## Corrected AI Diagnosis #3

**Case:** NET-002

**AI Answer:** "VLAN 10 and VLAN 20 router sub-interfaces are
misconfigured and need to be recreated."

**Human Decision:** EDITED

**Correct Answer:** The sub-interfaces were configured correctly; the
real next step was to check the routing table and any ACLs applied to
the sub-interfaces, since inter-VLAN routing configuration alone
looked correct in the evidence.

**Why AI Was Wrong:** The AI concluded the sub-interfaces were broken
even though the supplied `show run` output showed valid IP addressing
and encapsulation for both VLANs. It jumped to a fix ("recreate
interfaces") without first calling for the verification step
(`show ip route`) needed to isolate the actual blocker.

**Evidence:** Both `interface GigabitEthernet0/0.10` and
`.20` showed correct `encapsulation dot1Q` and `ip address` lines.

**Lesson:** When configuration evidence looks correct, the AI should
recommend the next diagnostic command rather than proposing a
destructive "recreate the interface" fix.

---

## Corrected AI Diagnosis #4

**Case:** NET-026

**AI Answer:** "PC1's default gateway is misconfigured, preventing
communication with PC2."

**Human Decision:** REJECTED

**Correct Answer:** Both PC1 and PC2 were assigned the exact same IP
address (`192.168.10.25`), which is a duplicate IP conflict — not a
gateway problem — and explains the intermittent behavior described in
the symptom.

**Why AI Was Wrong:** The AI focused on gateway configuration, a
common Layer 3 fault, without cross-checking the two `ipconfig` outputs
against each other for a duplicate address, even though both were
supplied as evidence.

**Evidence:** `PC1> ipconfig` and `PC2> ipconfig` both showed
`IP Address: 192.168.10.25`.

**Lesson:** When multiple hosts' configuration snippets are supplied
together, the AI (and the deterministic checker) should compare them
against each other, not just analyze each one in isolation.

---

## Corrected AI Diagnosis #5

**Case:** NET-009

**AI Answer:** "EIGRP is misconfigured on R1 and R2; restart EIGRP on
all routers."

**Human Decision:** EDITED

**Correct Answer:** Only the newly added router R3 was missing its
EIGRP `network` statements; R1 and R2 were unaffected and did not need
any changes.

**Why AI Was Wrong:** The AI over-generalized a fix across the whole
topology ("restart EIGRP on all routers") instead of pinpointing the
one router (R3) whose evidence actually showed the problem
(`show ip eigrp neighbors` returning no neighbors on R3 specifically).

**Evidence:** The evidence was explicitly scoped to `R3#show ip eigrp
neighbors` and `R3#show run | include autonomous-system`; no evidence
about R1/R2 misconfiguration was supplied.

**Lesson:** Fix recommendations should be scoped only to the device(s)
actually supported by the evidence, to avoid unnecessary or risky
changes on unrelated equipment.

---

## Summary

These five corrected cases were deliberately designed to demonstrate
common AI failure modes in a network-troubleshooting context:

1. Concluding an object is "active" without checking its contents.
2. Defaulting to a common pattern instead of grounding in supplied evidence.
3. Proposing a fix instead of asking for more verification when evidence is ambiguous.
4. Failing to cross-reference multiple pieces of evidence against each other.
5. Over-scoping a fix beyond what the evidence supports.

This is exactly why NetSage AI treats every AI diagnosis as a
**recommendation only** — a human reviewer must Approve, Edit, or
Reject it before it is considered final, and every decision is
permanently recorded in the audit log for later review and
AI-vs-human agreement analysis.

"""
app.py
======
NetSage - AI-assisted Cisco/Packet Tracer network troubleshooting helper.

Streamlit UI with three sections:
  1. Troubleshoot  - symptom/topology/evidence -> AI + Python -> human review
  2. Evaluation    - run the automated benchmark over cases/cases.csv
  3. Dashboard     - real metrics computed from saved results
"""

import json

import streamlit as st

import ai_engine
import comparator
import evaluation
import human_review
import rule_checker

st.set_page_config(page_title="NetSage", page_icon="🦋", layout="wide")

if "last_diagnosis" not in st.session_state:
    st.session_state.last_diagnosis = None  # AI result dict
if "last_python_result" not in st.session_state:
    st.session_state.last_python_result = None
if "last_comparison" not in st.session_state:
    st.session_state.last_comparison = None
if "last_case_ref" not in st.session_state:
    st.session_state.last_case_ref = None
if "review_recorded" not in st.session_state:
    st.session_state.review_recorded = False

st.title("🦋 NetSage")
st.caption("AI-assisted Cisco / Packet Tracer network troubleshooting helper")

tab_troubleshoot, tab_evaluation, tab_dashboard = st.tabs(
    ["🔍 Troubleshoot", "🚀 Evaluation", "📊 Dashboard"]
)

# =============================================================================
# TAB 1 — TROUBLESHOOT
# =============================================================================
with tab_troubleshoot:
    st.subheader("Network Symptom")
    symptom = st.text_input(
        "What is going wrong?",
        placeholder="PC cannot reach the router.",
        key="symptom_input",
    )

    st.subheader("Topology / Connections")
    topology = st.text_input(
        "How are the devices connected?",
        placeholder="PC0-Switch0, Switch0-Router0",
        key="topology_input",
    )

    st.subheader("Network Evidence")
    evidence = st.text_area(
        "Paste show-command output or other Packet Tracer evidence",
        height=220,
        placeholder=(
            "show ip interface brief\n\n"
            "GigabitEthernet0/0\n192.168.10.1\nadministratively down\ndown"
        ),
        key="evidence_input",
    )

    diagnose_clicked = st.button("🔍 Diagnose", type="primary")

    if diagnose_clicked:
        if not symptom.strip() or not topology.strip() or not evidence.strip():
            st.error(
                "Symptom, Topology, and Evidence are all required. "
                "Please fill in every field before running a diagnosis."
            )
        else:
            with st.spinner("Sending symptom/topology/evidence to the AI..."):
                ai_result = ai_engine.diagnose(symptom, topology, evidence)
            with st.spinner("Running independent Python verification..."):
                python_result = rule_checker.check_evidence(symptom, topology, evidence)

            st.session_state.last_diagnosis = ai_result
            st.session_state.last_python_result = python_result
            st.session_state.last_case_ref = f"{symptom[:40]}"
            st.session_state.review_recorded = False

            if ai_result["ok"]:
                comparison = comparator.compare(
                    ai_result["data"].get("root_cause", ""),
                    python_result["finding"],
                    python_result["status"],
                )
            else:
                comparison = "UNVERIFIED"
            st.session_state.last_comparison = comparison

    # ---- Display results (persist across reruns via session_state) --------
    ai_result = st.session_state.last_diagnosis
    python_result = st.session_state.last_python_result
    comparison = st.session_state.last_comparison

    if ai_result is not None:
        st.divider()
        st.markdown("### AI Diagnosis")

        if not ai_result["ok"]:
            st.error(f"⚠️ AI diagnosis unavailable: {ai_result['error']}")
            st.info(
                "The Python verification result below is still independent "
                "and valid, but there is no AI diagnosis to compare it "
                "against, and the recommendation cannot be trusted until "
                "the AI call succeeds."
            )
        else:
            data = ai_result["data"]
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**ROOT CAUSE**")
                st.write(data.get("root_cause", "—"))
                st.markdown("**CONFIDENCE**")
                conf = data.get("confidence")
                if isinstance(conf, (int, float)):
                    st.progress(min(max(conf, 0.0), 1.0), text=f"{conf:.0%}")
                else:
                    st.write(conf)
            with col2:
                st.markdown("**EVIDENCE**")
                for e in data.get("evidence", []) or ["—"]:
                    st.write(f"- {e}")
                st.markdown("**NEXT DIAGNOSTIC COMMAND**")
                st.code(data.get("next_command", "—"))

            st.markdown("**FIX STEPS**")
            for i, step in enumerate(data.get("fix_steps", []) or [], start=1):
                st.write(f"{i}. {step}")

        st.divider()
        st.markdown("### Python Verification (independent)")
        status_color = {
            "ISSUE_FOUND": "🟠",
            "NO_ISSUE_FOUND": "🟢",
            "UNVERIFIED": "⚪",
        }.get(python_result["status"], "⚪")
        st.write(f"{status_color} **Status:** {python_result['status']}")
        st.write(f"**Finding:** {python_result['finding']}")
        with st.expander("Evidence / explanation"):
            st.write(f"**Evidence used:** {python_result['evidence'] or '—'}")
            st.write(python_result["explanation"])

        st.divider()
        st.markdown("### AI ↔ Python")
        comparison_display = {
            "MATCH": ("🟢 MATCH", "The AI diagnosis and the independent Python "
                                   "check point to the same underlying issue."),
            "CONFLICT": ("🔴 CONFLICT", "The AI diagnosis and the independent "
                                        "Python check DISAGREE. Review carefully "
                                        "before trusting either one."),
            "UNVERIFIED": ("⚪ UNVERIFIED", "The Python checker could not "
                                            "independently confirm or deny the "
                                            "AI's diagnosis from the evidence given."),
        }
        label, explanation = comparison_display.get(comparison, ("⚪ UNVERIFIED", ""))
        st.markdown(f"## {label}")
        st.caption(explanation)

        st.divider()
        st.warning(
            "⚠️ This recommendation requires human judgment. NetSage will "
            "never automatically apply a fix to a router or network. "
            "Review the diagnosis below and choose how to proceed."
        )
        st.markdown("### Human Review")

        if st.session_state.review_recorded:
            st.success("✅ Your review decision has been recorded.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("✅ ACCEPT", use_container_width=True):
                    human_review.record_review(
                        st.session_state.last_case_ref, "ACCEPT",
                        ai_result.get("data") if ai_result["ok"] else None,
                    )
                    st.session_state.review_recorded = True
                    st.rerun()
            with c2:
                with st.popover("✏️ EDIT", use_container_width=True):
                    edit_text = st.text_area("Corrected diagnosis / fix", key="edit_text")
                    edit_reason = st.text_input("Reason for the correction", key="edit_reason")
                    if st.button("Save correction", key="save_edit"):
                        if edit_text.strip() and edit_reason.strip():
                            human_review.record_review(
                                st.session_state.last_case_ref, "EDIT",
                                ai_result.get("data") if ai_result["ok"] else None,
                                correction=edit_text, reason=edit_reason,
                                evidence=evidence,
                            )
                            st.session_state.review_recorded = True
                            st.rerun()
                        else:
                            st.error("Provide both a corrected diagnosis and a reason.")
            with c3:
                with st.popover("❌ REJECT", use_container_width=True):
                    reject_reason = st.text_input("Reason for rejecting (optional)", key="reject_reason")
                    if st.button("Confirm reject", key="confirm_reject"):
                        human_review.record_review(
                            st.session_state.last_case_ref, "REJECT",
                            ai_result.get("data") if ai_result["ok"] else None,
                            correction=("Rejected: no fix should be applied"
                                        if reject_reason.strip() else None),
                            reason=reject_reason.strip() or None,
                            evidence=evidence,
                        )
                        st.session_state.review_recorded = True
                        st.rerun()

# =============================================================================
# TAB 2 — EVALUATION
# =============================================================================
with tab_evaluation:
    st.subheader("Automated Benchmark Evaluation")
    st.write(
        "Runs every case in `cases/cases.csv` through the AI (symptom/topology"
        "/evidence only) and the Python checker, then scores AI diagnoses "
        "against the hidden `expected_fault` ground truth. Re-running updates "
        "each case's single current result — it never creates duplicates."
    )

    try:
        cases_preview = evaluation.load_cases()
        st.info(f"**{len(cases_preview)} case(s)** currently in cases/cases.csv")
    except ValueError as e:
        cases_preview = []
        st.error(f"Cannot load cases.csv: {e}")

    run_clicked = st.button("🚀 RUN EVALUATION", type="primary", disabled=not cases_preview)

    if run_clicked:
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def _progress(current, total, case_id):
            status_text.text(f"Evaluating Case {current} / {total} ({case_id})")
            progress_bar.progress(current / total)

        try:
            results = evaluation.run_evaluation(progress_callback=_progress)
            status_text.text(f"Done — evaluated {len(results)} case(s).")
            st.success("Evaluation complete. Results saved to results/evaluation_results.json")
        except ValueError as e:
            st.error(f"Evaluation could not run: {e}")

    st.divider()
    st.markdown("#### Current saved results")
    saved = evaluation.load_results()
    if saved:
        rows = []
        for case_id, r in sorted(saved.items()):
            rows.append({
                "Case": case_id,
                "AI Root Cause": r.get("ai_root_cause") or f"⚠ {r.get('error')}",
                "Python Status": r.get("python_status"),
                "AI↔Python": r.get("comparison"),
                "Correct?": "✅" if r.get("ai_correct") else "❌",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.write("No evaluation results yet. Click **RUN EVALUATION** above.")

# =============================================================================
# TAB 3 — DASHBOARD
# =============================================================================
with tab_dashboard:
    st.subheader("NetSage Dashboard")

    stats = evaluation.compute_dashboard_stats()
    review_stats = human_review.review_summary()

    m1, m2, m3 = st.columns(3)
    m1.metric("Evaluation Cases", stats["evaluated_cases"] if stats["evaluated_cases"]
               else f"0 / {stats['total_cases']}")
    m2.metric("AI Accuracy",
               f"{stats['ai_accuracy_pct']}%" if stats["ai_accuracy_pct"] is not None
               else "Not yet evaluated")
    if review_stats["ai_human_agreement_pct"] is not None:
        m3.metric("AI ↔ Human Agreement", f"{review_stats['ai_human_agreement_pct']}%")
    else:
        m3.metric("AI ↔ Human Agreement", "No human reviews yet")

    st.divider()
    col_issue, col_sev = st.columns(2)

    with col_issue:
        st.markdown("**Issue Types** (from case dataset)")
        if stats["issue_type_counts"]:
            st.bar_chart(stats["issue_type_counts"])
        else:
            st.write("No cases loaded.")

    with col_sev:
        st.markdown("**Severity** (from case dataset)")
        if stats["severity_counts"]:
            st.bar_chart(stats["severity_counts"])
        else:
            st.write("No cases loaded.")

    st.divider()
    st.markdown("**Human Review**")
    r1, r2, r3 = st.columns(3)
    r1.metric("Accepted", review_stats["accepted"])
    r2.metric("Edited", review_stats["edited"])
    r3.metric("Rejected", review_stats["rejected"])
    st.caption(
        "These counts come from real Accept/Edit/Reject decisions made in "
        "the Troubleshoot tab during normal use — not from benchmark evaluation."
    )

    st.divider()
    st.markdown("**Responsible AI — Logged Corrections**")
    rai_log = human_review.load_responsible_ai_log()
    st.write(f"{len(rai_log)} genuine human correction(s) logged.")
    if rai_log:
        with st.expander("View Responsible AI log"):
            st.json(rai_log)

"""
evaluation.py
=============
Automated benchmark evaluation engine.

Loads cases/cases.csv, runs each case through the AI (symptom/topology
/evidence ONLY - never expected_fault/osi_layer/concept/severity),
runs the independent Python rule checker, compares AI vs Python and
AI vs the hidden ground truth, and writes/updates
results/evaluation_results.json (one current record per case_id).

This module supports any number of cases; nothing here hard-codes 15
or 30.
"""

import csv
import json
import os
from datetime import datetime, timezone

import ai_engine
import rule_checker
import comparator

BASE_DIR = os.path.dirname(__file__)
CASES_PATH = os.path.join(BASE_DIR, "cases", "cases.csv")
RESULTS_PATH = os.path.join(BASE_DIR, "results", "evaluation_results.json")

# Fields that must NEVER be sent to the AI during evaluation.
GROUND_TRUTH_FIELDS = ("expected_fault", "osi_layer", "concept", "severity")


def load_cases():
    """Load all cases from cases.csv. Returns a list of dicts.
    Raises ValueError on invalid CSV or duplicate case_ids."""
    if not os.path.exists(CASES_PATH):
        raise ValueError(f"cases.csv not found at {CASES_PATH}")

    with open(CASES_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {"case_id", "symptom", "topology", "show_outputs", "expected_fault"}
        if reader.fieldnames is None or not required_cols.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"cases.csv is missing required columns. Found: {reader.fieldnames}"
            )
        rows = list(reader)

    seen = set()
    for row in rows:
        cid = row.get("case_id")
        if not cid:
            raise ValueError("Found a case row with an empty case_id.")
        if cid in seen:
            raise ValueError(f"Duplicate case_id found in cases.csv: {cid}")
        seen.add(cid)

    return rows


def load_results():
    if not os.path.exists(RESULTS_PATH):
        return {}
    try:
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            data = json.loads(content)
            # stored as {case_id: record} to guarantee one current
            # record per case_id, no matter how many times we run.
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_results(results_by_case_id: dict):
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results_by_case_id, f, indent=2)


def _score_ai_correct(ai_root_cause: str, expected_fault: str) -> bool:
    """Score a benchmark diagnosis by normalized fault category.

    This is deliberately deterministic and conservative: there is no loose
    word-overlap fallback that could mark an unrelated diagnosis as correct.
    """
    if not ai_root_cause or not expected_fault:
        return False
    ai_categories = comparator._categorize(ai_root_cause)
    expected_categories = comparator._categorize(expected_fault)
    return bool(ai_categories and expected_categories and
                ai_categories.intersection(expected_categories))


def run_evaluation(progress_callback=None):
    """
    Runs every case in cases.csv through AI + Python verification,
    scores AI accuracy against the hidden expected_fault, and updates
    results/evaluation_results.json (one current record per case_id).

    progress_callback(current_index, total, case_id) is called before
    each case is processed, if provided.

    Returns the full results dict (case_id -> record).
    """
    cases = load_cases()
    results = load_results()
    total = len(cases)

    for i, case in enumerate(cases, start=1):
        case_id = case["case_id"]
        if progress_callback:
            progress_callback(i, total, case_id)

        symptom = case.get("symptom", "")
        topology = case.get("topology", "")
        evidence = case.get("show_outputs", "")
        expected_fault = case.get("expected_fault", "")

        # --- Ground truth protection -----------------------------------
        # Only symptom/topology/evidence are ever passed to the AI.
        ai_response = ai_engine.diagnose(symptom, topology, evidence)

        python_result = rule_checker.check_evidence(symptom, topology, evidence)

        if ai_response["ok"]:
            ai_data = ai_response["data"]
            ai_root_cause = ai_data.get("root_cause", "")
            comparison = comparator.compare(
                ai_root_cause, python_result["finding"], python_result["status"]
            )
            ai_correct = _score_ai_correct(ai_root_cause, expected_fault)
            record = {
                "case_id": case_id,
                "ai_root_cause": ai_root_cause,
                "ai_confidence": ai_data.get("confidence"),
                "ai_evidence": ai_data.get("evidence"),
                "python_finding": python_result["finding"],
                "python_status": python_result["status"],
                "comparison": comparison,
                "expected_fault": expected_fault,
                "ai_correct": ai_correct,
                "error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            # One failed API call must not stop the whole evaluation.
            record = {
                "case_id": case_id,
                "ai_root_cause": None,
                "ai_confidence": None,
                "ai_evidence": None,
                "python_finding": python_result["finding"],
                "python_status": python_result["status"],
                "comparison": "UNVERIFIED",
                "expected_fault": expected_fault,
                "ai_correct": False,
                "error": ai_response["error"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        # One current record per case_id - overwrite, never duplicate.
        results[case_id] = record

    save_results(results)
    return results


def compute_dashboard_stats():
    """Compute AI accuracy and issue/severity breakdowns purely from
    saved evaluation_results.json + cases.csv metadata. Nothing here
    is hard-coded."""
    results = load_results()
    cases = {c["case_id"]: c for c in load_cases()} if os.path.exists(CASES_PATH) else {}

    evaluated = [r for r in results.values() if r.get("error") is None]
    total_evaluated = len(evaluated)
    correct = sum(1 for r in evaluated if r.get("ai_correct"))
    ai_accuracy = round(correct / total_evaluated * 100, 1) if total_evaluated else None

    issue_type_counts = {}
    severity_counts = {}
    for case_id, case in cases.items():
        concept = case.get("concept", "Unknown")
        severity = case.get("severity", "Unknown")
        issue_type_counts[concept] = issue_type_counts.get(concept, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    return {
        "total_cases": len(cases),
        "evaluated_cases": total_evaluated,
        "ai_accuracy_pct": ai_accuracy,
        "issue_type_counts": issue_type_counts,
        "severity_counts": severity_counts,
    }

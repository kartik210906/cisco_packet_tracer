# 🦋 NetSage

**NetSage** is an AI-assisted Cisco / Packet Tracer network troubleshooting
helper. You give it a symptom, a topology, and command-output evidence; it
returns an AI diagnosis, an **independent** Python rule-check, a comparison
between the two, and requires a human to Accept, Edit, or Reject the result
before anything is treated as final. NetSage never touches a router — it
only recommends.

## What NetSage does

```
Symptom + Topology + Evidence
            ↓
        AI Diagnosis  (Gemini)
            ↓
     Python Verification (deterministic, rule-based, no AI)
            ↓
      AI ↔ Python  →  MATCH / CONFLICT / UNVERIFIED
            ↓
   Human Review  →  ACCEPT / EDIT / REJECT
```

It also ships an **automated benchmark evaluator** that runs a labeled test
dataset end-to-end (AI never sees the expected answer) and a **dashboard**
that reports real, computed metrics — nothing hard-coded.

## Architecture

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI — Troubleshoot / Evaluation / Dashboard tabs |
| `ai_engine.py` | Calls Gemini with symptom/topology/evidence only; validates JSON output |
| `rule_checker.py` | Independent, deterministic evidence checks (never calls the AI) |
| `comparator.py` | Compares AI root cause vs Python finding → MATCH/CONFLICT/UNVERIFIED |
| `human_review.py` | Records Accept/Edit/Reject decisions; logs genuine corrections |
| `evaluation.py` | Loads `cases/cases.csv`, runs the benchmark, writes `results/evaluation_results.json` |
| `prompts/diagnose_prompt.md` | The single official AI prompt (with worked examples) |
| `cases/cases.csv` | Benchmark dataset (expandable, any number of rows) |
| `results/evaluation_results.json` | One current record per `case_id` |
| `responsible_ai/responsible_ai_log.json` | Genuine human corrections only |
| `human_review/reviews.json` | Lightweight Accept/Edit/Reject counters from normal use (kept separate from benchmark data) |

## Installation

```bash
cd NetSage
python3 -m venv .venv          # optional but recommended
source .venv/bin/activate
pip install -r requirements.txt
```

## API setup

1. Get a Gemini API key from Google AI Studio.
2. Copy the example env file and fill in your key:

```bash
cp .env.example .env
# then edit .env:
# GEMINI_API_KEY=your_real_key_here
```

The key is read from the environment only. It is never written to source
code, the README, `cases.csv`, the prompt, or the dashboard.

## How to run the application

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

### Troubleshoot tab
1. Enter Symptom, Topology, and Evidence.
2. Click **🔍 Diagnose**.
3. Review the AI diagnosis, the independent Python finding, and the
   **AI ↔ Python** verdict.
4. Choose **ACCEPT**, **EDIT** (provide a corrected diagnosis + reason),
   or **REJECT** (optionally give a reason). Genuine EDIT/REJECT
   corrections are appended to `responsible_ai/responsible_ai_log.json`.

## How to run evaluation

Go to the **🚀 Evaluation** tab and click **RUN EVALUATION**. This:
1. Loads every case in `cases/cases.csv`.
2. Sends only `symptom` / `topology` / `show_outputs` to the AI (never
   `expected_fault`, `osi_layer`, `concept`, or `severity`).
3. Runs the Python checker on the same evidence.
4. Compares AI vs Python, and AI vs the hidden `expected_fault`.
5. Continues past any single failed API call instead of stopping.
6. Shows `Evaluating Case N / total` progress.
7. Saves/updates one current result per `case_id` in
   `results/evaluation_results.json` (re-running never duplicates rows).

## Number of test cases currently included

**15 cases**, covering VLAN, Gateway, DHCP, DNS, Routing, ACL, NAT, and
Wireless. Nothing in the code hard-codes this number — add more rows to
`cases/cases.csv` (e.g. to reach 30) and the evaluator will process
however many rows exist.

## How AI accuracy is calculated

```
AI Accuracy = correct AI diagnoses / evaluated cases × 100
```

computed live from `results/evaluation_results.json` by
`evaluation.compute_dashboard_stats()`. "Correct" is decided by a
transparent keyword/category-overlap check between the AI's `root_cause`
and the case's hidden `expected_fault` (see `_score_ai_correct` in
`evaluation.py`) — nothing is fabricated or hand-set.

## How Python verification works

`rule_checker.py` never calls the AI. It applies fixed, deterministic
rules to the evidence text for:

1. Duplicate IP addresses
2. Wrong / mismatched subnet masks
3. Default gateway mismatch
4. Interface down / administratively down
5. Missing VLAN
6. Missing routes

If none of these patterns can be confidently identified in the evidence,
the checker returns `UNVERIFIED` rather than guessing. Categories outside
this rule set (e.g. DHCP, DNS, ACL, NAT, Wireless specifics) will
correctly come back `UNVERIFIED` unless they happen to also trip one of
the six general rules above — the checker is intentionally narrow so it
never fabricates a verdict it can't support.

## How Accept/Edit/Reject works

Human review is mandatory in the Troubleshoot workflow. NetSage never
executes a fix automatically.

- **ACCEPT** — logs the decision only; no automatic action is taken.
- **EDIT** — you provide a corrected diagnosis/fix and a reason. This is
  saved both as a review record and, since it's a genuine correction, in
  the Responsible AI log.
- **REJECT** — you may give a reason. If given, it's also logged as a
  Responsible AI correction.

This is called "AI ↔ Human Agreement" in the dashboard, never "human
accuracy" — there is no ground truth for a live troubleshooting session,
only whether the human agreed with the AI.

## How Dashboard works

The **📊 Dashboard** tab is inside `app.py` and reads only saved data —
`results/evaluation_results.json`, `cases/cases.csv`, and
`human_review/reviews.json`. It shows:

- Evaluation Cases and AI Accuracy (from evaluation results)
- AI ↔ Human Agreement (only shown once at least one real human review
  exists — never fabricated)
- Issue Types and Severity breakdown (from the case dataset)
- Human Review counts: Accepted / Edited / Rejected (from real Troubleshoot
  tab usage, kept separate from benchmark data)
- Number of genuine Responsible AI corrections logged

## How Responsible AI logging works

`responsible_ai/responsible_ai_log.json` only receives entries when a
human performs a real EDIT or REJECT with an actual corrected diagnosis
and reason in the Troubleshoot tab (see `human_review.record_review`).
Nothing here is auto-generated by the AI, and the app will not fabricate
entries to hit any target count. **The project specification calls for at
least 5 genuine corrected responses** — perform 5 real EDIT/REJECT
corrections during use (e.g. by intentionally testing cases where you
disagree with the AI) to build this evidence honestly.

## Dataset format (`cases/cases.csv`)

Columns: `case_id, symptom, topology, show_outputs, expected_fault,
osi_layer, concept, severity`. `expected_fault` is the hidden ground
truth and is only used after the AI has already produced its diagnosis —
it is never included in the request sent to the AI.

## Limitations

- The Python rule checker only recognizes six general fault patterns; it
  will correctly report `UNVERIFIED` for many DHCP/DNS/ACL/NAT/Wireless
  cases where the evidence doesn't also trip one of those six rules. This
  is by design (never guess), not a bug.
- AI-correctness scoring uses keyword/category overlap, not true semantic
  understanding — it's a transparent, inspectable heuristic, not a claim
  of perfect grading.
- Gemini API errors (missing key, timeout, malformed JSON) are handled
  gracefully and shown as errors rather than silently producing an
  unreliable diagnosis.
- NetSage is a decision-support tool only. It never applies configuration
  changes to a router, switch, or any other device — a human must always
  apply fixes manually in Packet Tracer.

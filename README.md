# 🦋 NetSage

**NetSage** is an AI-assisted Cisco / Packet Tracer network troubleshooting
helper. You give it a symptom, a topology, and command-output evidence; it
returns an AI diagnosis, an **independent** Python rule-check, a comparison
between the two, and requires a human to Accept, Edit, or Reject the result
before anything is treated as final. NetSage never touches a router — it
only recommends.

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

It also ships an **automated benchmark evaluator** that runs a labeled,
30-case test dataset end-to-end (the AI never sees the expected answer)
and a **dashboard** that reports metrics computed live from saved results
— nothing hard-coded.

---

## 1. Architecture

```
NetSage/
├── app.py                          ← MAIN PROGRAM (Streamlit UI, run this)
├── ai_engine.py                    ← Calls Gemini; validates its JSON output
├── rule_checker.py                 ← Independent deterministic evidence checks
├── comparator.py                   ← AI vs Python → MATCH / CONFLICT / UNVERIFIED
├── human_review.py                 ← Records Accept / Edit / Reject decisions
├── evaluation.py                   ← Runs the automated benchmark
│
├── prompts/
│   └── diagnose_prompt.md          ← The single official AI prompt
│
├── cases/
│   └── cases.csv                   ← 30-case benchmark dataset
│
├── results/
│   └── evaluation_results.json     ← One current record per case_id
│
├── responsible_ai/
│   └── responsible_ai_log.json     ← Genuine human corrections only
│
├── human_review/
│   └── reviews.json                ← Lightweight Accept/Edit/Reject log (normal use)
│
├── test_rule_checker.py            ← Unit tests for rule_checker.py
├── test_evaluation_scoring.py      ← Unit tests for evaluation scoring
│
├── .env / .env.example             ← GEMINI_API_KEY (never committed)
├── .gitignore
├── requirements.txt
└── README.md
```

| File | Responsibility |
|---|---|
| `app.py` | **Main program.** Streamlit UI with Troubleshoot / Evaluation / Dashboard tabs. |
| `ai_engine.py` | Sends symptom/topology/evidence to Gemini only; validates the returned JSON, never crashes on a bad response. |
| `rule_checker.py` | Deterministic checks (duplicate IP, subnet mask, gateway mismatch, interface down, missing VLAN, missing route) using Python's `ipaddress` module. Never calls the AI. |
| `comparator.py` | Categorizes and compares the AI's root cause against the Python finding. |
| `human_review.py` | Records ACCEPT / EDIT / REJECT; logs genuine corrections to Responsible AI. |
| `evaluation.py` | Loads `cases/cases.csv`, runs every case through AI + Python, scores AI accuracy against the hidden `expected_fault`, writes `results/evaluation_results.json`. |
| `prompts/diagnose_prompt.md` | The exact prompt sent to Gemini, with worked examples. |

### Data flow

**Normal troubleshooting (Troubleshoot tab):**
```
User enters Symptom / Topology / Evidence
        ↓
ai_engine.diagnose()  →  Gemini
        ↓
rule_checker.check_evidence()  (independent, runs regardless of AI success)
        ↓
comparator.compare()  →  MATCH / CONFLICT / UNVERIFIED
        ↓
human_review.record_review()  →  ACCEPT / EDIT / REJECT
        ↓ (if EDIT/REJECT with a real correction + reason)
responsible_ai_log.json
```

**Automated evaluation (Evaluation tab):**
```
cases/cases.csv
        ↓
evaluation.run_evaluation()
        ↓ for each case: symptom/topology/evidence ONLY → AI
        ↓                rule_checker on the same evidence
        ↓                comparator (AI vs Python)
        ↓                score AI vs hidden expected_fault
results/evaluation_results.json  (one record per case_id, re-running overwrites, never duplicates)
        ↓
Dashboard tab reads this file and computes AI Accuracy / issue-type / severity charts live
```

---

## 2. Installation

```bash
cd NetSage

python3 -m venv .venv          # optional but recommended
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## 3. API setup

1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/).
2.Edit `.env`:
```
GEMINI_API_KEY=your_real_key_here
```

The key is read from the environment only — it's never written to source
code, the README, `cases.csv`, the prompt, or the dashboard, and `.env` is
already listed in `.gitignore`.

---

## 4. How to run the main program

From inside the `NetSage/` folder:

```bash
streamlit run app.py
```

Streamlit will print a local URL (usually `http://localhost:8501`) — open
it in a browser. You'll see three tabs:

- **🔍 Troubleshoot** — enter a symptom, topology, and evidence, click
  **Diagnose**, then review the AI diagnosis, the independent Python
  finding, and the AI ↔ Python verdict. Choose **ACCEPT**, **EDIT**
  (provide a corrected diagnosis + reason), or **REJECT**.
- **🚀 Evaluation** — click **RUN EVALUATION** to process every case in
  `cases/cases.csv` automatically and save results.
- **📊 Dashboard** — view AI Accuracy, AI ↔ Human Agreement, issue-type
  and severity breakdowns, and human review counts, all computed live
  from the saved JSON files.

## 5. How to run evaluation from the command line (optional)

You don't have to use the UI button — you can also run it directly:

```bash
python3 -c "import evaluation; evaluation.run_evaluation(progress_callback=lambda i,t,c: print(f'{i}/{t} {c}'))"
```

This requires a valid `GEMINI_API_KEY` in `.env`; without one, each case
will be recorded with an error instead of an AI diagnosis (evaluation
still completes — one failed API call never stops the run).

## 6. How to run the tests

```bash
python3 test_rule_checker.py
python3 test_evaluation_scoring.py
```

Both are plain-Python test scripts (no pytest required), and both are
independent of the Gemini API — they exercise `rule_checker.py` and the
scoring logic in `evaluation.py` directly.

---

## 7. Dataset

`cases/cases.csv` currently ships with **30 cases** across VLAN, Gateway,
DHCP, DNS, Routing, ACL, NAT, Wireless, OSPF, Trunking, and Duplex
scenarios. Columns: `case_id, symptom, topology, show_outputs,
expected_fault, osi_layer, concept, severity`. `expected_fault` is the
hidden benchmark answer and is only used *after* the AI has produced its
diagnosis — it's never included in the request sent to the AI.

## 8. Current data status (read before demoing)

- `results/evaluation_results.json` currently contains placeholder-style
  data, not the output of a real evaluation run. Run **RUN EVALUATION**
  (with a real API key) before presenting AI Accuracy numbers.
- `responsible_ai/responsible_ai_log.json` is empty. Perform at least 5
  genuine EDIT/REJECT corrections in the Troubleshoot tab to populate it.
- `human_review/reviews.json` has a couple of entries that don't match
  the app's own output format — worth clearing and rebuilding through
  normal use before a demo.

## 9. Limitations

- `rule_checker.py` only implements 6 general deterministic rules
  (duplicate IP, subnet mask mismatch between devices explicitly stated
  to share a subnet, gateway mismatch, interface down, missing VLAN,
  missing route). For DNS/DHCP/ACL/NAT/wireless/OSPF/duplex cases it
  correctly returns `UNVERIFIED` unless one of those six patterns is
  also present — this is intentional ("never guess"), not a bug.
- AI-correctness scoring uses keyword/category overlap between the AI's
  root cause and the hidden `expected_fault`, not full semantic
  understanding.
- NetSage is decision-support only. It never applies configuration
  changes to a router, switch, or any other device — a human must always
  apply fixes manually in Packet Tracer.

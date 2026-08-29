"""
ai_engine.py
============
Thin wrapper around the Gemini API used to produce an AI diagnosis for
a Cisco/Packet Tracer troubleshooting case.

Design rules enforced here (see PROJECT spec):
- The API key is NEVER hard-coded; it is read from the environment.
- Only symptom / topology / evidence are ever sent to the model.
  Ground-truth fields (expected_fault, osi_layer, concept, severity)
  must never be passed into this module's public functions.
- All failures (missing key, timeout, malformed JSON) are caught and
  returned as a structured error instead of crashing the app or
  pretending the result is reliable.
"""

import json
import os
import re
import time

from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "gemini-3.5-flash"
REQUEST_TIMEOUT_SECONDS = 30

REQUIRED_FIELDS = ["root_cause", "confidence", "evidence", "next_command", "fix_steps"]

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "diagnose_prompt.md")


def _load_prompt_template() -> str:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _extract_json(text: str):
    """Best-effort extraction of a JSON object from model output that
    may be wrapped in markdown fences or contain leading/trailing prose."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text.strip()).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _validate_diagnosis(data) -> tuple:
    """Returns (is_valid, error_message)."""
    if not isinstance(data, dict):
        return False, "AI response was not a JSON object."
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        return False, f"AI response is missing required field(s): {', '.join(missing)}."
    if not isinstance(data.get("evidence"), list):
        data["evidence"] = [str(data["evidence"])] if data.get("evidence") else []
    if not isinstance(data.get("fix_steps"), list):
        data["fix_steps"] = [str(data["fix_steps"])] if data.get("fix_steps") else []
    try:
        data["confidence"] = float(data["confidence"])
    except (TypeError, ValueError):
        return False, "AI response 'confidence' field is not a valid number."
    return True, None


def diagnose(symptom: str, topology: str, evidence: str) -> dict:
    """
    Send ONLY symptom/topology/evidence to the AI and return a
    structured result:

    {
        "ok": bool,
        "data": { root_cause, confidence, evidence, next_command, fix_steps } | None,
        "error": str | None,
        "raw_response": str | None
    }
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "ok": False,
            "data": None,
            "error": "GEMINI_API_KEY is not set. Add it to your .env file "
                     "(see .env.example) before running a diagnosis.",
            "raw_response": None,
        }

    try:
        import google.generativeai as genai
    except ImportError:
        return {
            "ok": False,
            "data": None,
            "error": "google-generativeai package is not installed. "
                     "Run: pip install -r requirements.txt",
            "raw_response": None,
        }

    try:
        genai.configure(api_key=api_key)
        template = _load_prompt_template()
        prompt = (
            f"{template}\n\n"
            f"---\nCASE INPUT\n---\n"
            f"Symptom: {symptom}\n"
            f"Topology: {topology}\n"
            f"Evidence:\n{evidence}\n"
        )

        model = genai.GenerativeModel(MODEL_NAME)
        start = time.time()
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
            request_options={"timeout": REQUEST_TIMEOUT_SECONDS},
        )
        elapsed = time.time() - start

        raw_text = getattr(response, "text", None) or ""
        data = _extract_json(raw_text)
        is_valid, err = _validate_diagnosis(data)

        if not is_valid:
            return {
                "ok": False,
                "data": None,
                "error": f"AI returned invalid/incomplete JSON: {err}",
                "raw_response": raw_text,
            }

        return {
            "ok": True,
            "data": data,
            "error": None,
            "raw_response": raw_text,
            "latency_seconds": round(elapsed, 2),
        }

    except Exception as exc:
        msg = str(exc)
        if "timeout" in msg.lower() or "deadline" in msg.lower():
            error = f"AI request timed out after {REQUEST_TIMEOUT_SECONDS}s: {msg}"
        else:
            error = f"AI request failed: {msg}"
        return {
            "ok": False,
            "data": None,
            "error": error,
            "raw_response": None,
        }

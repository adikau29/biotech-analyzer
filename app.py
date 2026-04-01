import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if not ANTHROPIC_API_KEY:
    raise RuntimeError("Missing ANTHROPIC_API_KEY — make sure you have a .env file with your key.")

HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json",
}

JSON_SCHEMA = """{
  "company": "Full company name",
  "ticker": "TICKER or null",
  "exchange": "NASDAQ/NYSE/OTC or null",
  "cash_millions": number or null,
  "cash_runway_months": number or null,
  "runway_date": "Quarter Year e.g. Q1 2027, or null",
  "net_loss_quarterly_millions": number or null,
  "trials": [{"name": "drug name", "phase": "Phase 1/2/3", "indication": "disease", "status": "ongoing/enrolling/completed"}],
  "fda_dates": [{"type": "PDUFA/NDA/FDA decision", "date": "Month Year", "drug": "drug name"}],
  "catalysts": ["upcoming catalyst events"],
  "risks": ["risk factors as short strings"],
  "summary": "2-3 sentence investor-grade summary.",
  "data_confidence": "high/medium/low",
  "burn_rate_severity": "critical/warning/healthy or null",
  "trial_success_rates": [{"drug": "name", "phase": "Phase X", "indication": "disease", "historical_rate": "e.g. 40%", "context": "one sentence"}],
  "sentiment": {"score": "positive/neutral/cautious/negative", "signals": ["2-3 signals from management language"]}
}"""


def build_prompt(text, is_search):
    if is_search:
        return (
            f'You are a biotech investor analyst. Today is April 1, 2026. '
            f'Search for the most recent earnings release or SEC filing for: "{text}". '
            f'Extract all data and return ONLY valid raw JSON, no markdown, no backticks:\n{JSON_SCHEMA}'
        )
    else:
        return (
            f'You are a biotech investor analyst. Today is April 1, 2026. '
            f'Extract all data from the filing below and return ONLY valid raw JSON, no markdown, no backticks:\n{JSON_SCHEMA}'
            f'\n\nFiling text:\n{text}'
        )


def run_claude(prompt, use_search=False):
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}] if use_search else []

    for _ in range(10):
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1500,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=HEADERS,
                json=body,
                timeout=60,
            )
        except requests.exceptions.Timeout:
            raise Exception("Request timed out. Try again.")
        except requests.exceptions.ConnectionError:
            raise Exception("Could not reach Claude API. Check your internet connection.")

        if not resp.ok:
            msg = resp.json().get("error", {}).get("message", "Unknown API error")
            raise Exception(f"Claude API error: {msg}")

        data = resp.json()
        content = data.get("content", [])
        stop_reason = data.get("stop_reason", "end_turn")

        if stop_reason == "end_turn":
            return "".join(b.get("text", "") for b in content if b.get("type") == "text")

        if stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": content})
            tool_results = [
                {"type": "tool_result", "tool_use_id": b["id"], "content": ""}
                for b in content if b.get("type") == "tool_use"
            ]
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

    raise Exception("Could not complete analysis. Try again.")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    if not data or not data.get("text", "").strip():
        return jsonify({"error": "No text provided"}), 400

    text = data["text"].strip()
    is_search = len(text) < 200 and "\n" not in text

    # Truncate pasted text to avoid token limits
    if not is_search and len(text) > 10000:
        text = text[:10000] + "\n[truncated]"

    try:
        raw = run_claude(build_prompt(text, is_search), use_search=is_search)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return jsonify({"error": "Claude returned an unexpected response. Try again."}), 500

    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return jsonify({"error": "Could not parse response as JSON. Try again."}), 500

    return jsonify(parsed)


if __name__ == "__main__":
    print("\n✓ Biotech Filing Analyzer running at http://127.0.0.1:5000\n")
    app.run(debug=True, port=5000)

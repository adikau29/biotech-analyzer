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
    raise RuntimeError("Missing ANTHROPIC_API_KEY — check your .env file.")

HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json",
}

MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
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
  "burn_rate_severity": "critical/warning/healthy or null — critical under 6 months, warning 6-12 months, healthy over 12 months",
  "trial_success_rates": [{"drug": "name", "phase": "Phase X", "indication": "disease", "historical_rate": "e.g. 40%", "context": "one sentence"}],
  "sentiment": {"score": "positive/neutral/cautious/negative", "signals": ["2-3 signals from management language"]}
}"""


def build_prompt(text, is_search):
    if is_search:
        return (
            'You are a senior biotech investor analyst. Today is April 1, 2026. '
            'Search the web thoroughly for the most recent earnings release, SEC filing, pipeline update, or any investor information for: "' + text + '". '
            'Search for the company name, ticker symbol, drug names, and any related filings. '
            'Extract ALL available data and return ONLY valid raw JSON, no markdown, no backticks:\n' + JSON_SCHEMA
        )
    else:
        return (
            'You are a senior biotech investor analyst. Today is April 1, 2026. '
            'Extract all data from the filing below and return ONLY valid raw JSON, no markdown, no backticks:\n' + JSON_SCHEMA +
            '\n\nFiling text:\n' + text
        )


def extract_json(raw):
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        try:
            clean = re.sub(r'[\x00-\x1f\x7f]', '', match.group())
            return json.loads(clean)
        except json.JSONDecodeError:
            return None


def run_claude(prompt, model_key="sonnet", use_search=False):
    model = MODELS.get(model_key, MODELS["sonnet"])
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}] if use_search else []

    for _ in range(10):
        body = {
            "model": model,
            "max_tokens": 2000,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=HEADERS,
                json=body,
                timeout=90,
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
    model_key = data.get("model", "sonnet")
    is_search = len(text) < 200 and "\n" not in text

    if not is_search and len(text) > 10000:
        text = text[:10000] + "\n[truncated]"

    # First attempt
    try:
        raw = run_claude(build_prompt(text, is_search), model_key=model_key, use_search=is_search)
        parsed = extract_json(raw)
        if parsed:
            return jsonify(parsed)
    except Exception as e:
        if "rate limit" not in str(e).lower():
            return jsonify({"error": str(e)}), 500

    # Auto retry with broader query for search mode
    if is_search:
        try:
            retry_text = f"{text} biotech pharma pipeline earnings SEC filing clinical trials investor"
            raw = run_claude(build_prompt(retry_text, True), model_key=model_key, use_search=True)
            parsed = extract_json(raw)
            if parsed:
                return jsonify(parsed)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Could not find enough data. Try adding more detail to your search e.g. company name + 'pipeline 2026'"}), 500


if __name__ == "__main__":
    print("\n✓ Biotech Filing Analyzer running at http://127.0.0.1:5000\n")
    app.run(host='0.0.0.0', port=5000)

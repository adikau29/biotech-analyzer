# Biotech Filing Analyzer

An AI-powered tool that extracts investor-grade data from SEC filings, earnings press releases, and clinical readouts — built with Python, Flask, and the Claude API.

Paste in any biotech filing and instantly get:
- Cash on hand & runway
- Active clinical trials by phase
- Upcoming FDA / PDUFA dates
- Key catalysts
- Risk flags
- Analyst summary

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/YOUR_USERNAME/biotech-analyzer.git
cd biotech-analyzer
```

**2. Create a virtual environment**
```bash
python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Add your API key**
```bash
cp .env.example .env
# Open .env and replace with your actual Anthropic API key
```

Get your API key at: https://console.anthropic.com

**5. Run**
```bash
python app.py
```

Open http://localhost:5000 in your browser.

## How it works

1. You paste filing text into the browser UI
2. The frontend sends it to the local Flask server (`/analyze`)
3. Flask calls the Claude API with a structured extraction prompt
4. Claude returns JSON with all extracted fields
5. The UI renders it as a clean data dashboard

The API key stays on the server — it's never exposed to the browser.

## Stack

- **Backend**: Python + Flask
- **AI**: Anthropic Claude (claude-sonnet)
- **Frontend**: Vanilla HTML/CSS/JS (no dependencies)

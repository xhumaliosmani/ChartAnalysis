# Trading Chart Analyzer

Upload candlestick chart screenshots; get back a structured trade decision
(long / short / no-trade), a conviction score, entry zone, stop, targets,
sized position, and a confluence breakdown. Save each call to a local
journal, mark outcomes, and watch real win rate stats build up over time.

The analyst is Claude (`claude-opus-4-7`) with a system prompt that
encodes documented TA frameworks: Dow market structure, support/resistance,
50/200 EMA trend, candlestick reversals at key levels, chart patterns,
Fibonacci retracements, RSI/MACD divergence, Bollinger squeezes, and
Wyckoff volume analysis.

## Features

- **Single-chart mode** — drop one screenshot, get a call.
- **Multi-timeframe mode** — upload a higher timeframe (bias) and lower
  timeframe (entry) chart together; the model uses HTF trend as a
  confluence factor and triggers off the LTF.
- **Position sizing** — enter account size and risk % (default 1%);
  when the model extracts numeric entry/stop from the chart, you get
  the exact position size in units.
- **Trade journal (SQLite)** — save each analysis, then mark the outcome
  (win / loss / BE / skipped) with the actual entry and exit prices.
  R multiple and $ P&L are computed automatically.
- **Stats tab** — overall win rate, average R, total P&L, and win rate
  broken down by conviction bucket. This is the real test: if the
  70–92 bucket doesn't materially outperform the 35–54 bucket, the
  setup quality isn't translating into edge.

## Guardrails baked into the prompt

- **2+ independent factors required.** A single indicator is noise.
- **Conviction capped at 92.** No false certainty.
- **R:R < 1.5 is auto-rejected** even on high-conviction setups.
- **"No trade" is a valid, encouraged output.** Forcing trades on every
  chart is the #1 way to collapse a win rate.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your key from https://console.anthropic.com
```

## Run

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

## Files

- `app.py` — Streamlit UI (Analyze / Journal / Stats tabs)
- `prompts.py` — TA system prompt + single-chart and MTF user prompts
- `db.py` — SQLite-backed journal, sizing math, outcome stats
- `journal.db` — created on first run (gitignored)

## Disclaimer

This tool is for educational analysis. It is not financial advice. No
technical-analysis method wins 100% of the time; the edge comes from
disciplined risk management and selective entries. The stats tab is
there so you can honestly evaluate whether this assistant's calls
perform for *you* on *your* markets.

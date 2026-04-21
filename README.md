# Trading Chart Analyzer

Upload a candlestick chart screenshot; get back a structured trade decision
(long / short / no-trade), a conviction score, entry zone, stop, targets,
and the confluence factors driving the call.

The analyst is Claude (`claude-opus-4-7`) with a system prompt that encodes
documented technical-analysis frameworks: Dow market structure,
support/resistance, 50/200 EMA trend, candlestick reversals at key levels,
classic chart patterns, Fibonacci retracements, RSI/MACD divergence,
Bollinger squeezes, and Wyckoff volume analysis.

## Guardrails it follows

- **2+ aligned factors required.** A single indicator is never a trade.
- **Conviction is capped at 92.** Certainty is a red flag in markets.
- **R:R < 1.5 is auto-rejected** even when conviction is high.
- **"No trade" is a valid output.** Most charts do not present an A+ setup.

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

Open the URL Streamlit prints (usually http://localhost:8501), drop a
chart screenshot in, optionally add notes in the sidebar, and click
**Analyze chart**.

## Output

You get:

- **Direction** — LONG / SHORT / NO TRADE
- **Conviction** — 0–92, colour-coded
- **Market structure** read
- **Entry plan** — type, price zone, trigger
- **Stop loss, T1, T2, R:R, invalidation level**
- **Confluence factors** that support the call
- **Conflicting signals** that argue against it
- Raw JSON for programmatic use

## Disclaimer

This tool is for educational analysis. It is not financial advice. No
technical-analysis method wins 100% of the time; the edge comes from
disciplined risk management and selective entries.

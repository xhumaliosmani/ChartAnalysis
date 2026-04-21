"""Trading Chart Analyzer — Streamlit app.

Upload a chart screenshot; Claude (vision) returns a structured trade
decision grounded in documented technical-analysis methods.

Run:
    streamlit run app.py

Requires ANTHROPIC_API_KEY in environment or in a local .env file.
"""

from __future__ import annotations

import base64
import io
import json
import os
from typing import Any

import streamlit as st
from anthropic import Anthropic, APIError
from dotenv import load_dotenv
from PIL import Image

from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

load_dotenv()

MODEL = "claude-opus-4-7"
MAX_TOKENS = 2048


# ----- Claude call ----------------------------------------------------------

def _encode_image(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        },
    }


def analyze_chart(
    client: Anthropic,
    image_bytes: bytes,
    media_type: str,
    user_notes: str,
) -> dict[str, Any]:
    """Send chart to Claude and return parsed JSON decision."""
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    _encode_image(image_bytes, media_type),
                    {
                        "type": "text",
                        "text": USER_PROMPT_TEMPLATE.format(
                            user_notes=user_notes or "(none)"
                        ),
                    },
                ],
            }
        ],
    )

    raw = "".join(block.text for block in message.content if block.type == "text").strip()
    # Strip ```json fences if the model added them despite instructions.
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()

    return json.loads(raw)


# ----- Rendering ------------------------------------------------------------

DIRECTION_STYLE = {
    "long":  ("LONG / BUY",  "#16a34a"),
    "short": ("SHORT / SELL", "#dc2626"),
    "flat":  ("NO TRADE",    "#6b7280"),
}


def _conviction_color(conviction: int) -> str:
    if conviction >= 70:
        return "#16a34a"
    if conviction >= 55:
        return "#ca8a04"
    if conviction >= 35:
        return "#ea580c"
    return "#6b7280"


def render_decision(d: dict[str, Any]) -> None:
    if not d.get("readable", True):
        st.error("The image does not appear to be a readable trading chart.")
        st.write(d.get("summary", ""))
        return

    direction = d.get("direction", "flat")
    label, color = DIRECTION_STYLE.get(direction, DIRECTION_STYLE["flat"])
    conviction = int(d.get("conviction", 0))

    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        st.markdown(
            f"<div style='padding:14px;border-radius:10px;background:{color};"
            f"color:white;text-align:center;font-weight:700;font-size:22px;'>"
            f"{label}</div>",
            unsafe_allow_html=True,
        )
    with c2:
        bar = _conviction_color(conviction)
        st.markdown(
            f"<div style='padding:14px;border-radius:10px;background:#111;"
            f"color:white;text-align:center;'>"
            f"<div style='font-size:13px;opacity:0.75;'>CONVICTION</div>"
            f"<div style='font-size:30px;font-weight:800;color:{bar};'>{conviction}</div>"
            f"<div style='font-size:11px;opacity:0.55;'>out of 92</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with c3:
        inst = d.get("instrument_guess") or "—"
        tf = d.get("timeframe_guess") or "—"
        st.markdown(
            f"<div style='padding:14px;border-radius:10px;background:#111;color:white;'>"
            f"<div style='font-size:12px;opacity:0.7;'>INSTRUMENT</div>"
            f"<div style='font-size:18px;font-weight:700;'>{inst}</div>"
            f"<div style='font-size:12px;opacity:0.7;margin-top:6px;'>TIMEFRAME</div>"
            f"<div style='font-size:18px;font-weight:700;'>{tf}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("### Trade plan")
    st.write(d.get("summary", ""))

    entry = d.get("entry", {}) or {}
    plan_rows = [
        ("Market structure", d.get("market_structure", "—")),
        ("Entry type",       entry.get("type", "—")),
        ("Entry zone",       entry.get("price_zone", "—")),
        ("Trigger",          entry.get("trigger", "—")),
        ("Stop loss",        d.get("stop_loss", "—")),
        ("Target 1",         (d.get("targets") or {}).get("t1", "—")),
        ("Target 2",         (d.get("targets") or {}).get("t2", "—")),
        ("Risk / reward",    d.get("risk_reward", "—")),
        ("Invalidation",     d.get("invalidation", "—")),
    ]
    for label_, value in plan_rows:
        st.markdown(f"**{label_}:** {value}")

    factors = d.get("factors") or []
    if factors:
        st.markdown("### Confluence factors")
        for f in factors:
            st.markdown(
                f"- **[{f.get('category','?')}] {f.get('name','')}** — "
                f"{f.get('evidence','')}"
            )

    conflicts = d.get("conflicts") or []
    if conflicts:
        st.markdown("### Conflicting signals")
        for f in conflicts:
            st.markdown(
                f"- **[{f.get('category','?')}] {f.get('name','')}** — "
                f"{f.get('evidence','')}"
            )

    st.caption(d.get("disclaimer", "Not financial advice."))

    with st.expander("Raw JSON"):
        st.code(json.dumps(d, indent=2), language="json")


# ----- UI -------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Chart Analyzer", page_icon=None, layout="wide")
    st.title("Trading Chart Analyzer")
    st.caption(
        "Upload a candlestick chart. The model reads market structure, "
        "candlestick patterns, MAs, RSI/MACD, volume, and chart patterns, "
        "then returns a direction, conviction score, and full trade plan. "
        "It will say NO TRADE when signals conflict — that is a feature."
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error(
            "ANTHROPIC_API_KEY is not set. Create a `.env` file next to "
            "`app.py` with `ANTHROPIC_API_KEY=sk-ant-...` and restart."
        )
        st.stop()

    with st.sidebar:
        st.subheader("Optional context")
        user_notes = st.text_area(
            "Notes for the analyst (timeframe, news, bias you want checked, etc.)",
            height=120,
            placeholder="e.g. 4H BTCUSD — looking for a long continuation above 62k",
        )
        st.markdown("---")
        st.markdown(
            "**Methods used:** Dow/market structure, S/R & supply-demand, "
            "50/200 EMA trend, candlestick reversals, chart patterns, "
            "Fibonacci, RSI/MACD divergence, Bollinger, volume/Wyckoff, Ichimoku."
        )
        st.markdown(
            "Conviction is capped at 92. A single indicator never qualifies as "
            "a trade — 2+ aligned factors required."
        )

    uploaded = st.file_uploader(
        "Chart screenshot (PNG / JPG / WEBP)",
        type=["png", "jpg", "jpeg", "webp"],
    )
    if not uploaded:
        st.info("Drop a chart screenshot above to get a trade call.")
        return

    image_bytes = uploaded.read()
    mime = uploaded.type or "image/png"
    if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        mime = "image/png"

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        st.error("Could not decode that image.")
        return

    left, right = st.columns([1, 1])
    with left:
        st.image(img, caption=uploaded.name, use_container_width=True)
    with right:
        if st.button("Analyze chart", type="primary", use_container_width=True):
            client = Anthropic(api_key=api_key)
            with st.spinner("Reading the chart…"):
                try:
                    decision = analyze_chart(client, image_bytes, mime, user_notes)
                except APIError as e:
                    st.error(f"Anthropic API error: {e}")
                    return
                except json.JSONDecodeError as e:
                    st.error(f"Model did not return valid JSON: {e}")
                    return
            render_decision(decision)


if __name__ == "__main__":
    main()

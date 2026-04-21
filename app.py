"""Trading Chart Analyzer — Streamlit app.

Tabs:
    Analyze  — upload 1 or 2 charts (LTF, or HTF+LTF). Get decision,
               position size, and save to journal.
    Journal  — review past calls, mark outcomes (win/loss/BE).
    Stats    — win rate overall and by conviction bucket, avg R, total P&L.

Requires ANTHROPIC_API_KEY in env or .env.
Run: streamlit run app.py
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

import db
from auth import require_auth, sign_out_button
from prompts import MTF_PROMPT_TEMPLATE, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

load_dotenv()

MODEL = "claude-opus-4-7"
MAX_TOKENS = 2048


def _get_api_key() -> str | None:
    """Prefer Streamlit Cloud secrets; fall back to env var for local dev."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY")  # type: ignore[attr-defined]
        if key:
            return str(key)
    except (FileNotFoundError, KeyError, AttributeError):
        pass
    return os.getenv("ANTHROPIC_API_KEY")


# ----- Claude call ----------------------------------------------------------

def _img_block(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        },
    }


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()
    return json.loads(raw)


def analyze(
    client: Anthropic,
    charts: list[tuple[bytes, str]],   # [(bytes, media_type), ...] — 1 or 2
    user_notes: str,
) -> dict[str, Any]:
    if len(charts) == 2:
        text = MTF_PROMPT_TEMPLATE.format(user_notes=user_notes or "(none)")
    else:
        text = USER_PROMPT_TEMPLATE.format(user_notes=user_notes or "(none)")

    content: list[dict[str, Any]] = [_img_block(b, m) for b, m in charts]
    content.append({"type": "text", "text": text})

    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text")
    return _parse_json(raw)


# ----- Rendering helpers ----------------------------------------------------

DIRECTION_STYLE = {
    "long":  ("LONG / BUY",   "#16a34a"),
    "short": ("SHORT / SELL", "#dc2626"),
    "flat":  ("NO TRADE",     "#6b7280"),
}


def _conviction_color(c: int) -> str:
    if c >= 70:
        return "#16a34a"
    if c >= 55:
        return "#ca8a04"
    if c >= 35:
        return "#ea580c"
    return "#6b7280"


def compute_position_size(
    decision: dict[str, Any],
    account_size: float,
    risk_pct: float,
) -> tuple[float | None, float | None, str]:
    """Return (position_size_units, risk_dollars, message)."""
    if decision.get("direction") == "flat":
        return None, None, "No trade — skipping sizing."
    entry = decision.get("entry_price_numeric")
    stop = decision.get("stop_loss_numeric")
    if entry is None or stop is None:
        return None, None, (
            "Could not extract numeric entry/stop from chart. "
            "Enter them manually below to size the position."
        )
    risk_dollars = account_size * (risk_pct / 100.0)
    per_unit_risk = abs(entry - stop)
    if per_unit_risk <= 0:
        return None, risk_dollars, "Entry and stop are equal — check the numbers."
    size = risk_dollars / per_unit_risk
    return size, risk_dollars, (
        f"Risk ${risk_dollars:,.2f} ({risk_pct:.2f}% of ${account_size:,.0f}). "
        f"Stop distance {per_unit_risk:.4f} per unit → size **{size:,.4f} units**."
    )


def render_decision(d: dict[str, Any], sizing_msg: str | None = None) -> None:
    if not d.get("readable", True):
        st.error("That image doesn't look like a readable trading chart.")
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
            f"<div style='font-size:11px;opacity:0.55;'>out of 92</div></div>",
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
            f"<div style='font-size:18px;font-weight:700;'>{tf}</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("### Trade plan")
    st.write(d.get("summary", ""))

    entry = d.get("entry") or {}
    targets = d.get("targets") or {}
    for k, v in [
        ("Market structure", d.get("market_structure", "—")),
        ("Entry type",       entry.get("type", "—")),
        ("Entry zone",       entry.get("price_zone", "—")),
        ("Trigger",          entry.get("trigger", "—")),
        ("Stop loss",        d.get("stop_loss", "—")),
        ("Target 1",         targets.get("t1", "—")),
        ("Target 2",         targets.get("t2", "—")),
        ("Risk / reward",    d.get("risk_reward", "—")),
        ("Invalidation",     d.get("invalidation", "—")),
    ]:
        st.markdown(f"**{k}:** {v}")

    if sizing_msg:
        st.info(sizing_msg)

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


# ----- Tab 1: Analyze -------------------------------------------------------

def _read_uploaded(uploaded) -> tuple[bytes, str, Image.Image] | None:
    if uploaded is None:
        return None
    b = uploaded.read()
    mime = uploaded.type or "image/png"
    if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        mime = "image/png"
    try:
        img = Image.open(io.BytesIO(b))
    except Exception:
        st.error(f"Could not decode {uploaded.name}.")
        return None
    return b, mime, img


def analyze_tab(api_key: str) -> None:
    st.subheader("Analyze chart")

    mode = st.radio(
        "Mode",
        ["Single chart", "Multi-timeframe (HTF + LTF)"],
        horizontal=True,
    )

    ltf_img_data: tuple[bytes, str, Image.Image] | None = None
    htf_img_data: tuple[bytes, str, Image.Image] | None = None

    if mode == "Single chart":
        up = st.file_uploader(
            "Chart screenshot (PNG / JPG / WEBP)",
            type=["png", "jpg", "jpeg", "webp"],
            key="single_up",
        )
        ltf_img_data = _read_uploaded(up)
        if ltf_img_data:
            st.image(ltf_img_data[2], caption="Chart", use_container_width=True)
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**HTF (bias)** — higher timeframe, e.g. 4H or 1D")
            up_h = st.file_uploader(
                "HTF chart", type=["png", "jpg", "jpeg", "webp"], key="htf_up"
            )
            htf_img_data = _read_uploaded(up_h)
            if htf_img_data:
                st.image(htf_img_data[2], use_container_width=True)
        with col_b:
            st.markdown("**LTF (entry)** — lower timeframe, e.g. 15m or 1H")
            up_l = st.file_uploader(
                "LTF chart", type=["png", "jpg", "jpeg", "webp"], key="ltf_up"
            )
            ltf_img_data = _read_uploaded(up_l)
            if ltf_img_data:
                st.image(ltf_img_data[2], use_container_width=True)

    user_notes = st.text_area(
        "Notes for the analyst (optional)",
        height=80,
        placeholder="e.g. looking for a long continuation above 62k",
    )

    # Position sizing inputs
    with st.expander("Position sizing", expanded=True):
        c1, c2 = st.columns(2)
        account_size = c1.number_input(
            "Account size ($)", min_value=0.0, value=10_000.0, step=100.0
        )
        risk_pct = c2.number_input(
            "Risk per trade (%)", min_value=0.0, max_value=10.0,
            value=1.0, step=0.25,
        )

    ready = ltf_img_data is not None and (mode == "Single chart" or htf_img_data is not None)
    if not st.button("Analyze chart", type="primary", disabled=not ready):
        if not ready:
            st.info("Upload the required chart(s) to enable analysis.")
        return

    charts: list[tuple[bytes, str]] = []
    if mode == "Multi-timeframe (HTF + LTF)":
        charts.append((htf_img_data[0], htf_img_data[1]))  # type: ignore[index]
    charts.append((ltf_img_data[0], ltf_img_data[1]))      # type: ignore[index]

    client = Anthropic(api_key=api_key)
    with st.spinner("Reading the chart…"):
        try:
            decision = analyze(client, charts, user_notes)
        except APIError as e:
            st.error(f"Anthropic API error: {e}")
            return
        except json.JSONDecodeError as e:
            st.error(f"Model did not return valid JSON: {e}")
            return

    size, risk_dollars, sizing_msg = compute_position_size(
        decision, account_size, risk_pct
    )
    render_decision(decision, sizing_msg)

    # Save-to-journal button
    st.markdown("---")
    save_col, manual_col = st.columns([1, 2])
    with save_col:
        if st.button("Save to journal"):
            tid = db.save_decision(
                decision, user_notes, account_size, risk_pct, risk_dollars, size
            )
            st.success(f"Saved as trade #{tid}. See Journal tab.")
    with manual_col:
        st.caption(
            "If numeric entry/stop are null the sizer can't run — enter them "
            "in the Journal after saving, or mark the trade outcome manually."
        )


# ----- Tab 2: Journal -------------------------------------------------------

STATUS_CHOICES = ["all", "pending", "taken", "skipped", "win", "loss", "breakeven"]


def journal_tab() -> None:
    st.subheader("Trade journal")

    status_filter = st.selectbox("Filter by status", STATUS_CHOICES, index=0)
    trades = db.list_trades(status_filter)
    if not trades:
        st.info("No trades recorded yet. Analyze a chart and hit **Save to journal**.")
        return

    for t in trades:
        header = (
            f"#{t['id']} · {t['created_at'][:16]} · "
            f"{t['instrument'] or '—'} {t['timeframe'] or ''} · "
            f"{(t['direction'] or '').upper()} · "
            f"conv {t['conviction']} · status {t['status']}"
            + (f" · {t['r_multiple']:+.2f}R" if t["r_multiple"] is not None else "")
        )
        with st.expander(header):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Structure:** {t['market_structure'] or '—'}")
                st.markdown(f"**Entry zone:** {t['entry_zone'] or '—'}")
                st.markdown(f"**Entry trigger:** {t['entry_trigger'] or '—'}")
                st.markdown(f"**Stop:** {t['stop_loss'] or '—'}")
                st.markdown(f"**T1 / T2:** {t['target1'] or '—'} / {t['target2'] or '—'}")
                st.markdown(f"**R:R:** {t['risk_reward'] or '—'}")
                st.markdown(f"**Invalidation:** {t['invalidation'] or '—'}")
            with c2:
                st.markdown(f"**Summary:** {t['summary'] or '—'}")
                if t["position_size"] is not None:
                    st.markdown(
                        f"**Sizing:** {t['position_size']:.4f} units · "
                        f"risk ${t['risk_dollars']:,.2f} "
                        f"({t['risk_pct']:.2f}% of ${t['account_size']:,.0f})"
                    )
                factors = json.loads(t["factors_json"] or "[]")
                if factors:
                    st.markdown("**Factors:**")
                    for f in factors:
                        st.markdown(
                            f"- [{f.get('category','?')}] {f.get('name','')}: "
                            f"{f.get('evidence','')}"
                        )
                if t["user_notes"]:
                    st.markdown(f"**Your notes:** {t['user_notes']}")

            st.markdown("---")
            st.markdown("#### Update outcome")
            with st.form(f"outcome_{t['id']}"):
                new_status = st.selectbox(
                    "Status",
                    ["pending", "taken", "skipped", "win", "loss", "breakeven"],
                    index=["pending", "taken", "skipped", "win", "loss", "breakeven"].index(
                        t["status"] or "pending"
                    ),
                    key=f"st_{t['id']}",
                )
                ae_col, ax_col = st.columns(2)
                actual_entry = ae_col.number_input(
                    "Actual entry price",
                    value=float(t["actual_entry"] or t["entry_price"] or 0.0),
                    format="%.6f",
                    key=f"ae_{t['id']}",
                )
                actual_exit = ax_col.number_input(
                    "Actual exit price",
                    value=float(t["actual_exit"] or 0.0),
                    format="%.6f",
                    key=f"ax_{t['id']}",
                )
                outcome_notes = st.text_input(
                    "Outcome notes (optional)",
                    value=t["outcome_notes"] or "",
                    key=f"on_{t['id']}",
                )
                save_btn = st.form_submit_button("Save outcome")
                del_btn = st.form_submit_button("Delete trade")

                if save_btn:
                    db.update_outcome(
                        t["id"],
                        new_status,
                        actual_entry if actual_entry else None,
                        actual_exit if actual_exit else None,
                        outcome_notes or None,
                    )
                    st.success("Updated.")
                    st.rerun()
                if del_btn:
                    db.delete_trade(t["id"])
                    st.warning("Deleted.")
                    st.rerun()


# ----- Tab 3: Stats ---------------------------------------------------------

def stats_tab() -> None:
    st.subheader("Performance stats")
    s = db.stats_summary()

    if s["total_closed"] == 0:
        st.info(
            "No closed trades yet. Mark some trades in the Journal tab as "
            "win / loss / breakeven to see stats."
        )
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Closed trades", s["total_closed"])
    c2.metric("Win rate", f"{s['win_rate_pct']:.1f}%")
    c3.metric("Avg R", f"{s['avg_r']:+.2f}R")
    c4.metric("Total P&L", f"${s['total_pnl']:,.2f}")

    st.caption(
        f"{s['wins']} wins / {s['losses']} losses / {s['breakeven']} BE "
        "(win rate excludes BE)."
    )

    st.markdown("### Win rate by conviction bucket")
    st.caption("This is the real test: higher-conviction buckets should win more often.")
    for b in s["buckets"]:
        st.markdown(
            f"- **{b['bucket']}** — n={b['n']}, "
            f"{b['wins']}W / {b['losses']}L → "
            f"**{b['win_rate']:.1f}%** win rate"
        )


# ----- Main -----------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Chart Analyzer", layout="wide")

    # Gate everything behind the password if APP_PASSWORD is set.
    require_auth()

    db.init_db()

    st.title("Trading Chart Analyzer")
    st.caption(
        "Upload chart screenshots. Get a disciplined long/short/no-trade "
        "call with confluence reasoning, sizing, and a journal that "
        "tracks how well the calls actually perform."
    )

    api_key = _get_api_key()
    if not api_key:
        st.error(
            "ANTHROPIC_API_KEY is not set. Locally: copy `.env.example` to "
            "`.env` and paste your key. On Streamlit Cloud: set it in "
            "App settings → Secrets."
        )
        st.stop()

    with st.sidebar:
        st.caption(f"Storage: {db.backend_label()}")
        sign_out_button()

    t1, t2, t3 = st.tabs(["Analyze", "Journal", "Stats"])
    with t1:
        analyze_tab(api_key)
    with t2:
        journal_tab()
    with t3:
        stats_tab()


if __name__ == "__main__":
    main()

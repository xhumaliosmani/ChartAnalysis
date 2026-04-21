"""Journal storage — SQLAlchemy, works on SQLite (local) or Postgres (prod).

Backend selection:
    - DATABASE_URL env/secret set  -> use that (Postgres on Neon/Supabase/etc).
    - otherwise                    -> sqlite:///journal.db next to this file.

Legacy `postgres://` URLs (as emitted by Heroku/Neon) are auto-rewritten
to `postgresql+psycopg2://` which SQLAlchemy 2.x requires.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column, Float, Integer, MetaData, String, Table, Text,
    create_engine, delete, select, text, update,
)
from sqlalchemy.engine import Engine

try:  # pragma: no cover - streamlit only present in app context
    import streamlit as st
except Exception:  # noqa: BLE001
    st = None  # type: ignore[assignment]


_LOCAL_SQLITE = f"sqlite:///{Path(__file__).parent / 'journal.db'}"


def _get_database_url() -> str:
    url: str | None = None
    if st is not None:
        try:
            url = st.secrets.get("DATABASE_URL")  # type: ignore[attr-defined]
        except (FileNotFoundError, KeyError, AttributeError):
            url = None
    if not url:
        url = os.getenv("DATABASE_URL")
    if not url:
        return _LOCAL_SQLITE
    # Neon/Heroku-style scheme rewrite
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


_engine: Engine | None = None
metadata = MetaData()

trades = Table(
    "trades", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("created_at",      String(40), nullable=False),
    Column("instrument",      String(64)),
    Column("timeframe",       String(16)),
    Column("direction",       String(8), nullable=False),
    Column("conviction",      Integer, nullable=False),
    Column("market_structure", Text),
    Column("entry_zone",      Text),
    Column("entry_price",     Float),
    Column("entry_trigger",   Text),
    Column("stop_loss",       Text),
    Column("stop_price",      Float),
    Column("target1",         Text),
    Column("target1_price",   Float),
    Column("target2",         Text),
    Column("target2_price",   Float),
    Column("risk_reward",     Text),
    Column("invalidation",    Text),
    Column("summary",         Text),
    Column("factors_json",    Text),
    Column("conflicts_json",  Text),
    Column("user_notes",      Text),

    Column("account_size",    Float),
    Column("risk_pct",        Float),
    Column("risk_dollars",    Float),
    Column("position_size",   Float),

    Column("status",          String(16), default="pending"),
    Column("actual_entry",    Float),
    Column("actual_exit",     Float),
    Column("r_multiple",      Float),
    Column("pnl_dollars",     Float),
    Column("closed_at",       String(40)),
    Column("outcome_notes",   Text),
)


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = _get_database_url()
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    return _engine


def init_db() -> None:
    metadata.create_all(_get_engine())


# ----- Write ---------------------------------------------------------------

def save_decision(
    decision: dict[str, Any],
    user_notes: str,
    account_size: float | None,
    risk_pct: float | None,
    risk_dollars: float | None,
    position_size: float | None,
) -> int:
    entry = decision.get("entry") or {}
    targets = decision.get("targets") or {}

    row = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "instrument": decision.get("instrument_guess"),
        "timeframe": decision.get("timeframe_guess"),
        "direction": decision.get("direction", "flat"),
        "conviction": int(decision.get("conviction", 0)),
        "market_structure": decision.get("market_structure"),
        "entry_zone": entry.get("price_zone"),
        "entry_price": decision.get("entry_price_numeric"),
        "entry_trigger": entry.get("trigger"),
        "stop_loss": decision.get("stop_loss"),
        "stop_price": decision.get("stop_loss_numeric"),
        "target1": targets.get("t1"),
        "target1_price": decision.get("target1_numeric"),
        "target2": targets.get("t2"),
        "target2_price": decision.get("target2_numeric"),
        "risk_reward": decision.get("risk_reward"),
        "invalidation": decision.get("invalidation"),
        "summary": decision.get("summary"),
        "factors_json": json.dumps(decision.get("factors") or []),
        "conflicts_json": json.dumps(decision.get("conflicts") or []),
        "user_notes": user_notes or None,
        "account_size": account_size,
        "risk_pct": risk_pct,
        "risk_dollars": risk_dollars,
        "position_size": position_size,
        "status": "pending",
    }
    with _get_engine().begin() as con:
        result = con.execute(trades.insert().values(**row))
        return int(result.inserted_primary_key[0])


def update_outcome(
    trade_id: int,
    status: str,
    actual_entry: float | None,
    actual_exit: float | None,
    outcome_notes: str | None,
) -> None:
    t = get_trade(trade_id)
    if t is None:
        return

    r_multiple: float | None = None
    pnl: float | None = None

    if (
        status in ("win", "loss", "breakeven")
        and actual_entry is not None
        and actual_exit is not None
        and t.get("stop_price") is not None
    ):
        risk_per_unit = abs(actual_entry - t["stop_price"])
        if risk_per_unit > 0:
            direction = t["direction"]
            pnl_per_unit = (
                (actual_exit - actual_entry)
                if direction == "long"
                else (actual_entry - actual_exit)
            )
            r_multiple = pnl_per_unit / risk_per_unit
            if t.get("position_size") is not None:
                pnl = pnl_per_unit * t["position_size"]

    with _get_engine().begin() as con:
        con.execute(
            update(trades).where(trades.c.id == trade_id).values(
                status=status,
                actual_entry=actual_entry,
                actual_exit=actual_exit,
                r_multiple=r_multiple,
                pnl_dollars=pnl,
                outcome_notes=outcome_notes,
                closed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        )


def delete_trade(trade_id: int) -> None:
    with _get_engine().begin() as con:
        con.execute(delete(trades).where(trades.c.id == trade_id))


# ----- Read ----------------------------------------------------------------

def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def list_trades(status_filter: str | None = None) -> list[dict[str, Any]]:
    q = select(trades)
    if status_filter and status_filter != "all":
        q = q.where(trades.c.status == status_filter)
    q = q.order_by(trades.c.created_at.desc())
    with _get_engine().connect() as con:
        return [_row_to_dict(r) for r in con.execute(q)]


def get_trade(trade_id: int) -> dict[str, Any] | None:
    with _get_engine().connect() as con:
        row = con.execute(select(trades).where(trades.c.id == trade_id)).first()
        return _row_to_dict(row) if row is not None else None


# ----- Stats ---------------------------------------------------------------

def _pct(n: int, d: int) -> float:
    return (100.0 * n / d) if d else 0.0


def stats_summary() -> dict[str, Any]:
    with _get_engine().connect() as con:
        rows = [_row_to_dict(r) for r in con.execute(
            select(trades).where(trades.c.status.in_(("win", "loss", "breakeven")))
        )]

    wins = sum(1 for r in rows if r["status"] == "win")
    losses = sum(1 for r in rows if r["status"] == "loss")
    be = sum(1 for r in rows if r["status"] == "breakeven")
    decided = wins + losses
    win_rate = _pct(wins, decided)

    rs = [r["r_multiple"] for r in rows if r["r_multiple"] is not None]
    avg_r = sum(rs) / len(rs) if rs else 0.0

    pnls = [r["pnl_dollars"] for r in rows if r["pnl_dollars"] is not None]
    total_pnl = sum(pnls) if pnls else 0.0

    buckets: dict[str, list[dict[str, Any]]] = {
        "0-34 (flat/low)":  [],
        "35-54 (weak)":     [],
        "55-69 (medium)":   [],
        "70-92 (strong)":   [],
    }
    for r in rows:
        c = r.get("conviction") or 0
        if c < 35:
            key = "0-34 (flat/low)"
        elif c < 55:
            key = "35-54 (weak)"
        elif c < 70:
            key = "55-69 (medium)"
        else:
            key = "70-92 (strong)"
        buckets[key].append(r)

    bucket_stats = []
    for name, brows in buckets.items():
        bw = sum(1 for r in brows if r["status"] == "win")
        bl = sum(1 for r in brows if r["status"] == "loss")
        bucket_stats.append({
            "bucket": name,
            "n": len(brows),
            "wins": bw,
            "losses": bl,
            "win_rate": _pct(bw, bw + bl),
        })

    return {
        "total_closed": len(rows),
        "wins": wins,
        "losses": losses,
        "breakeven": be,
        "win_rate_pct": win_rate,
        "avg_r": avg_r,
        "total_pnl": total_pnl,
        "buckets": bucket_stats,
    }


def backend_label() -> str:
    """Human-readable name of the current backend (for diagnostics)."""
    url = _get_database_url()
    if url.startswith("sqlite"):
        return "SQLite (local)"
    if "postgres" in url:
        return "PostgreSQL"
    return url.split("://", 1)[0]

"""SQLite-backed trade journal.

One table: `trades`. Each row is one analysis. Outcome fields start empty
and are filled in when the user marks the trade won/lost/BE.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).parent / "journal.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    instrument      TEXT,
    timeframe       TEXT,
    direction       TEXT    NOT NULL,
    conviction      INTEGER NOT NULL,
    market_structure TEXT,
    entry_zone      TEXT,
    entry_price     REAL,
    entry_trigger   TEXT,
    stop_loss       TEXT,
    stop_price      REAL,
    target1         TEXT,
    target1_price   REAL,
    target2         TEXT,
    target2_price   REAL,
    risk_reward     TEXT,
    invalidation    TEXT,
    summary         TEXT,
    factors_json    TEXT,
    conflicts_json  TEXT,
    user_notes      TEXT,

    account_size    REAL,
    risk_pct        REAL,
    risk_dollars    REAL,
    position_size   REAL,

    status          TEXT    DEFAULT 'pending',
    actual_entry    REAL,
    actual_exit     REAL,
    r_multiple      REAL,
    pnl_dollars     REAL,
    closed_at       TEXT,
    outcome_notes   TEXT
);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript(SCHEMA)


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
    }

    cols = ",".join(row.keys())
    placeholders = ",".join("?" for _ in row)
    with _conn() as con:
        cur = con.execute(
            f"INSERT INTO trades ({cols}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        return int(cur.lastrowid)


def list_trades(status_filter: str | None = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM trades"
    args: tuple = ()
    if status_filter and status_filter != "all":
        q += " WHERE status = ?"
        args = (status_filter,)
    q += " ORDER BY created_at DESC"
    with _conn() as con:
        return list(con.execute(q, args))


def get_trade(trade_id: int) -> sqlite3.Row | None:
    with _conn() as con:
        return con.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()


def update_outcome(
    trade_id: int,
    status: str,
    actual_entry: float | None,
    actual_exit: float | None,
    outcome_notes: str | None,
) -> None:
    """Compute R multiple and $ P&L from the recorded stop distance."""
    trade = get_trade(trade_id)
    if trade is None:
        return

    r_multiple: float | None = None
    pnl: float | None = None

    if (
        status in ("win", "loss", "breakeven")
        and actual_entry is not None
        and actual_exit is not None
        and trade["stop_price"] is not None
    ):
        risk_per_unit = abs(actual_entry - trade["stop_price"])
        if risk_per_unit > 0:
            direction = trade["direction"]
            pnl_per_unit = (
                (actual_exit - actual_entry)
                if direction == "long"
                else (actual_entry - actual_exit)
            )
            r_multiple = pnl_per_unit / risk_per_unit
            if trade["position_size"] is not None:
                pnl = pnl_per_unit * trade["position_size"]

    with _conn() as con:
        con.execute(
            """
            UPDATE trades
               SET status = ?,
                   actual_entry = ?,
                   actual_exit = ?,
                   r_multiple = ?,
                   pnl_dollars = ?,
                   outcome_notes = ?,
                   closed_at = ?
             WHERE id = ?
            """,
            (
                status,
                actual_entry,
                actual_exit,
                r_multiple,
                pnl,
                outcome_notes,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                trade_id,
            ),
        )


def delete_trade(trade_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM trades WHERE id = ?", (trade_id,))


# ----- Stats ----------------------------------------------------------------

def _pct(n: int, d: int) -> float:
    return (100.0 * n / d) if d else 0.0


def stats_summary() -> dict[str, Any]:
    with _conn() as con:
        rows = list(con.execute(
            "SELECT status, conviction, r_multiple, pnl_dollars, direction "
            "FROM trades WHERE status IN ('win','loss','breakeven')"
        ))

    total = len(rows)
    wins = sum(1 for r in rows if r["status"] == "win")
    losses = sum(1 for r in rows if r["status"] == "loss")
    be = sum(1 for r in rows if r["status"] == "breakeven")

    decided = wins + losses  # BE excluded from win rate denominator
    win_rate = _pct(wins, decided)

    rs = [r["r_multiple"] for r in rows if r["r_multiple"] is not None]
    avg_r = sum(rs) / len(rs) if rs else 0.0

    pnls = [r["pnl_dollars"] for r in rows if r["pnl_dollars"] is not None]
    total_pnl = sum(pnls) if pnls else 0.0

    # Conviction buckets
    buckets = {"0-34 (flat/low)": [], "35-54 (weak)": [], "55-69 (medium)": [], "70-92 (strong)": []}
    for r in rows:
        c = r["conviction"] or 0
        if c < 35:
            b = "0-34 (flat/low)"
        elif c < 55:
            b = "35-54 (weak)"
        elif c < 70:
            b = "55-69 (medium)"
        else:
            b = "70-92 (strong)"
        buckets[b].append(r)

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
        "total_closed": total,
        "wins": wins,
        "losses": losses,
        "breakeven": be,
        "win_rate_pct": win_rate,
        "avg_r": avg_r,
        "total_pnl": total_pnl,
        "buckets": bucket_stats,
    }


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in rows]

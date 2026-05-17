"""SQLite repository.

Single-file DB. Thread-safety via check_same_thread=False + a fresh connection
per call. Path can be overridden with TR_DB_PATH (used by demo / screenshot
runs to avoid touching the user's real database).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "trade_review.db"
DB_PATH = Path(os.environ.get("TR_DB_PATH") or str(_DEFAULT_DB))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ─── Trades ─────────────────────────────────────────────────────────

def insert_trade(trade: dict[str, Any]) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO trades (symbol, market, name, action, price, quantity,
                                   trade_time, reason, mood)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (trade["symbol"], trade["market"], trade.get("name"),
             trade["action"], trade["price"], trade["quantity"],
             trade["trade_time"], trade.get("reason"), trade.get("mood")),
        )
        conn.commit()
        return cur.lastrowid


def get_trade(trade_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None


def list_recent_trades(symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM trades WHERE symbol = ? ORDER BY trade_time DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY trade_time DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def last_trade_before(symbol: str, trade_time: str) -> dict[str, Any] | None:
    """报复性交易检测用：同一 symbol 最近一笔更早的交易。"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE symbol = ? AND trade_time < ? "
            "ORDER BY trade_time DESC LIMIT 1",
            (symbol, trade_time),
        ).fetchone()
        return dict(row) if row else None


def count_trades_on_date(date_str: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE DATE(trade_time) = ?", (date_str,)
        ).fetchone()
        return row["n"] if row else 0


# ─── Positions ─────────────────────────────────────────────────────

def upsert_position(pos: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO positions (symbol, market, name, quantity, cost_price, updated_at)
               VALUES (?,?,?,?,?, CURRENT_TIMESTAMP)
               ON CONFLICT(symbol, market) DO UPDATE SET
                   name = excluded.name,
                   quantity = excluded.quantity,
                   cost_price = excluded.cost_price,
                   updated_at = CURRENT_TIMESTAMP""",
            (pos["symbol"], pos["market"], pos.get("name"),
             pos["quantity"], pos["cost_price"]),
        )
        conn.commit()


def list_positions() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM positions ORDER BY market, symbol").fetchall()
        return [dict(r) for r in rows]


def delete_position(symbol: str, market: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM positions WHERE symbol = ? AND market = ?", (symbol, market))
        conn.commit()


# ─── Reviews ───────────────────────────────────────────────────────

def insert_review(review: dict[str, Any]) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO reviews (review_type, trade_id, review_date, scores_json,
                                    tags_json, report_md, scenarios_json, lesson,
                                    ai_engine, ai_latency_ms)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (review["review_type"], review.get("trade_id"), review["review_date"],
             json.dumps(review.get("scores"), ensure_ascii=False) if review.get("scores") else None,
             json.dumps(review.get("tags"), ensure_ascii=False) if review.get("tags") else None,
             review["report_md"],
             json.dumps(review.get("scenarios"), ensure_ascii=False) if review.get("scenarios") else None,
             review.get("lesson"),
             review.get("ai_engine"),
             review.get("ai_latency_ms")),
        )
        conn.commit()
        return cur.lastrowid


def get_review(review_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
        return dict(row) if row else None


# ─── Mindset tags ──────────────────────────────────────────────────

def insert_tags(trade_id: int, tags: list[dict[str, Any]]) -> None:
    if not tags:
        return
    with _connect() as conn:
        conn.executemany(
            "INSERT INTO mindset_tags (trade_id, tag, severity, evidence_json) VALUES (?,?,?,?)",
            [(trade_id, t["tag"], t.get("severity"),
              json.dumps(t.get("evidence"), ensure_ascii=False))
             for t in tags],
        )
        conn.commit()


def list_tags_in_range(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """周度画像聚合用。"""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT mt.*, t.symbol, t.trade_time FROM mindset_tags mt
               JOIN trades t ON t.id = mt.trade_id
               WHERE DATE(t.trade_time) BETWEEN ? AND ?""",
            (start_date, end_date),
        ).fetchall()
        return [dict(r) for r in rows]


def list_trades_with_context(symbol: str | None = None,
                             tag: str | None = None,
                             limit: int = 100) -> list[dict[str, Any]]:
    """交易日志用：一次查出 trade + 关联标签 + 闪评 scores/lesson。"""
    with _connect() as conn:
        base = "SELECT * FROM trades"
        where = []
        params: list[Any] = []
        if symbol:
            where.append("symbol = ?")
            params.append(symbol)
        if where:
            base += " WHERE " + " AND ".join(where)
        base += " ORDER BY trade_time DESC LIMIT ?"
        params.append(limit)
        trades = [dict(r) for r in conn.execute(base, params).fetchall()]
        if not trades:
            return []

        ids = [t["id"] for t in trades]
        placeholder = ",".join("?" * len(ids))

        tag_rows = conn.execute(
            f"SELECT * FROM mindset_tags WHERE trade_id IN ({placeholder})",
            ids,
        ).fetchall()
        tags_by_trade: dict[int, list[dict]] = {}
        for r in tag_rows:
            d = dict(r)
            tags_by_trade.setdefault(d["trade_id"], []).append(d)

        review_rows = conn.execute(
            f"""SELECT id, trade_id, scores_json, tags_json, lesson
                FROM reviews
                WHERE review_type='flash' AND trade_id IN ({placeholder})""",
            ids,
        ).fetchall()
        review_by_trade = {r["trade_id"]: dict(r) for r in review_rows}

        for t in trades:
            t["tags"] = tags_by_trade.get(t["id"], [])
            t["review"] = review_by_trade.get(t["id"])

        # tag 过滤（后端层做，保证 limit 足够）
        if tag:
            trades = [t for t in trades if any(x["tag"] == tag for x in t["tags"])]

        return trades

"""Seed a fresh demo SQLite db so screenshots show realistic content
without exposing the user's real positions.

Used by scripts/screenshot.sh — run it pointed at a temp DB:

    TR_DB_PATH=/tmp/tr_demo.db .venv/bin/python scripts/seed_demo.py
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta
from pathlib import Path

# Make sure repo points at the demo DB before we import it.
TR_DB = os.environ.get("TR_DB_PATH")
if not TR_DB:
    raise SystemExit("set TR_DB_PATH first (point it at a throwaway file)")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import repo  # noqa: E402

# Wipe any existing demo db so we always start clean.
demo_path = Path(TR_DB)
if demo_path.exists():
    demo_path.unlink()
demo_path.parent.mkdir(parents=True, exist_ok=True)

repo.init_db()
print(f"[seed] schema applied → {demo_path}")

# ── Demo positions: a balanced multi-market portfolio ────────────────
DEMO_POSITIONS = [
    # symbol, market, name, qty, cost_price
    ("600519", "A",  "贵州茅台",   10,  1420.00),
    ("002240", "A",  "盛新锂能",  100,    49.88),
    ("601398", "A",  "工商银行",  500,     7.20),
    ("000858", "A",  "五粮液",     50,   168.50),
    ("0700",   "HK", "Tencent",    50,   320.00),
    ("AAPL",   "US", "Apple",      10,   175.00),
    ("NVDA",   "US", "NVIDIA",      5,   780.00),
    ("MSFT",   "US", "Microsoft",  10,   410.00),
]

for symbol, market, name, qty, cost in DEMO_POSITIONS:
    repo.upsert_position({
        "symbol": symbol, "market": market, "name": name,
        "quantity": qty, "cost_price": cost,
    })
print(f"[seed] {len(DEMO_POSITIONS)} positions inserted")

# ── Demo trades over the past 14 days, with mindset tags ─────────────
DEMO_TRADES = [
    # (days_ago, hour, symbol, market, action, price, qty, reason, mood)
    (12, "09:35", "002240", "A",  "buy",   45.20, 100, "锂电板块异动放量", "兴奋"),
    (11, "10:12", "600519", "A",  "buy",   1402,    5, "回踩 MA20 试仓",  "平静"),
    (10, "13:55", "002240", "A",  "buy",   48.30, 100, "顶破前高,加仓",   "FOMO"),
    ( 9, "14:21", "AAPL",   "US", "buy",   172,    10, "财报前布局",       "平静"),
    ( 7, "10:08", "002240", "A",  "sell",  46.10, 100, "跌穿 5 日线止损", "焦虑"),
    ( 7, "11:30", "002240", "A",  "buy",   46.90, 200, "想拉回成本反手",   "急躁"),
    ( 5, "09:42", "0700",   "HK", "buy",   315,    50, "AI 主题持续",     "平静"),
    ( 4, "14:50", "NVDA",   "US", "buy",   765,     5, "财报后回调",       "平静"),
    ( 3, "10:33", "601398", "A",  "buy",   7.05,  500, "高股息防御",       "平静"),
    ( 2, "13:18", "MSFT",   "US", "buy",   408,    10, "AI 战略受益",     "平静"),
    ( 1, "09:48", "000858", "A",  "buy",   165,    50, "白酒板块底部反弹", "犹豫"),
]

now = datetime.now()
for days_ago, hhmm, sym, mkt, act, price, qty, reason, mood in DEMO_TRADES:
    trade_time = (now - timedelta(days=days_ago)).strftime(f"%Y-%m-%d {hhmm}:00")
    name_lookup = {p[0]: p[2] for p in DEMO_POSITIONS}
    trade_id = repo.insert_trade({
        "symbol": sym, "market": mkt, "name": name_lookup.get(sym, ""),
        "action": act, "price": price, "quantity": qty,
        "trade_time": trade_time, "reason": reason, "mood": mood,
    })

    # Sprinkle some mindset tags so the weekly radar isn't all 85
    tags = []
    if reason in ("锂电板块异动放量",) or "FOMO" in mood:
        tags.append({"tag": "追涨", "severity": "medium",
                     "evidence": {"pre30_change_pct": 2.3, "daily_change_pct": 4.1}})
    if "止损" in reason and mood == "焦虑":
        tags.append({"tag": "杀跌", "severity": "light",
                     "evidence": {"daily_change_pct": -1.8}})
    if "反手" in reason or mood == "急躁":
        tags.append({"tag": "报复性交易", "severity": "medium",
                     "evidence": {"gap_hours": 1.2}})
    if days_ago == 10 and sym == "002240":
        tags.append({"tag": "频繁交易", "severity": "light",
                     "evidence": {"daily_count": 4}})
    if tags:
        repo.insert_tags(trade_id, tags)

print(f"[seed] {len(DEMO_TRADES)} trades inserted with behavioral tags")
print(f"[seed] done — point a backend at TR_DB_PATH={demo_path}")

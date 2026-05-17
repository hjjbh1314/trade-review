"""Optional iFinD MCP enrichment for A-share quotes.

iFinD is a paid commercial data feed (10jqka). It's used purely as an *optional*
enrichment layer that gives the AI coach an extra natural-language paragraph on
the stock's intraday context.

Without an iFinD token the rest of the app works fine: A-share data flows
through akshare and yfinance, and the snapshot's `ifind_text` field is
synthesized locally from those numbers (see aggregator._compose_summary).

To opt in, set IFIND_AUTH_TOKEN in your .env, or place an
`ifind_mcp_config.json` next to this repo with `{"auth_token": "..."}`.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Allow importing the legacy ifind_client.py from the repo root if present.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_client: Any = None
_init_failed: bool = False


def _ifind_configured() -> bool:
    """Cheap check before we even try to construct a client. Avoids spamming
    logs on every request when the user has no iFinD setup."""
    if os.environ.get("IFIND_AUTH_TOKEN", "").strip():
        return True
    cfg = os.environ.get("IFIND_MCP_CONFIG") or str(_ROOT / "ifind_mcp_config.json")
    return Path(cfg).exists()


def _get_client() -> Any | None:
    """Lazy-load. Once init fails, stay disabled until the process restarts."""
    global _client, _init_failed
    if _client is not None:
        return _client
    if _init_failed:
        return None
    if not _ifind_configured():
        _init_failed = True
        return None
    try:
        from ifind_client import IFindMCPClient  # type: ignore
        _client = IFindMCPClient()
        log.info("iFinD client ready")
        return _client
    except Exception as e:
        log.info("iFinD disabled (%s)", e)
        _init_failed = True
        return None


def enrich_with_ifind_text(symbol: str, trade_date: str | None = None) -> str | None:
    """Best-effort iFinD natural-language summary. Returns None if iFinD isn't
    configured or any error occurs — the caller falls back to a local summary.
    """
    client = _get_client()
    if not client:
        return None
    try:
        result = client.query_stock_trend(code=symbol, trade_date=trade_date)
        if not result.get("ok"):
            log.info("iFinD query non-ok: %s", result.get("error"))
            return None
        text = str(result.get("text", "")).strip()
        return text[:1200] if text else None
    except Exception as e:
        log.warning("iFinD query failed for %s: %s", symbol, e)
        return None

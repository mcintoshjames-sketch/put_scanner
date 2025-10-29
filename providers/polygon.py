# Minimal Polygon adapter for Strategy Lab
# Uses only standard library networking to avoid extra dependencies.

from __future__ import annotations
import requests
import os

import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


class PolygonError(Exception):
    pass


@dataclass
class _Resp:
    status: int
    data: dict


class PolygonClient:
    def __init__(self, api_key: str, base_url: str = "https://api.polygon.io") -> None:
        if not api_key:
            raise PolygonError("Missing Polygon API key")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, params: Optional[Dict[str, object]] = None) -> _Resp:
        qs = dict(params or {})
        qs["apiKey"] = self.api_key
        url = f"{self.base_url}{path}?{urlencode(qs, doseq=True)}"
        req = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(req, timeout=15) as resp:
                status = resp.getcode() or 0
                data = json.loads(resp.read().decode("utf-8"))
                return _Resp(status=status, data=data)
        except Exception as e:
            raise PolygonError(f"GET {path} failed: {e}")

    # ---------- Public methods used by Strategy Lab ----------

    def last_price(self, symbol: str) -> float:
        """Return previous close as a proxy for last price using aggregates.
        This endpoint is stable across API versions and avoids last-trade quirks.
        """
        path = f"/v2/aggs/ticker/{symbol.upper()}/prev"
        resp = self._get(path, {"adjusted": "false", "limit": 1})
        if resp.status != 200:
            raise PolygonError(f"HTTP {resp.status}: {resp.data}")
        results = resp.data.get("results") or []
        if not results:
            raise PolygonError(f"No results for {symbol}")
        close = results[0].get("c")
        if close is None or not (close == close):
            raise PolygonError(f"No price in response for {symbol}")
        return float(close)

    def expirations(self, symbol: str) -> List[str]:
        """List option expiration dates for the underlying symbol."""
        out: List[str] = []
        seen = set()
        params: Dict[str, object] = {
            "underlying_ticker": symbol.upper(),
            "active": "true",
            "limit": 1000,
            "order": "asc",
            "sort": "expiration_date",
        }
        path = "/v3/reference/options/contracts"
        next_url: Optional[str] = None
        for _ in range(10):  # cap pagination to be safe
            if next_url:
                # next_url already includes apiKey; call directly
                req = Request(next_url, headers={"Accept": "application/json"})
                try:
                    with urlopen(req, timeout=20) as resp:
                        status = resp.getcode() or 0
                        data = json.loads(resp.read().decode("utf-8"))
                except Exception as e:
                    raise PolygonError(f"pagination error: {e}")
            else:
                r = self._get(path, params)
                status = r.status
                data = r.data
            if status != 200:
                raise PolygonError(f"HTTP {status}: {data}")
            results = data.get("results") or []
            for row in results:
                exp = row.get("expiration_date")
                if exp and exp not in seen:
                    seen.add(exp)
                    out.append(exp)
            next_url = data.get("next_url")
            if not next_url:
                break
        out.sort()
        return out

    def chain_snapshot_df(self, symbol: str, expiration: str) -> pd.DataFrame:
        """Return a DataFrame for calls and puts at the given expiration.
        Columns normalized to resemble yfinance: type, strike, bid, ask, lastPrice,
        impliedVolatility (decimal), openInterest, and mark when derivable.
        """
        params: Dict[str, object] = {
            "expiration_date": expiration, "limit": 1000}
        path = f"/v3/snapshot/options/{symbol.upper()}"
        rows: List[dict] = []
        next_url: Optional[str] = None
        for _ in range(10):
            if next_url:
                req = Request(next_url, headers={"Accept": "application/json"})
                try:
                    with urlopen(req, timeout=25) as resp:
                        status = resp.getcode() or 0
                        data = json.loads(resp.read().decode("utf-8"))
                except Exception as e:
                    raise PolygonError(f"snapshot pagination error: {e}")
            else:
                r = self._get(path, params)
                status = r.status
                data = r.data
            if status != 200:
                raise PolygonError(f"HTTP {status}: {data}")
            results = data.get("results") or []
            for r in results:
                ct = (r.get("contract_type") or "").lower()
                typ = "call" if ct.startswith("c") else (
                    "put" if ct.startswith("p") else ct)
                strike = r.get("strike_price")
                # bid/ask try top-level, else last_quote
                lq = r.get("last_quote") or {}
                bid = r.get("bid_price") if r.get(
                    "bid_price") is not None else lq.get("bid_price")
                ask = r.get("ask_price") if r.get(
                    "ask_price") is not None else lq.get("ask_price")
                # last price: prefer last_trade price, then last_price, then day close
                lt = r.get("last_trade") or {}
                last = (
                    lt.get("price")
                    if lt
                    else (r.get("last_price") if r.get("last_price") is not None else (r.get("day") or {}).get("close"))
                )
                iv = r.get("implied_volatility")
                oi = r.get("open_interest")
                # mark as mid if possible
                mark = None
                try:
                    b = float(bid) if bid is not None else math.nan
                    a = float(ask) if ask is not None else math.nan
                    if b == b and a == a and b > 0 and a > 0:
                        mark = b + 0.5 * (a - b)
                except Exception:
                    pass
                rows.append(
                    {
                        "type": typ,
                        "strike": strike,
                        "bid": bid,
                        "ask": ask,
                        "lastPrice": last,
                        "impliedVolatility": iv,
                        "openInterest": oi,
                        "mark": mark,
                    }
                )
            next_url = data.get("next_url")
            if not next_url:
                break
        df = pd.DataFrame(rows)
        # Normalize types/IV where possible
        if not df.empty:
            df["type"] = df["type"].astype(str).str.lower()
            # Ensure IV is decimal
            if "impliedVolatility" in df.columns:
                try:
                    df["impliedVolatility"] = pd.to_numeric(
                        df["impliedVolatility"], errors="coerce")
                except Exception:
                    pass
        return df


class PolygonError(RuntimeError):
    pass


class PolygonClient:
    """
    Lightweight Polygon.io wrapper for:
      - last trade price (equity)
      - expirations (reference contracts)
      - chain snapshots (calls+puts) incl. greeks/IV/OI
    """

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.polygon.io", timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("POLYGON_API_KEY")
        if not self.api_key:
            raise PolygonError(
                "POLYGON_API_KEY missing. Export it or pass api_key=...")
        self.timeout = timeout
        self.sess = requests.Session()
        self.sess.headers.update(
            {"Authorization": f"Bearer {self.api_key}", "User-Agent": "strategy-lab/1.0"})

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        r = self.sess.get(url, params=params or {}, timeout=self.timeout)
        if r.status_code >= 400:
            raise PolygonError(f"GET {url} {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except Exception as e:
            raise PolygonError(f"JSON decode error for {url}: {e}") from e

    # ---------- Equity price ----------
    def last_price(self, symbol: str) -> float:
        # Try real-time last trade; fall back to prev close
        try:
            d = self._get(f"/v2/last/trade/{symbol}")
            p = d.get("results", {}).get("p")
            if p is not None:
                return float(p)
        except Exception:
            pass
        d = self._get(f"/v2/aggs/ticker/{symbol}/prev")
        r = (d or {}).get("results") or []
        if not r:
            raise PolygonError(f"No price for {symbol}")
        return float(r[0].get("c"))

    # ---------- Expirations ----------
    def expirations(self, underlying: str, max_pages: int = 10) -> list[str]:
        """
        Collect distinct expiration dates from reference contracts.
        """
        params = {
            "underlying_ticker": underlying,
            "expired": "false",
            "limit": 250,
            "order": "asc",
            "sort": "expiration_date",
        }
        out, page = set(), 0
        path = "/v3/reference/options/contracts"
        while page < max_pages and path:
            d = self._get(path, params=params)
            results = (d or {}).get("results") or []
            for r in results:
                exp = r.get("expiration_date")
                if exp:
                    out.add(str(exp)[:10])
            path = d.get("next_url")
            if path:
                path = path.replace(self.base_url, "")
                params = None
            page += 1
        return sorted(out)

    # ---------- Chain snapshots (greeks, IV, OI) ----------
    def chain_snapshot_df(self, underlying: str, expiration: str, max_pages: int = 10) -> pd.DataFrame:
        """
        Pull all contracts via snapshot (paged), filter by expiration date.
        Returns DataFrame with: type, strike, bid, ask, last, openInterest, impliedVolatility, delta, gamma, theta, vega, volume.
        """
        params = {"limit": 250}
        path = f"/v3/snapshot/options/{underlying}"
        rows, page = [], 0
        while page < max_pages and path:
            d = self._get(path, params=params)
            results = (d or {}).get("results") or []
            for r in results:
                det = r.get("details") or {}
                exp = (det.get("expiration_date") or "")[:10]
                if exp != expiration:
                    continue
                typ = (det.get("contract_type") or "").lower()
                strike = det.get("strike_price")
                lq = r.get("last_quote") or {}
                lt = r.get("last_trade") or {}
                gk = r.get("greeks") or {}
                oi = r.get("open_interest")
                try:
                    # Resolve prices with sensible fallbacks
                    bid_src = lq.get("bid_price", lq.get("bid", None))
                    ask_src = lq.get("ask_price", lq.get("ask", None))
                    bid_val = float(
                        bid_src) if bid_src is not None else float("nan")
                    ask_val = float(
                        ask_src) if ask_src is not None else float("nan")
                    last_trade = float(lt.get("price", 0.0) or 0.0)
                    day_close = float(
                        (r.get("day", {}) or {}).get("close", 0.0) or 0.0)
                    last_price = float(r.get("last_price", 0.0) or 0.0)
                    last_val = last_trade or last_price or day_close or 0.0
                    mark_val = None
                    if bid_val > 0 and ask_val > 0:
                        mark_val = (bid_val + ask_val) / 2.0
                    elif last_val > 0:
                        mark_val = last_val

                    rows.append({
                        "symbol": underlying,
                        "type": typ,
                        "expiration": exp,
                        "strike": float(strike) if strike is not None else float("nan"),
                        # Use normalized prices
                        "bid": bid_val,
                        "ask": ask_val,
                        "last": last_val,
                        "lastPrice": last_val,
                        "openInterest": int(oi or 0),
                        # decimal IV: prefer top-level implied_volatility; fallback to greeks.iv
                        "impliedVolatility": (
                            float(r.get("implied_volatility"))
                            if r.get("implied_volatility") is not None else (
                                float(gk.get("iv")) if gk.get(
                                    "iv") is not None else float("nan")
                            )
                        ),
                        "delta": float(gk.get("delta", 0.0) or 0.0),
                        "gamma": float(gk.get("gamma", 0.0) or 0.0),
                        "theta": float(gk.get("theta", 0.0) or 0.0),
                        "vega": float(gk.get("vega", 0.0) or 0.0),
                        "volume": int(r.get("day", {}).get("volume", 0) or 0),
                        "mark": mark_val,
                    })
                except Exception:
                    continue
            path = d.get("next_url")
            if path:
                path = path.replace(self.base_url, "")
                params = None
            page += 1
        df = pd.DataFrame(rows)
        return df

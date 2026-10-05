#!/usr/bin/env python3
"""Headless Paper Trading & USIC Execution Daemon.
Tracks open paper positions & executes USIC rules (BE shield, trailing stop, 1.5R 50%, 2.5R runner).
"""
from __future__ import annotations
import argparse, json, math, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORTFOLIO_PATH = ROOT / "data" / "paper_portfolio.json"
FINANCE_QUERY_URL = "https://finance-query.com/v2/quote"
WORKER_PROXY_URL = "https://nse-quote.audittool-api.workers.dev"
CLOUD_PORTFOLIO_URL = "https://nse-quote.audittool-api.workers.dev/portfolio"

def load_portfolio(path: Path = DEFAULT_PORTFOLIO_PATH, sync_cloud: bool = True, key: str = "default") -> dict[str, Any]:
    """Load portfolio state from Cloudflare KV edge or disk."""
    if sync_cloud:
        try:
            req = urllib.request.Request(f"{CLOUD_PORTFOLIO_URL}?key={urllib.parse.quote(key)}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, dict) and "positions" in data and not data.get("isNew"):
                        save_portfolio(data, path, sync_cloud=False)
                        return data
        except Exception:
            pass
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"initialCapital": 1e6, "cash": 1e6, "positions": [], "closedTrades": [], "lastUpdated": datetime.now(timezone.utc).isoformat()}


def save_portfolio(
    portfolio: dict[str, Any],
    path: Path = DEFAULT_PORTFOLIO_PATH,
    sync_cloud: bool = True,
    key: str = "default",
) -> None:
    """Save portfolio state to disk and Cloudflare KV edge."""
    path.parent.mkdir(parents=True, exist_ok=True)
    portfolio["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
    if sync_cloud:
        try:
            body = json.dumps(portfolio).encode("utf-8")
            req = urllib.request.Request(
                f"{CLOUD_PORTFOLIO_URL}?key={urllib.parse.quote(key)}",
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=3) as _:
                pass
        except Exception:
            pass


def fetch_live_quotes(symbols: list[str]) -> dict[str, float]:
    """Fetch live market prices via finance-query.com with Cloudflare and yfinance fallbacks."""
    prices: dict[str, float] = {}
    clean_syms = [s.strip().upper() for s in symbols if s.strip()]
    if not clean_syms:
        return prices

    # 1. Primary: finance-query.com (Verdenroz/finance-query)
    for sym in clean_syms:
        sym_ns = sym if sym.endswith(".NS") or sym.startswith("^") else f"{sym}.NS"
        try:
            url = f"{FINANCE_QUERY_URL}/{urllib.parse.quote(sym_ns)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    p = data.get("regularMarketPrice")
                    if p is not None and not math.isnan(float(p)):
                        prices[sym] = float(p)
        except Exception:
            continue

    # 2. Secondary fallback: Cloudflare Worker Proxy
    missing = [s for s in clean_syms if s not in prices]
    for sym in missing:
        sym_ns = sym if sym.endswith(".NS") or sym.startswith("^") else f"{sym}.NS"
        try:
            url = f"{WORKER_PROXY_URL}/?symbol={urllib.parse.quote(sym_ns)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    p = data.get("price")
                    if p is not None and not math.isnan(float(p)):
                        prices[sym] = float(p)
        except Exception:
            continue

    # 2. Fallback to yfinance for any missing symbols
    missing = [s for s in clean_syms if s not in prices]
    if missing:
        try:
            import yfinance as yf
            yf_tickers = [s if s.endswith(".NS") or s.startswith("^") else f"{s}.NS" for s in missing]
            df = yf.download(yf_tickers, period="5d", interval="1d", progress=False, auto_adjust=False)
            for s, ysym in zip(missing, yf_tickers):
                if hasattr(df, "columns") and ysym in df["Close"]:
                    series = df["Close"][ysym].dropna()
                    if len(series):
                        prices[s] = float(series.iloc[-1])
        except Exception:
            pass

    return prices


def evaluate_staged_positions(
    portfolio: dict[str, Any],
    live_prices: dict[str, float]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate and execute automatic USIC rules (Stops & 1.5R Take-Profits)."""
    open_positions = portfolio.get("positions", [])
    closed_trades = portfolio.get("closedTrades", [])
    cash = float(portfolio.get("cash", 1000000.0))
    executed_events: list[dict[str, Any]] = []

    remaining_positions = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for pos in open_positions:
        sym = pos["symbol"]
        cur = live_prices.get(sym, float(pos.get("currentPrice", pos["buyPrice"])))
        pos["currentPrice"] = cur
        buy = float(pos["buyPrice"])
        shares = int(pos["shares"])
        stop = float(pos["stopPrice"])
        init_stop = float(pos.get("initialStopPrice", stop))
        risk_per_share = max(0.1, buy - init_stop)
        target1 = float(pos.get("target1Price", buy + 1.5 * risk_per_share))
        target2 = float(pos.get("target2Price", buy + 2.5 * risk_per_share))
        scaled_out = bool(pos.get("scaledOut", False))

        pos["peakPrice"] = max(float(pos.get("peakPrice", buy)), cur)
        roi = ((cur - buy) / buy) * 100.0
        pos["peakRoi"] = max(float(pos.get("peakRoi", 0.0)), roi)

        # Rule 0a: Automatic Breakeven Shield (+2% Gain)
        if roi >= 2.0 and stop < buy:
            pos["stopPrice"] = buy
            stop = buy
            executed_events.append({"action": "BREAKEVEN_SHIELD", "symbol": sym, "price": cur, "roi": roi})

        # Rule 0b: Automatic Dynamic Trailing Stop (+3.5%+ Peak Gain)
        if pos["peakRoi"] >= 3.5:
            profit_lock = buy + (pos["peakPrice"] - buy) * 0.55
            buffer_stop = pos["peakPrice"] * 0.96
            trail = max(profit_lock, buffer_stop)
            if trail > stop:
                pos["stopPrice"] = round(trail, 2)
                stop = pos["stopPrice"]
                executed_events.append({"action": "TRAIL_UPDATE", "symbol": sym, "price": cur, "roi": roi, "newStop": stop})

        # Check Rule 1: Automatic Stop-Loss or Trailing Stop Breach
        if cur <= stop:
            exit_pnl = (shares * cur) - (shares * buy)
            cash += shares * cur
            if stop > buy:
                reason = f"🛡️ Auto Trailing Stop Executed at ₹{cur:.2f} (Peak ₹{pos['peakPrice']:.2f}, Locked {roi:+.2f}%)"
            elif stop >= buy:
                reason = f"🛡️ Auto Breakeven Shield Executed at ₹{cur:.2f} ({roi:+.2f}%)"
            else:
                reason = f"🛑 Auto Stop-Loss Triggered at ₹{cur:.2f} ({roi:+.2f}%)"
            closed_trades.append({
                "symbol": sym,
                "setupType": pos.get("setupType", "Breakout Model"),
                "shares": shares,
                "buyPrice": buy,
                "exitPrice": cur,
                "pnl": round(exit_pnl, 2),
                "roi": round(roi, 2),
                "entryDate": pos.get("entryDate", now_str),
                "exitDate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "exitReason": reason,
            })
            executed_events.append({"action": "STOP", "symbol": sym, "price": cur, "roi": roi})
            continue

        # Check Rule 2: Automatic Target 1 (+1.5R) 50% Scale-Out
        if not scaled_out and cur >= target1:
            half_shares = math.floor(shares / 2)
            if half_shares > 0:
                pnl_half = (half_shares * cur) - (half_shares * buy)
                roi_half = ((cur - buy) / buy) * 100.0
                cash += half_shares * cur
                closed_trades.append({
                    "symbol": sym,
                    "setupType": pos.get("setupType", "Breakout Model"),
                    "shares": half_shares,
                    "buyPrice": buy,
                    "exitPrice": cur,
                    "pnl": round(pnl_half, 2),
                    "roi": round(roi_half, 2),
                    "entryDate": pos.get("entryDate", now_str),
                    "exitDate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "exitReason": f"🎯 Auto Target 1.5R Locked (50% Scale-Out at ₹{cur:.2f}, {roi_half:+.2f}%)",
                })
                pos["shares"] = shares - half_shares
                pos["scaledOut"] = True
                pos["stopPrice"] = round(max(stop, buy * 1.005), 2)  # Raised to Breakeven+
                executed_events.append({"action": "TARGET1", "symbol": sym, "price": cur, "roi": roi_half})

        # Check Rule 3: Automatic Target 2 (+2.5R) Runner Exit
        if pos.get("scaledOut", False) and cur >= target2:
            rem_shares = int(pos["shares"])
            exit_pnl = (rem_shares * cur) - (rem_shares * buy)
            roi = ((cur - buy) / buy) * 100.0
            cash += rem_shares * cur
            closed_trades.append({
                "symbol": sym,
                "setupType": pos.get("setupType", "Breakout Model"),
                "shares": rem_shares,
                "buyPrice": buy,
                "exitPrice": cur,
                "pnl": round(exit_pnl, 2),
                "roi": round(roi, 2),
                "entryDate": pos.get("entryDate", now_str),
                "exitDate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "exitReason": f"🏆 Auto Target 2.5R Runner Locked (+{roi:+.2f}%)",
            })
            executed_events.append({"action": "TARGET2", "symbol": sym, "price": cur, "roi": roi})
            continue

        remaining_positions.append(pos)

    portfolio["positions"] = remaining_positions
    portfolio["closedTrades"] = closed_trades
    portfolio["cash"] = round(cash, 2)
    return portfolio, executed_events


def print_portfolio_status(portfolio: dict[str, Any]) -> None:
    """Print readable terminal HUD for paper portfolio."""
    cash = portfolio.get("cash", 0.0)
    pos_list = portfolio.get("positions", [])
    closed_list = portfolio.get("closedTrades", [])
    invested = sum(p["shares"] * p["buyPrice"] for p in pos_list)
    cur_val = sum(p["shares"] * p.get("currentPrice", p["buyPrice"]) for p in pos_list)
    unrealized = cur_val - invested
    realized = sum(t["pnl"] for t in closed_list)

    print("\n" + "=" * 70)
    print("💼 ASTRA QUANT • HEADLESS PAPER TRADING MONITOR")
    print(f"Total Value: ₹{cash + cur_val:,.2f} | Cash: ₹{cash:,.2f} | Invested: ₹{invested:,.2f}")
    print(f"Unrealized P&L: ₹{unrealized:+,.2f} | Realized P&L: ₹{realized:+,.2f} | Open: {len(pos_list)}")
    print("-" * 70)
    for p in pos_list:
        cur = p.get("currentPrice", p["buyPrice"])
        roi = ((cur - p["buyPrice"]) / p["buyPrice"]) * 100.0
        be_tag = " [🛡️ BE]" if p.get("stopPrice", 0) >= p["buyPrice"] else ""
        scale_tag = " [✅ 1.5R LOCKED]" if p.get("scaledOut") else ""
        print(f"• {p['symbol']:<10} {p['shares']:>5} sh @ ₹{p['buyPrice']:>7.2f} -> LTP: ₹{cur:>7.2f} ({roi:>+6.2f}%) | Stop: ₹{p['stopPrice']:>7.2f}{be_tag}{scale_tag}")
    print("=" * 70 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless Paper Trading & Execution Daemon")
    ap.add_argument("--portfolio", default=str(DEFAULT_PORTFOLIO_PATH))
    ap.add_argument("--once", action="store_true", help="Run single evaluation cycle")
    ap.add_argument("--no-cloud", action="store_true", help="Disable Cloudflare KV edge sync")
    ap.add_argument("--key", default="default", help="Cloudflare KV sync key / passphrase")
    args = ap.parse_args()

    sync_cloud = not args.no_cloud
    p_path = Path(args.portfolio)
    port = load_portfolio(p_path, sync_cloud=sync_cloud, key=args.key)
    syms = [p["symbol"] for p in port.get("positions", [])]
    prices = fetch_live_quotes(syms) if syms else {}
    port, events = evaluate_staged_positions(port, prices)
    save_portfolio(port, p_path, sync_cloud=sync_cloud, key=args.key)
    print_portfolio_status(port)
    if events:
        print(f"⚡ Executed {len(events)} automated rules:")
        for ev in events:
            extra = f" -> Stop: ₹{ev['newStop']:.2f}" if 'newStop' in ev else ""
            print(f"  -> {ev['action']}: {ev['symbol']} at ₹{ev['price']:.2f} ({ev.get('roi', 0.0):+.2f}%){extra}")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

#!/usr/bin/env python3
"""Decision trail: which stocks, which criteria, and the history behind them.

  python scripts/decisions.py
  python scripts/decisions.py --top 15 --asof 2026-09-25
  python scripts/decisions.py --symbols CUPID,MARINE,WELSPUNLIV

Writes reports/DECISIONS.md (readable) and reports/decisions.json (agent
readable):

  1. the blended quality score and what each component means,
  2. the hard gates a stock must clear,
  3. today's ranked names with the reason for each,
  4. every strategy in the engine and its rule,
  5. the historical evidence per strategy (cohort size, hit rate, expectancy
     with a 95% CI, and whether it beats the seeded random null).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from collections import defaultdict
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import audit, engine, evidence, quality, regime, sector, sizing  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import data_quality_report, load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402
from protocol.github_screeners import (  # noqa: E402
    compute_screener_features, screen_canslim, screen_darvas_box,
    screen_minervini, screen_pkscreener_vcp, screen_protocol_v2,
    screen_qullamaggie, screen_relative_strength, screen_stan_weinstein,
    screen_turtle_trading, screen_wyckoff_closing_range, screen_sector_momentum_leader,
    screen_connors_rsi_pullback,
)
from protocol.simulator import prepare  # noqa: E402

DEFAULT_SET = ["recovered_after_rej", "pa_state_a", "trap", "random"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Which stocks, which criteria, what evidence")
    ap.add_argument("--config", default=None)
    wide = ROOT / "data" / "nse_all_history.parquet"
    core = ROOT / "data" / "universe_history.parquet"
    default_data = str(wide if wide.exists() else core)
    ap.add_argument("--data", default=default_data)
    ap.add_argument("--asof", default=None)
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--strategies", default=",".join(DEFAULT_SET))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--symbols", default="all")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    ap.add_argument("--ignore-regime", action="store_true", help="Rank candidates even if market regime is defensive")
    ap.add_argument("--capital-per-stock", type=float, default=None, help="Fixed capital to allocate per stock (e.g. 100000)")
    ap.add_argument("--max-per-sector", type=int, default=1, help="Max candidates per sector")
    args = ap.parse_args()

    cfg = load_config(args.config)
    history = load_history(args.data)
    if args.symbols != "all":
        syms = [s.strip().upper() for s in args.symbols.split(",")]
        history = history[history["Symbol"].isin(syms)]
    if args.asof:
        asof = pd.Timestamp(args.asof)
    else:
        available = pd.Timestamp(history["Date"].max())
        asof = max(available, pd.Timestamp(get(cfg, "validation.validation_end")))
    history = history[history["Date"] <= asof]
    if history.empty:
        print("no data on/before", asof.date())
        return 1

    panel = build_panel(history)
    mkt_regime = regime.get_regime_at(history, asof)

    # ---- 1. today's ranked names (filtered by extension & sector) -----------
    raw_picks = quality.rank(panel, cfg, asof, top=args.top * 3)
    if not raw_picks.empty and "ext_sma50" in raw_picks.columns:
        max_ext = float(cfg.get("quality", {}).get("max_ext_sma50", 0.20))
        raw_picks = raw_picks[raw_picks["ext_sma50"].isna() | (raw_picks["ext_sma50"] <= max_ext)]
    picks = sector.apply_sector_diversification(raw_picks, max_per_sector=args.max_per_sector, top=args.top)
    today = []
    for _, r in picks.iterrows():
        item = {k: r[k] for k in (
            "rank", "symbol", "date", "close", "reference", "rvol20", "atrpct",
            "prox52", "efficiency", "ret20", "ret120", "turnover20",
            "penetration", "stop_proxy", "score", "coverage", "data_status",
            "candidates", "edge", "edge_age_days") if k in picks.columns}
        item["industry"] = r.get("industry") or sector.get_sector(str(r["symbol"]))
        item["reason"] = quality.reason(r, cfg)
        item["gates"] = list(r["gates"])
        today.append(item)

    cand_dicts = [{
        "symbol": t["symbol"],
        "entry_price": float(t["close"]),
        "atr14": float(t.get("atrpct") or 0.03) * float(t["close"]),
        "stop_price": float(t.get("stop_proxy")) if t.get("stop_proxy") is not None else None,
    } for t in today]
    if args.capital_per_stock:
        allocations = sizing.allocate_fixed_capital_per_stock(
            cand_dicts, capital_per_stock=args.capital_per_stock
        )
        rem_cash = 0.0
    else:
        allocations, rem_cash = sizing.allocate_portfolio_capital(
            cand_dicts, total_portfolio_capital=args.capital, risk_per_trade_pct=0.01
        )
    alloc_map = {a.symbol: a for a in allocations}
    for t in today:
        al = alloc_map.get(t["symbol"])
        if al:
            t["shares"] = al.shares
            t["capital_allocated"] = al.capital_allocated
            t["risk_rupees"] = al.risk_rupees
            t["stop_price"] = al.stop_price
            t["capital_pct"] = al.capital_pct

    # ---- 1b. multi-framework confluence candidates -------------------------
    confluence_top = []
    try:
        feat = compute_screener_features(history, asof)
        groups = [
            ("Protocol Fortified", screen_protocol_v2(feat, top_n=60, min_turnover_cr=0.5)),
            ("Relative Strength Leader", screen_relative_strength(feat, top_n=60, min_turnover_cr=0.5)),
            ("Minervini Template", screen_minervini(feat, top_n=60, min_turnover_cr=0.5)),
            ("Stan Weinstein Stage 2", screen_stan_weinstein(feat, top_n=60, min_turnover_cr=0.5)),
            ("Qullamaggie Breakout", screen_qullamaggie(feat, top_n=60, min_turnover_cr=0.5)),
            ("CANSLIM Setup", screen_canslim(feat, top_n=60, min_turnover_cr=0.5)),
            ("Turtle Trading Breakout", screen_turtle_trading(feat, top_n=60, min_turnover_cr=0.5)),
            ("Darvas Box Breakout", screen_darvas_box(feat, top_n=60, min_turnover_cr=0.5)),
            ("PKScreener VCP", screen_pkscreener_vcp(feat, top_n=60, min_turnover_cr=0.5)),
            ("Wyckoff Closing Range", screen_wyckoff_closing_range(feat, top_n=60, min_turnover_cr=0.5)),
            ("Industry Momentum Leader", screen_sector_momentum_leader(feat, top_n=60, min_turnover_cr=0.5)),
            ("Connors RSI Pullback", screen_connors_rsi_pullback(feat, top_n=60, min_turnover_cr=0.5)),
        ]
        fw_counts = defaultdict(list)
        fw_sym_data = {}
        for gname, sub in groups:
            for item in sub:
                s = item.symbol
                fw_counts[s].append(gname)
                if s not in fw_sym_data:
                    fw_sym_data[s] = item

        deliv_file = ROOT / "data" / "delivery_history.parquet"
        deliv_map = {}
        if deliv_file.exists():
            try:
                ddf = pd.read_parquet(deliv_file)
                ddf["Date"] = pd.to_datetime(ddf["Date"]).dt.normalize()
                dsub = ddf[ddf["Date"] == asof]
                deliv_map = dict(zip(dsub["Symbol"].astype(str), dsub["DelivPct"].astype(float)))
            except Exception:
                pass

        sorted_fw = sorted(fw_counts.items(), key=lambda x: (len(x[1]), fw_sym_data[x[0]].ret20), reverse=True)
        for s, fws in sorted_fw[:max(10, args.top)]:
            item = fw_sym_data[s]
            sec = sector.get_sector(s)
            deliv = deliv_map.get(s)
            p52 = float(feat.loc[feat["Symbol"] == s, "prox52"].iloc[0]) if "prox52" in feat.columns and not feat.loc[feat["Symbol"] == s].empty else 1.0
            confluence_top.append({
                "symbol": s,
                "industry": sec,
                "close": round(float(item.close), 2),
                "rvol": round(float(item.rvol20), 2),
                "ret20": round(float(item.ret20), 4),
                "deliv_pct": round(float(deliv), 1) if deliv is not None else None,
                "prox52": round(p52, 4),
                "frameworks_passed": fws,
                "framework_count": len(fws),
            })
    except Exception as e:
        print(f"Warning: could not compute multi-framework confluence: {e}")

    # ---- 2. historical evidence per strategy -------------------------------
    bars = {s: b.sort_values("Date").reset_index(drop=True)
            for s, b in history.groupby("Symbol")}
    arrays = {s: prepare(b) for s, b in bars.items()}
    names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    ev_rows, null_exp = [], None
    for name in names:
        run = engine.run_strategy(name, panel, bars, cfg, args.capital, (None, None),
                                  None, arrays)
        e = evidence.evidence_for(run["trades"], cfg, label=name)
        if name == "random":
            null_exp = e["expectancy"]
        ev_rows.append(e)
    for e in ev_rows:
        e.update(evidence.compare_to_null(e, null_exp))

    winners = [e for e in ev_rows if e.get("beats_null")]
    if today:
        best = winners[0] if winners else max(
            ev_rows, key=lambda x: x.get("expectancy") or -9)
        if mkt_regime["regime"] == "DEFENSIVE" and not args.ignore_regime:
            headline = (
                f"MARKET REGIME DEFENSIVE ({mkt_regime['action']}): "
                f"{mkt_regime['message']} "
                f"Top defensive candidate is {today[0]['symbol']} (score {today[0]['score']}). "
                f"Capital protection (CASH) advised.")
        else:
            headline = (
                f"{today[0]['symbol']} ranks first today (quality score {today[0]['score']}). "
                f"The rule with the best evidence is `{best['label']}`: it has fired "
                f"{best['N']} times historically and averages {best['expectancy']} net per "
                f"trade versus {null_exp} for the seeded random null — "
                f"{'it beats the null' if best.get('beats_null') else 'it does NOT beat the null'}.")
    else:
        headline = ("No stock cleared every hard gate today. That is a real answer: "
                    "the engine is saying there is nothing worth buying right now.")

    components_meta = [{
        "name": field, "label": label, "measures": measures, "why": why,
        "sign": sign, "weight": cfg["quality"]["weights"].get(field),
    } for field, (label, sign, measures, why) in quality.COMPONENTS.items()]
    components_meta.append({
        "name": "edge", "label": "Reclaimed-reference pattern", "sign": 1,
        "measures": "the recovered_after_rej pattern fired recently",
        "why": "the only registered rule that ever beat the random null, but "
               "never independently validated, so the weight is held small",
        "weight": quality.EDGE_WEIGHT,
    })

    payload = {
        "asof": str(asof.date()), "config_hash": cfg["_hash"],
        "universe": {"symbols": int(history["Symbol"].nunique()),
                     "sessions": int(history["Date"].nunique()),
                     "from": str(history["Date"].min().date()),
                     "to": str(history["Date"].max().date())},
        "audit_passed": bool(audit.static_scan()["pass"]),
        "data_quality": data_quality_report(history),
        "headline": headline, "today": today, "components": components_meta,
        "rule_chain": today[0]["gates"] if today else quality.gates(pd.Series(dtype=object), cfg),
        "sufficiency": quality.data_sufficiency_report(panel, cfg, asof),
        "strategies": evidence.STRATEGIES, "evidence": ev_rows,
        "caveats": evidence.CAVEATS,
        "regime": mkt_regime,
        "confluence_top": confluence_top,
    }

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "DECISIONS.md").write_text(evidence.to_markdown(payload), encoding="utf-8")
    (out / "decisions.json").write_text(json.dumps(payload, indent=2, default=str),
                                        encoding="utf-8")

    print(f"\n==============================================================================")
    print(f"MARKET REGIME: {mkt_regime['regime']} ({mkt_regime['action']})")
    print(f"{mkt_regime['message']}")
    print(f"==============================================================================\n")
    print(payload["headline"])
    if today:
        print()
        for t in today:
            sec_lbl = f"[{t.get('industry', 'Unknown')}]"
            print(f"  {t['rank']:>2}. {t['symbol']:<12} {sec_lbl:<25} score={t['score']:.2f}  {t['reason']}")
        if args.capital_per_stock:
            print(f"\n--- CAPITAL INFUSION (Fixed INR {args.capital_per_stock:,.0f} per Stock) ---")
        else:
            print("\n--- VOLATILITY RISK-PARITY CAPITAL INFUSION (1% Risk / Trade) ---")
        print(f"  {'Symbol':<12} {'Shares':>7} {'Entry (INR)':>12} {'Infusion (INR)':>16} {'Alloc %':>9} {'Stop (INR)':>12} {'Risk (INR)':>12}")
        print("  " + "-" * 84)
        for t in today:
            if "capital_allocated" in t:
                print(f"  {t['symbol']:<12} {t['shares']:>7d} {t['close']:>12.2f} {t['capital_allocated']:>16.2f} {t.get('capital_pct', 0.0)*100:>8.1f}% {t.get('stop_price', 0.0):>12.2f} {t.get('risk_rupees', 0.0):>12.2f}")
        print("  " + "-" * 84)
        total_infusion = sum(t.get("capital_allocated", 0.0) for t in today)
        if args.capital_per_stock:
            print(f"  Total Portfolio Infusion: INR {total_infusion:,.2f} across {len(today)} stocks (INR {args.capital_per_stock:,.0f} per stock)")
        else:
            print(f"  Portfolio Capital: INR {args.capital:,.2f} | Total Allocated: INR {total_infusion:,.2f} | Cash: INR {rem_cash:,.2f}")

    if confluence_top:
        print(f"\n==============================================================================")
        print(f"MULTI-FRAMEWORK CONFLUENCE LEADERS (Top {len(confluence_top)} Setups across 12 Frameworks)")
        print(f"==============================================================================")
        print(f"  {'Rank':>4} {'Symbol':<12} {'Sector':<26} {'Confluence':>10} {'Close (INR)':>12} {'Top Frameworks'}")
        print("  " + "-" * 84)
        for idx, c in enumerate(confluence_top, 1):
            fws = ", ".join(c["frameworks_passed"][:3])
            if len(c["frameworks_passed"]) > 3:
                fws += f" (+{len(c['frameworks_passed']) - 3} more)"
            print(f"  {idx:>4}. {c['symbol']:<12} {c['industry'][:24]:<26} {c['framework_count']:>2}/12     {c['close']:>12.2f}  {fws}")

    print()
    print(f"{'strategy':<24}{'N':>8}{'expectancy':>12}{' 95% CI':>24}{'  vs null':>10}")
    for e in ev_rows:
        ci = e.get("expectancy_ci") or ["", ""]
        print(f"{e['label']:<24}{e['N']:>8}{str(e['expectancy']):>12}"
              f"{str(ci[0]) + ' to ' + str(ci[1]):>24}{str(e.get('beats_null')):>10}")
    print(f"\nwrote {out / 'DECISIONS.md'}, {out / 'decisions.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
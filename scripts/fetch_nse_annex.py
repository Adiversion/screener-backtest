#!/usr/bin/env python3
"""Fetch supplementary NSE datasets: Board Meetings, Corporate Actions & Breadth.

Uses the unofficial nse package to download event calendars and corporate announcements,
caching them in data/ for the screener and risk blackout engine.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"


def fetch_annex_data() -> dict[str, int]:
    """Fetch board meetings, corporate actions, and save as CSVs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    counts = {"board_meetings": 0, "corporate_actions": 0}

    try:
        from nse import NSE
        try:
            ctx = NSE(download_folder=DATA_DIR)
        except TypeError:
            ctx = NSE(download_folder=DATA_DIR, server=False)
        with ctx as nse:
            # 1. Fetch Board Meetings / Results calendar
            try:
                bm = nse.boardMeetings()
                if isinstance(bm, list) and len(bm) > 0:
                    df_bm = pd.DataFrame(bm)
                    out_bm = DATA_DIR / "board_meetings.csv"
                    df_bm.to_csv(out_bm, index=False)
                    counts["board_meetings"] = len(df_bm)
                    print(f"Saved {len(df_bm)} board meetings -> {out_bm}")
            except Exception as e:
                print(f"[WARN] Failed to fetch board meetings: {e}")

            # 2. Fetch Corporate Actions (Dividends, Splits, Bonus)
            try:
                acts = nse.actions()
                if isinstance(acts, list) and len(acts) > 0:
                    df_act = pd.DataFrame(acts)
                    out_act = DATA_DIR / "corporate_actions.csv"
                    df_act.to_csv(out_act, index=False)
                    counts["corporate_actions"] = len(df_act)
                    print(f"Saved {len(df_act)} corporate actions -> {out_act}")
            except Exception as e:
                print(f"[WARN] Failed to fetch corporate actions: {e}")

            # 3. Fetch latest Price Band & Surveillance Report (sec_list)
            try:
                # Try today or recent market date
                now = datetime.now()
                sec_path = None
                for d in [now, datetime(2026, 10, 1)]:
                    try:
                        sec_path = nse.priceband_report(d)
                        if sec_path and Path(sec_path).exists():
                            break
                    except Exception:
                        continue
                if sec_path and Path(sec_path).exists():
                    df_sec = pd.read_csv(sec_path)
                    out_sec = DATA_DIR / "sec_list_latest.csv"
                    df_sec.to_csv(out_sec, index=False)
                    counts["surveillance_securities"] = len(df_sec)
                    print(f"Saved {len(df_sec)} securities surveillance list -> {out_sec}")
            except Exception as e:
                print(f"[WARN] Failed to fetch priceband report: {e}")

    except ImportError:
        print("[WARN] 'nse' package not installed. Run: pip install nse")
    except Exception as e:
        print(f"[WARN] NSE connection failed: {e}")

    # Fallback copy if sec_list_01102026.csv exists but sec_list_latest.csv does not
    if not (DATA_DIR / "sec_list_latest.csv").exists():
        fallback = DATA_DIR / "sec_list_01102026.csv"
        if fallback.exists():
            import shutil
            shutil.copyfile(fallback, DATA_DIR / "sec_list_latest.csv")

    return counts


if __name__ == "__main__":
    fetch_annex_data()

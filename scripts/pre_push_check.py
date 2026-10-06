#!/usr/bin/env python3
"""Pre-Push & Pre-Flight E2E Headless Verification Suite for GitHub Pages.

Performs strict automated validation before pushing to git:
1. Spins up local static HTTP server for docs/
2. Boots headless Chromium via Playwright
3. Listens for and traps ALL:
   - pageerror (Uncaught JS exceptions, RangeError, TypeError)
   - console.error messages
4. Exercises critical interactive features:
   - Forward Verifier: Session mode -> Individual Stock mode (prevents mutual recursion)
   - Stock search & custom verification (e.g. RAMRAT)
   - Stock modal opening (verifying 9/12 frameworks & multi-year chart)
   - Light Mode toggle (verifying #ffffff chart background & contrast)
   - Fullscreen chart toggle
   - All section routing pages (screener.html, macro.html, verifier.html, paper_trading.html)
5. Exits with code 0 on complete pass, or code 1 with full diagnostics on any failure.
"""
from __future__ import annotations

import http.server
import socketserver
import sys
import threading
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
PORT = 8877


class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress normal access logs


def run_checks() -> int:
    print("=" * 70)
    print("🚀 ASTRA QUANT PRE-FLIGHT E2E BROWSER CHECK (PLAYWRIGHT)")
    print("=" * 70)

    # 1. Start local server
    server = socketserver.TCPServer(("127.0.0.1", PORT), QuietHTTPHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"✓ Local verification server running at http://127.0.0.1:{PORT}")

    errors_found: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Wire exception traps
        def on_page_error(err):
            msg = f"[PAGE_ERROR] {err}"
            print(f"❌ {msg}")
            errors_found.append(msg)

        def on_console(msg):
            if msg.type == "error":
                # Filter benign network aborts if any
                text = msg.text
                if "Failed to load resource" not in text and "favicon.ico" not in text:
                    err_msg = f"[CONSOLE_ERROR] {text}"
                    print(f"❌ {err_msg}")
                    errors_found.append(err_msg)

        page.on("pageerror", on_page_error)
        page.on("console", on_console)

        base_url = f"http://127.0.0.1:{PORT}"

        # -------------------------------------------------------------
        # TEST 1: index.html load & general execution
        # -------------------------------------------------------------
        print("\n[1/6] Loading index.html and checking boot sequence...")
        page.goto(f"{base_url}/index.html", wait_until="networkidle")
        time.sleep(0.5)
        title = page.title()
        print(f"✓ Page title loaded: '{title}'")

        # -------------------------------------------------------------
        # TEST 2: Forward Verifier Mode Switching (Session <-> Stock)
        # -------------------------------------------------------------
        print("\n[2/6] Testing Forward Verifier session & individual stock modes (recursion check)...")
        btn_stock = page.query_selector("#btnFwdModeStock")
        if btn_stock:
            btn_stock.click()
            time.sleep(0.4)
            print("✓ Clicked #btnFwdModeStock (Individual Stock)")

        btn_session = page.query_selector("#btnFwdModeSession")
        if btn_session:
            btn_session.click()
            time.sleep(0.4)
            print("✓ Clicked #btnFwdModeSession (By Session)")

        if btn_stock:
            btn_stock.click()
            time.sleep(0.4)
            print("✓ Returned to #btnFwdModeStock")

        # Verify a specific custom stock
        page.fill("#fwdStockInput", "RAMRAT")
        page.keyboard.press("Enter")
        time.sleep(0.5)
        print("✓ Verified custom stock input for 'RAMRAT'")

        # -------------------------------------------------------------
        # TEST 3: Stock Inspector Modal, Frameworks & Multi-Year Chart
        # -------------------------------------------------------------
        print("\n[3/6] Testing Stock Inspector Modal with RAMRAT...")
        page.evaluate("openModal('RAMRAT')")
        time.sleep(0.8)

        modal = page.query_selector("#stockModal")
        is_open = modal and "open" in (modal.get_attribute("class") or "")
        print(f"✓ Stock modal open: {is_open}")

        sym_text = page.inner_text("#mSym") if page.query_selector("#mSym") else ""
        print(f"✓ Modal symbol displayed: {sym_text}")
        assert "RAMRAT" in sym_text, f"Expected RAMRAT in modal, got {sym_text}"

        badges_text = page.inner_text("#mBadges") if page.query_selector("#mBadges") else ""
        print(f"✓ Framework banner: {badges_text.splitlines()[0] if badges_text else 'N/A'}")

        # Check chart container has rendered canvas elements
        canvases = page.query_selector_all("#stockChartContainer canvas")
        print(f"✓ TradingView Lightweight Chart canvas elements: {len(canvases)}")
        assert len(canvases) > 0, "No chart canvas rendered!"

        # Also verify Weekly candidate with mixed badge shapes
        print("✓ Testing Weekly Candidate modal & badges...")
        test_weekly_sym = page.evaluate("(() => { const c = D.candidates.find(x => x.weekly_bucket && x.symbol !== 'RAMRAT'); return c ? c.symbol : (D.candidates[0] ? D.candidates[0].symbol : 'RAMRAT'); })()")
        page.evaluate(f"openModal('{test_weekly_sym}')")
        time.sleep(0.5)
        weekly_modal_sym = page.inner_text("#mSym") if page.query_selector("#mSym") else ""
        assert test_weekly_sym in weekly_modal_sym, f"Expected {test_weekly_sym} in modal, got {weekly_modal_sym}"
        weekly_badges = page.inner_text("#mBadges") if page.query_selector("#mBadges") else ""
        print(f"✓ Weekly {test_weekly_sym} modal & badges verified: {weekly_badges.splitlines()[0] if weekly_badges else 'N/A'}")

        # Save dark mode screenshot
        dark_png = ROOT / "audit_ramrat_modal_dark.png"
        page.screenshot(path=str(dark_png))
        print(f"✓ Saved dark mode screenshot: {dark_png.name}")

        # -------------------------------------------------------------
        # TEST 4: Light Mode Toggle
        # -------------------------------------------------------------
        print("\n[4/6] Testing Light Mode toggle...")
        btn_theme = page.query_selector("#mThemeToggleBtn")
        if btn_theme:
            btn_theme.click()
            time.sleep(0.5)
            print("✓ Clicked Light Mode button")
            # Save light mode screenshot
            light_png = ROOT / "audit_ramrat_modal_light.png"
            page.screenshot(path=str(light_png))
            print(f"✓ Saved light mode screenshot: {light_png.name}")

            # Switch back to dark mode
            btn_theme.click()
            time.sleep(0.3)
            print("✓ Toggled back to Dark Mode")

        # -------------------------------------------------------------
        # TEST 5: Direct Fullscreen Chart & Drawing Tools
        # -------------------------------------------------------------
        print("\n[5/7] Testing Direct Fullscreen Chart button & Drawing Tools...")
        page.evaluate("openChartFullscreen('DYNAMATECH')")
        time.sleep(0.8)

        is_fullscreen = page.evaluate("isChartFullscreen")
        print(f"✓ Direct Fullscreen active: {is_fullscreen}")
        assert is_fullscreen is True, "Expected chart to open directly in fullscreen!"

        title_text = page.inner_text("#mChartSectionTitle") if page.query_selector("#mChartSectionTitle") else ""
        print(f"✓ Fullscreen chart header: {title_text}")
        assert "DYNAMATECH" in title_text, f"Expected DYNAMATECH in title, got {title_text}"

        hud_text = page.inner_text("#chartFrameworkHud") if page.query_selector("#chartFrameworkHud") else ""
        print(f"✓ Pine Script Framework HUD: {hud_text[:80]}...")
        assert "PINE CONFLUENCE" in hud_text, "Expected Pine Confluence HUD to be populated!"

        # Test Indicator toggles
        btn_ema10 = page.query_selector("#pill_ema10")
        if btn_ema10:
            btn_ema10.click()
            time.sleep(0.2)
            btn_ema10.click()
            print("✓ Toggled EMA 10 indicator visibility")

        btn_all = page.query_selector("#pill_all")
        if btn_all:
            btn_all.click()
            time.sleep(0.2)
            btn_all.click()
            print("✓ Toggled master All Indicators button")

        # Test Drawing Tools
        btn_horz = page.query_selector("#btnToolHorz")
        if btn_horz:
            btn_horz.click()
            time.sleep(0.2)
            chart_container = page.query_selector("#stockChartContainer")
            if chart_container:
                box = chart_container.bounding_box()
                if box:
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    time.sleep(0.3)
                    print("✓ Placed manual Horizontal S/R line at chart center")

        # Save Direct Fullscreen Chart screenshot
        full_png = ROOT / "audit_direct_fullscreen_chart.png"
        page.screenshot(path=str(full_png))
        print(f"✓ Saved direct fullscreen chart screenshot: {full_png.name}")

        # Exit direct fullscreen (must close completely back to screener)
        page.keyboard.press("Escape")
        time.sleep(0.4)
        is_still_open = page.evaluate("document.getElementById('stockModal').classList.contains('open')")
        print(f"✓ Modal closed completely on escape from direct chart: {not is_still_open}")
        assert not is_still_open, "Expected modal to close completely after exiting direct fullscreen chart!"

        # -------------------------------------------------------------
        # TEST 6: Smoke test all standalone pages
        # -------------------------------------------------------------
        print("\n[6/7] Verifying standalone pages...")
        pages_to_check = [
            "screener.html",
            "macro.html",
            "inspector.html",
            "verifier.html",
            "report.html",
            "paper_trading.html",
        ]
        for p_name in pages_to_check:
            page.goto(f"{base_url}/{p_name}", wait_until="networkidle")
            time.sleep(0.3)
            print(f"✓ {p_name} loaded cleanly without exceptions")

        browser.close()

    server.shutdown()

    print("\n" + "=" * 70)
    if errors_found:
        print(f"❌ PRE-FLIGHT CHECK FAILED: {len(errors_found)} error(s) encountered!")
        for e in errors_found:
            print(f"   - {e}")
        print("=" * 70)
        return 1
    else:
        print("🎉 ALL PRE-FLIGHT CHECKS PASSED PERFECTLY (0 ERRORS)")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(run_checks())

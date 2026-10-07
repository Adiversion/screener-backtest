#!/usr/bin/env python3
"""Headless design audit for the Astra Quant site.

Serves `docs/` over a local static server, then captures a screenshot of every
page in both themes at a desktop and a mobile viewport. Reports any console
error or uncaught exception it sees, so a design change cannot pass silently
because the page merely "loaded".

  python scripts/design_audit.py                      # all pages, 2 themes, 2 sizes
  python scripts/design_audit.py --tag baseline       # label the run
  python scripts/design_audit.py --pages index.html   # one page
  python scripts/design_audit.py --no-mobile

Output: reports/design_audit/<tag>/<page>_<theme>_<viewport>.png and a
`summary.json` next to them. Exit code is 1 when any console error is seen.
"""
from __future__ import annotations

import argparse
import http.server
import json
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
# The directory the harness serves. `--dir` switches it to reports/preview for
# the fast design loop; the committed site is always served from docs/.
SERVE_DIR = ROOT / "docs"
PORT = 8899

DEFAULT_PAGES = [
    "index.html",
    "screener.html",
    "macro.html",
    "inspector.html",
    "verifier.html",
    "report.html",
    "paper_trading.html",
]

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}

THEMES = ("dark", "light")

BENIGN = ("Failed to load resource", "favicon.ico", "net::ERR_ABORTED")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SERVE_DIR), **kwargs)

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        pass


def apply_theme(page, theme: str) -> bool:
    """Set the theme through the app's own toggle when it exists.

    Falls back to setting the `data-theme` attribute directly, so the harness
    also works against a build that has no toggle yet (the baseline).
    """
    for sel in ("#themeToggleBtn", "#mThemeToggleBtn", "#themeToggle"):
        node = page.query_selector(sel)
        if not node:
            continue
        try:
            if not node.is_visible():
                continue
            current = page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')"
            )
            if current == theme:
                return True
            node.click(timeout=5_000)
        except Exception:  # noqa: BLE001 - a hidden toggle is not an audit failure
            continue
        time.sleep(0.45)
        if (
            page.evaluate("() => document.documentElement.getAttribute('data-theme')")
            == theme
        ):
            return True
    page.evaluate(
        "(t) => { document.documentElement.setAttribute('data-theme', t);"
        " window.dispatchEvent(new CustomEvent('astra:themechange',"
        " {detail:{theme:t}})); }",
        theme,
    )
    time.sleep(0.25)
    return True


CONTRAST_JS = r"""
(tag) => {
  const parse = (c) => {
    if (!c) return null;
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const p = m[1].split(',').map(x => parseFloat(x.trim()));
      return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }
    const h = c.trim().match(/^#([0-9a-f]{3,8})$/i);
    if (!h) return null;
    let v = h[1];
    if (v.length === 3 || v.length === 4) v = v.split('').map(x => x + x).join('');
    return {
      r: parseInt(v.slice(0, 2), 16),
      g: parseInt(v.slice(2, 4), 16),
      b: parseInt(v.slice(4, 6), 16),
      a: v.length === 8 ? parseInt(v.slice(6, 8), 16) / 255 : 1,
    };
  };
  /* A gradient background has no single colour, so contrast cannot be
     measured on it. Those elements are skipped rather than guessed at. */
  const hasGradient = (el) => {
    let node = el;
    while (node) {
      const img = getComputedStyle(node).backgroundImage;
      if (img && img !== 'none') return true;
      node = node.parentElement;
    }
    return false;
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (a, b) => {
    const la = lum(a), lb = lum(b);
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  };
  /* Composite the ancestor backgrounds bottom-up. Treating a translucent
     parent as opaque reports a colour the eye never sees, so the whole chain
     has to be layered in the right order. */
  const pageColour = () => {
    const root0 = document.documentElement;
    let token = getComputedStyle(root0).getPropertyValue('--bg').trim();
    if (!token) token = getComputedStyle(root0).getPropertyValue('--bg-base').trim();
    const fromToken = token ? parse(token) : null;
    if (fromToken && fromToken.a >= 1) return fromToken;
    const root = parse(getComputedStyle(document.documentElement).backgroundColor);
    if (root && root.a >= 1) return root;
    return { r: 255, g: 255, b: 255, a: 1 };
  };
  const effBg = (el) => {
    const chain = [];
    let node = el;
    while (node) {
      const c = parse(getComputedStyle(node).backgroundColor);
      if (c && c.a > 0) chain.push(c);
      node = node.parentElement;
    }
    let acc = pageColour();
    for (let i = chain.length - 1; i >= 0; i--) acc = over(chain[i], acc);
    return acc;
  };
  const fail = [];
  const seen = new Set();
  const nodes = document.querySelectorAll('body *');
  for (const el of nodes) {
    if (!el.textContent || !el.textContent.trim()) continue;
    if (seen.has(el)) continue;
    let hasOwnText = false;
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) { hasOwnText = true; break; }
    }
    if (!hasOwnText) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.15) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) continue;
    const fg = parse(cs.color);
    if (!fg) continue;
    if (hasGradient(el)) continue;
    const bg = effBg(el);
    const fg2 = over(fg, bg);
    const size = parseFloat(cs.fontSize);
    const bold = parseInt(cs.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const min = large ? 3.0 : 4.5;
    const r = ratio(fg2, bg);
    if (r < min) {
      const cls = (el.className || '').toString().split(' ').filter(Boolean).slice(0, 2).join('.');
      const key = el.tagName + '.' + cls + '|' + Math.round(r * 100);
      if (seen.has(key)) continue;
      seen.add(key);
      fail.push({
        sel: el.tagName.toLowerCase() + (cls ? '.' + cls : ''),
        ratio: Math.round(r * 100) / 100,
        need: min,
        color: cs.color,
        bg: 'rgb(' + Math.round(bg.r) + ',' + Math.round(bg.g) + ',' + Math.round(bg.b) + ')',
        text: el.textContent.trim().slice(0, 28),
        html: el.outerHTML.slice(0, 150),
      });
    }
    if (fail.length >= 25) break;
  }
  return fail;
}"""


def capture(browser, base_url: str, page_name: str, theme: str, viewport_name: str,
            shot_dir: Path, errors: list[str], full_page: bool) -> dict:
    context = browser.new_context(viewport=VIEWPORTS[viewport_name])
    page = context.new_page()

    found: list[str] = []

    def on_page_error(err):
        found.append(f"[PAGE_ERROR] {page_name}/{theme}/{viewport_name}: {err}")

    def on_console(msg):
        if msg.type != "error":
            return
        if any(b in msg.text for b in BENIGN):
            return
        found.append(f"[CONSOLE_ERROR] {page_name}/{theme}/{viewport_name}: {msg.text}")

    page.on("pageerror", on_page_error)
    page.on("console", on_console)

    info: dict = {"page": page_name, "theme": theme, "viewport": viewport_name}
    url = f"{base_url}/{page_name}"
    try:
        page.goto(url, wait_until="load", timeout=90_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        apply_theme(page, theme)
        time.sleep(0.8)
        info["title"] = page.title()
        info["theme_applied"] = page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')"
        )
        info["body_bg"] = page.evaluate(
            "() => getComputedStyle(document.body).backgroundColor"
        )
        info["body_fg"] = page.evaluate(
            "() => getComputedStyle(document.body).color"
        )
        info["scroll_width"] = page.evaluate("() => document.documentElement.scrollWidth")
        info["overflows_viewport"] = bool(
            page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 2")
        )
        try:
            info["contrast_failures"] = page.evaluate(CONTRAST_JS)
        except Exception as exc:  # noqa: BLE001
            info["contrast_failures"] = [{"error": str(exc)}]
        shot = shot_dir / f"{Path(page_name).stem}_{theme}_{viewport_name}.png"
        page.screenshot(path=str(shot), full_page=full_page)
        info["screenshot"] = shot.name
    except Exception as exc:  # noqa: BLE001 - the audit must survive any page
        found.append(f"[LOAD_ERROR] {page_name}/{theme}/{viewport_name}: {exc}")
    finally:
        context.close()

    errors.extend(found)
    info["errors"] = found
    return info


def functional_checks(browser, base_url: str, shot_dir: Path,
                      errors: list[str]) -> list[str]:
    """Exercise the theme control the way a user does, on a real page.

    The screenshot pass may set `data-theme` directly, so it cannot prove the
    button works. This can: it clicks the control, reloads, and checks that the
    choice survived -- and it proves the chart follows the page theme.
    """
    notes: list[str] = []
    context = browser.new_context(viewport=VIEWPORTS["desktop"])
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(f"[FUNCTIONAL_PAGE_ERROR] {e}"))
    page.on("console", lambda m: errors.append(f"[FUNCTIONAL_CONSOLE] {m.text}")
            if m.type == "error" and not any(b in m.text for b in BENIGN) else None)
    try:
        page.goto(f"{base_url}/index.html", wait_until="load", timeout=90_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        page.evaluate("() => { try { localStorage.removeItem('astra-theme'); } catch (e) {} }")
        page.reload(wait_until="load", timeout=90_000)
        time.sleep(0.5)

        start = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        notes.append(f"theme on first load (no saved choice): {start}")

        btn = page.query_selector("#themeToggleBtn")
        if not btn or not btn.is_visible():
            errors.append("[FUNCTIONAL] #themeToggleBtn is missing or hidden")
        else:
            before = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
            btn.click(timeout=5_000)
            time.sleep(0.5)
            after_theme = page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')")
            after_bg = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
            if after_theme == start:
                errors.append("[FUNCTIONAL] toggling did not change the theme")
            if after_bg == before:
                errors.append("[FUNCTIONAL] toggling did not repaint the page")
            notes.append(f"toggle {start} -> {after_theme}, body {before} -> {after_bg}")

            page.reload(wait_until="load", timeout=90_000)
            time.sleep(0.5)
            persisted = page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')")
            if persisted != after_theme:
                errors.append(
                    f"[FUNCTIONAL] choice did not persist: {persisted} != {after_theme}")
            notes.append(f"after reload: {persisted} (persisted)")

            saved = page.evaluate("() => localStorage.getItem('astra-theme')")
            if saved != after_theme:
                errors.append(f"[FUNCTIONAL] localStorage holds {saved!r}")

        # The chart must follow the page theme.
        # `const D = ...` makes a global lexical binding, not a `window` property.
        sym = page.evaluate(
            "() => (typeof D !== 'undefined' && D.candidates && D.candidates[0])"
            " ? D.candidates[0].symbol : null")
        if sym:
            page.evaluate("(s) => openModal(s)", sym)
            time.sleep(1.4)
            canvases = page.query_selector_all("#stockChartContainer canvas")
            if not canvases:
                errors.append("[FUNCTIONAL] the stock chart rendered no canvas")
            notes.append(f"stock chart '{sym}': {len(canvases)} canvas elements")

            # The canvas must repaint with the page, or the chart lies about
            # the theme it is drawn in.
            def chart_bg() -> str:
                return page.evaluate(
                    "() => (typeof currentStockChartInstance !== 'undefined'"
                    " && currentStockChartInstance)"
                    " ? currentStockChartInstance.options().layout.background.color"
                    " : 'n/a'")

            bg_now = chart_bg()
            other = 'dark' if after_theme == 'light' else 'light'
            page.evaluate("(t) => applyTheme(t, true)", other)
            time.sleep(0.6)
            bg_other = chart_bg()
            if bg_now == bg_other:
                errors.append(
                    f"[FUNCTIONAL] chart background did not follow the theme "
                    f"({bg_now!r} in both)")
            notes.append(f"chart background {after_theme}={bg_now} -> {other}={bg_other}")
            page.evaluate("(t) => applyTheme(t, true)", after_theme)
            time.sleep(0.4)
            shot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot_dir / f"modal_{after_theme}_desktop.png"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"[FUNCTIONAL_ERROR] {exc}")
    finally:
        context.close()
    return notes


def open_stock_modal(browser, base_url: str, shot_dir: Path, errors: list[str]) -> None:
    """Open the chart modal, because the chart is the one themed canvas."""
    context = browser.new_context(viewport=VIEWPORTS["desktop"])
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(f"[MODAL_PAGE_ERROR] {e}"))
    try:
        page.goto(f"{base_url}/index.html", wait_until="load", timeout=90_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        for theme in THEMES:
            apply_theme(page, theme)
            sym = page.evaluate(
                "() => (typeof D !== 'undefined' && D.candidates && D.candidates[0])"
                " ? D.candidates[0].symbol : null")
            if not sym:
                continue
            page.evaluate("(s) => openModal(s)", sym)
            time.sleep(1.4)
            if theme == "dark":
                page.screenshot(path=str(shot_dir / "modal_dark_desktop.png"))
            else:
                page.screenshot(path=str(shot_dir / "modal_light_desktop.png"))
                page.keyboard.press("Escape")
                time.sleep(0.3)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"[MODAL_ERROR] {exc}")
    finally:
        context.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless design audit")
    ap.add_argument("--tag", default="latest")
    ap.add_argument("--dir", default=str(ROOT / "docs"),
                    help="directory to serve (use reports/preview for the fast loop)")
    ap.add_argument("--pages", nargs="*", default=None)
    ap.add_argument("--themes", nargs="*", default=list(THEMES))
    ap.add_argument("--no-mobile", action="store_true")
    ap.add_argument("--full-page", action="store_true")
    ap.add_argument("--outdir", default=str(ROOT / "reports" / "design_audit"))
    args = ap.parse_args()

    global SERVE_DIR
    SERVE_DIR = Path(args.dir).resolve()
    if not SERVE_DIR.exists():
        print(f"no such directory: {SERVE_DIR}")
        return 1

    pages = args.pages or DEFAULT_PAGES
    sizes = ["desktop"] if args.no_mobile else list(VIEWPORTS)
    shot_dir = Path(args.outdir) / args.tag
    shot_dir.mkdir(parents=True, exist_ok=True)

    server = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{PORT}"
    print(f"design audit: {base_url} -> {shot_dir}")

    results: list[dict] = []
    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for page_name in pages:
                for theme in args.themes:
                    for size in sizes:
                        r = capture(browser, base_url, page_name, theme, size,
                                    shot_dir, errors, args.full_page)
                        status = "ok" if not r["errors"] else "ERR"
                        cf = r.get("contrast_failures") or []
                        print(f"  [{status}] {page_name} {theme} {size}"
                              f"  bg={r.get('body_bg')} fg={r.get('body_fg')}"
                              f"  contrast_failures={len(cf)}"
                              f"{'  OVERFLOW' if r.get('overflows_viewport') else ''}")
                        results.append(r)
            open_stock_modal(browser, base_url, shot_dir, errors)
            notes = functional_checks(browser, base_url, shot_dir, errors)
            for n in notes:
                print(f"  functional: {n}")
            browser.close()
    finally:
        server.shutdown()

    summary = {
        "tag": args.tag,
        "pages": pages,
        "themes": args.themes,
        "viewports": sizes,
        "results": results,
        "error_count": len(errors),
        "errors": errors,
    }
    (shot_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("-" * 62)
    worst: list[tuple] = []
    for r in results:
        for f in r.get("contrast_failures") or []:
            if "error" in f:
                continue
            worst.append((f["ratio"], f["need"], r["page"], r["theme"],
                          r["viewport"], f["sel"], f["color"], f["bg"], f["text"],
                          f.get("html", "")))
    worst.sort()
    if worst:
        print(f"contrast: {len(worst)} element/theme combinations below WCAG AA")
        for w in worst[:18]:
            print(f"  {w[0]:>5} (need {w[1]}) {w[3]}/{w[4]} {w[5]:<34} "
                  f"fg={w[6]} bg={w[7]}  {w[9][:110]}")
    else:
        print("contrast: no WCAG AA failures found")
    if errors:
        print(f"FAILED: {len(errors)} console/page error(s)")
        for e in errors[:20]:
            print(f"  - {e}")
        return 1
    print(f"PASSED: {len(results)} captures, 0 errors -> {shot_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

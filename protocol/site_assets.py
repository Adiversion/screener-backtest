"""CSS for the research site, kept out of the renderer.

A large blob of text, not logic. It lives apart from `site_html.py` so the
render and write functions stay reviewable on their own, and apart from
`site_js.py` so neither file approaches the 300-line limit.
"""
from __future__ import annotations

CSS = """
:root{
  --bg:#0d1117; --panel:#161b22; --panel2:#1c2129; --line:#30363d;
  --text:#e6edf3; --muted:#8b949e; --accent:#58a6ff; --good:#3fb950;
  --warn:#d29922; --bad:#f85149; --radius:10px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
header{border-bottom:1px solid var(--line);background:var(--panel);
  padding:18px 20px;position:sticky;top:0;z-index:20}
.wrap{max-width:1100px;margin:0 auto}
h1{margin:0 0 2px;font-size:20px;letter-spacing:-.2px}
h2{font-size:17px;margin:26px 0 10px}
h3{font-size:14px;margin:18px 0 8px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.6px}
.sub{color:var(--muted);font-size:13px}
.tabs{display:flex;gap:6px;margin-top:14px;flex-wrap:wrap}
.tab{background:var(--panel2);border:1px solid var(--line);color:var(--muted);
  padding:7px 14px;border-radius:999px;cursor:pointer;font-size:13px}
.tab.on{background:var(--accent);border-color:var(--accent);color:#04121f;
  font-weight:600}
main{padding:20px}
#q{width:100%;padding:14px 16px;font-size:17px;border-radius:var(--radius);
  border:1px solid var(--line);background:var(--panel);color:var(--text)}
#q:focus{outline:2px solid var(--accent);outline-offset:-1px}
.card{background:var(--panel);border:1px solid var(--line);
  border-radius:var(--radius);padding:16px;margin:14px 0}
.verdict{display:inline-block;padding:5px 12px;border-radius:999px;
  font-weight:700;font-size:12px;letter-spacing:.5px}
.pass{background:rgba(63,185,80,.15);color:var(--good);
  border:1px solid rgba(63,185,80,.4)}
.fail{background:rgba(248,81,73,.13);color:var(--bad);
  border:1px solid rgba(248,81,73,.4)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
  gap:10px;margin:12px 0}
.kpi{background:var(--panel2);border-radius:8px;padding:10px 12px}
.kpi .k{font-size:11px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.5px}
.kpi .v{font-size:17px;font-weight:600;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
th{text-align:left;color:var(--muted);font-weight:600;font-size:11px;
  text-transform:uppercase;letter-spacing:.5px;padding:7px 8px;
  border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid rgba(48,54,61,.5);
  vertical-align:top}
tr:last-child td{border-bottom:none}
.ok{color:var(--good);font-weight:700}
.no{color:var(--bad);font-weight:700}
.bar{height:7px;background:var(--panel2);border-radius:4px;overflow:hidden;
  min-width:70px}
.bar>i{display:block;height:100%;background:var(--accent)}
.sym{font-weight:700;letter-spacing:.3px}
.row{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;
  align-items:baseline}
.pill{font-size:11px;color:var(--muted);border:1px solid var(--line);
  padding:2px 8px;border-radius:999px}
.muted{color:var(--muted)}
.note{font-size:12px;color:var(--muted);margin-top:6px}
.list a{display:block;padding:9px 11px;border:1px solid var(--line);
  border-radius:8px;margin:6px 0;text-decoration:none;color:var(--text);
  background:var(--panel2)}
.list a:hover{border-color:var(--accent)}
code{background:var(--panel2);padding:1px 5px;border-radius:4px;font-size:12px}
footer{padding:26px 20px;color:var(--muted);font-size:12px;
  border-top:1px solid var(--line);margin-top:30px}
.hide{display:none!important}
"""

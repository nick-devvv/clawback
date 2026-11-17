"""Build the site pages from the Claude Design boards.

design/Main.dc.html  -> public/site/landing.html  (served at /)
design/Demo.dc.html  -> public/site/demo.html     (served at /demo, and embedded in the landing page)
design/Live.dc.html  -> public/site/live.html     (served at /live, talks to /api/py)

Each page gets the board's <helmet> in its <head>, its template in <template id="tpl">, its Component script, and
public/site/dc-runtime.js to render it. Board-to-board links become site routes, and the demo embed becomes an iframe.

Run: python3 design/build_site.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {"Main": ("landing", "Clawback · your vendors owe you money", None), "Demo": ("demo", "Clawback · watch it", "1280x800"), "Live": ("live", "Clawback · try it live", None)}
LINKS = {"Main.dc.html": "/", "Demo.dc.html": "/demo", "Live.dc.html": "/live"}
DESCRIPTION = "Clawback finds the uptime credits your vendors owe you, writes the claim, and learns from every reply. Built with Cognee."


def build(name: str) -> str:
    slug, title, fit = PAGES[name]
    src = (ROOT / "design" / f"{name}.dc.html").read_text()
    helmet = re.search(r"<helmet>(.*?)</helmet>", src, re.S).group(1)
    body = re.search(r"<x-dc>(.*?)</x-dc>", src, re.S).group(1)
    body = re.sub(r"<helmet>.*?</helmet>", "", body, flags=re.S)
    m = re.search(r"<script type=\"text/x-dc\" data-dc-script data-props='(.*?)'>(.*?)</script>", src, re.S)
    props_spec, script = json.loads(m.group(1)), m.group(2)
    props = {k: v.get("default") for k, v in props_spec.items() if not k.startswith("$") and isinstance(v, dict)}
    body = re.sub(r'<dc-import name="Demo"[^>]*></dc-import>', '<iframe src="/demo?embed=1" title="Clawback demo, one real claim start to finish" style="width: 1280px; height: 800px; border: 0; display: block; background: transparent" loading="lazy"></iframe>', body)
    for a, b in LINKS.items():
        body = body.replace(f'href="{a}"', f'href="{b}"')
    page_css = "html,body{margin:0;height:100%}" + ("body{overflow:hidden}" if fit else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{DESCRIPTION}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{DESCRIPTION}">
<link rel="icon" href="/site/favicon.svg" type="image/svg+xml">
<style>{page_css}</style>
{helmet}
</head>
<body data-props='{json.dumps(props)}'{f' data-fit="{fit}"' if fit else ''}>
<template id="tpl">{body}</template>
<div id="app"></div>
<script src="/site/dc-runtime.js"></script>
<script>
{script}
window.Component = Component;
window.__dcMount();
</script>
</body>
</html>
"""


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 11 7" shape-rendering="crispEdges"><path d="M0 1h2v1H0zM1 0h1v1H1zM9 0h1v1H9zM9 1h2v1H9zM1 2h1v1H1zM9 2h1v1H9zM3 3h5v1H3zM2 4h7v2H2zM1 6h1v1H1zM3 6h1v1H3zM7 6h1v1H7zM9 6h1v1H9z" fill="#FF6A1F"/><path d="M4 2h1v1H4zM6 2h1v1H6z" fill="#22170F"/></svg>"""

if __name__ == "__main__":
    out = ROOT / "public" / "site"
    out.mkdir(parents=True, exist_ok=True)
    for name, (slug, _, _) in PAGES.items():
        (out / f"{slug}.html").write_text(build(name))
        print("built", f"public/site/{slug}.html")
    (out / "favicon.svg").write_text(FAVICON)

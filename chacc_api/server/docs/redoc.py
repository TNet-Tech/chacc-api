from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

_REDOC_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.io/redoc@latest/bundles/redoc.standalone.css">
    <style>
    html, body, .redoc-wrap, .redoc {
      background: var(--chacc-navy) !important;
      color: var(--chacc-text) !important;
    }
    {css}
    </style>
</head>
<body>
    <redoc spec-url="{openapi_url}" hide-download-button></redoc>
    <script src="https://unpkg.io/redoc@latest/bundles/redoc.standalone.js"></script>
</body>
</html>
"""


def get_themed_redoc_html(request: Request, app_title: str) -> HTMLResponse:
    css_path = Path(__file__).resolve().parent / "css" / "redoc.css"
    css = css_path.read_text(encoding="utf-8")
    html = _REDOC_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    html = html.replace("{css}", css)
    return HTMLResponse(content=html)

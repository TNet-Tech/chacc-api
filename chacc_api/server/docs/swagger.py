from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.io/swagger-ui-dist@5/swagger-ui.css">
    <style>
    {css}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.io/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.io/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
    window.onload = function() {
        const ui = SwaggerUIBundle({
            url: "{openapi_url}",
            dom_id: '#swagger-ui',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIStandalonePreset
            ],
            layout: "StandaloneLayout",
            deepLinking: true,
            tryItOutEnabled: true,
            persistAuthorization: true,
        });
    };
    </script>
</body>
</html>
"""


def get_themed_swagger_ui_html(request: Request, app_title: str) -> HTMLResponse:
    css_path = Path(__file__).resolve().parent / "css" / "swagger.css"
    css = css_path.read_text(encoding="utf-8")
    html = _SWAGGER_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    html = html.replace("{css}", css)
    return HTMLResponse(content=html)

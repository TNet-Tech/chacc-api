from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.io/swagger-ui-dist@5.17.14/swagger-ui.css">
    <style>
    {extra_css}
    {css}
    </style>
</head>
<body>
    <div id="chacc-loader">
        <div class="loader-content">
            <img src="{logo_data_uri}" alt="ChaCC" class="loader-logo">
            <div class="loader-ring"></div>
        </div>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.io/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.io/swagger-ui-dist@5.17.14/swagger-ui-standalone-preset.js"></script>
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
            onComplete: function() {
                const defaultLoader = document.querySelector('.swagger-ui .loading-container');
                if (defaultLoader) {
                    defaultLoader.remove();
                }
                const loader = document.getElementById('chacc-loader');
                if (loader) {
                    loader.classList.add('hidden');
                    setTimeout(() => loader.remove(), 500);
                }
                const topbarWrapper = document.querySelector('.swagger-ui .topbar .topbar-wrapper');
                if (topbarWrapper) {
                    const logo = document.createElement('div');
                    logo.className = 'chacc-docs-logo';
                    logo.innerHTML = '<img src="{logo_data_uri}" alt="ChaCC">';
                    topbarWrapper.insertBefore(logo, topbarWrapper.firstChild);
                }
            }
        });
    };
    </script>
</body>
</html>
"""


def get_themed_swagger_ui_html(
    request: Request, app_title: str, logo_data_uri: str = ""
) -> HTMLResponse:
    css_path = Path(__file__).resolve().parent / "css" / "swagger.css"
    css = css_path.read_text(encoding="utf-8")

    extra_css = """
    #chacc-loader {
        position: fixed;
        inset: 0;
        background: #1A242B;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        transition: opacity 0.5s ease, visibility 0.5s ease;
    }
    #chacc-loader.hidden {
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
    }
    .loader-content {
        position: relative;
        width: 80px;
        height: 80px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .loader-logo {
        width: 36px;
        height: auto;
        position: relative;
        z-index: 2;
    }
    .loader-logo[src=""] {
        display: none;
    }
    .loader-ring {
        position: absolute;
        width: 80px;
        height: 80px;
        border: 3px solid rgba(0, 210, 211, 0.2);
        border-top-color: #00D2D3;
        border-radius: 50%;
        animation: chacc-spin 1s linear infinite;
    }
    @keyframes chacc-spin {
        to { transform: rotate(360deg); }
    }
    .chacc-docs-logo {
        display: inline-flex;
        align-items: center;
        margin-right: 12px;
        height: 40px;
    }
    .chacc-docs-logo img {
        height: 72px;
        width: auto;
    }
    .swagger-ui .topbar {
        padding-left: 48px !important;
    }
    .swagger-ui .loading-container {
        display: none !important;
    }
    """

    html = _SWAGGER_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    html = html.replace("{logo_data_uri}", logo_data_uri)
    html = html.replace("{extra_css}", extra_css)
    html = html.replace("{css}", css)
    return HTMLResponse(content=html)

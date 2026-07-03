from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

_REDOC_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.io/redoc@2.1.3/bundles/redoc.standalone.css">
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
    <redoc spec-url="{openapi_url}" hide-download-button></redoc>
    <script src="https://unpkg.io/redoc@2.1.3/bundles/redoc.standalone.js"></script>
    <script>
    (function() {
        const loader = document.getElementById('chacc-loader');
        let logoInjected = false;

        function hideLoader() {
            if (loader && !logoInjected) {
                logoInjected = true;
                loader.classList.add('hidden');
                setTimeout(() => loader.remove(), 500);
            }
        }

        function injectLogo() {
            const header = document.querySelector('.redoc .header, .rdoc .rdoc__header');
            if (header && !header.querySelector('.chacc-docs-logo')) {
                const logo = document.createElement('div');
                logo.className = 'chacc-docs-logo';
                logo.innerHTML = '<img src="{logo_data_uri}" alt="ChaCC">';
                header.insertBefore(logo, header.firstChild);
                hideLoader();
                return true;
            }
            return false;
        }

        let attempts = 0;
        const maxAttempts = 20;
        const interval = setInterval(() => {
            attempts += 1;
            if (injectLogo() || attempts >= maxAttempts) {
                clearInterval(interval);
                if (!logoInjected) hideLoader();
            }
        }, 300);

        window.addEventListener('load', () => {
            setTimeout(() => {
                injectLogo();
                if (!logoInjected) hideLoader();
                clearInterval(interval);
            }, 1500);
        });
    })();
    </script>
</body>
</html>
"""


def get_themed_redoc_html(request: Request, app_title: str, logo_data_uri: str = "") -> HTMLResponse:
    css_path = Path(__file__).resolve().parent / "css" / "redoc.css"
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
        height: 36px;
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
        height: 28px;
        width: auto;
    }
    .redoc .header,
    .rdoc .rdoc__header {
        padding-left: 48px !important;
    }
    .redoc .loading-container,
    .redoc .loader,
    .redoc [class*="loading"],
    .redoc [class*="spinner"],
    .rdoc [class*="loading"],
    .rdoc [class*="spinner"] {
        display: none !important;
    }
    html, body {
        margin: 0 !important;
        padding: 0 !important;
        background: #1A242B !important;
        height: 100% !important;
    }
    .redoc-wrap, .redoc, .rdoc, .rdoc-wrap {
        height: 100vh !important;
        border: none !important;
    }
    """

    html = _REDOC_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    html = html.replace("{logo_data_uri}", logo_data_uri)
    html = html.replace("{extra_css}", extra_css)
    html = html.replace("{css}", css)
    return HTMLResponse(content=html)

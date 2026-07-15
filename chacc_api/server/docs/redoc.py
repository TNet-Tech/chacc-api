from fastapi import Request
from fastapi.responses import HTMLResponse

_REDOC_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.io/redoc@2.1.3/bundles/redoc.standalone.css">
    <link rel="stylesheet" href="/static/css/redoc.css">
    <link rel="stylesheet" href="/static/css/redoc-extra.css">
</head>
<body>
    <div id="chacc-loader">
        <div class="loader-content">
            <img src="/static/img/chacc-icon.ico" alt="ChaCC" class="loader-logo">
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
                logo.innerHTML = '<img src="/static/img/chacc-icon.ico" alt="ChaCC">';
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


def get_themed_redoc_html(request: Request, app_title: str) -> HTMLResponse:
    html = _REDOC_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    return HTMLResponse(content=html)

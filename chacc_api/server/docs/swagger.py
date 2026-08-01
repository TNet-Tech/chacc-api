from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.io/swagger-ui-dist@5.17.14/swagger-ui.css">
    <link rel="stylesheet" href="/static/css/swagger.css">
    <link rel="stylesheet" href="/static/css/swagger-extra.css">
</head>
<body>
    <div id="chacc-loader">
        <div class="loader-content">
            <img src="/static/img/chacc-icon.ico" alt="ChaCC" class="loader-logo">
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
                    logo.innerHTML = '<img src="/static/img/chacc-icon.ico" alt="ChaCC">';
                    topbarWrapper.insertBefore(logo, topbarWrapper.firstChild);
                }
            }
        });
    };
    </script>
</body>
</html>
"""


def get_themed_swagger_ui_html(request: Request, app_title: str) -> HTMLResponse:
    html = _SWAGGER_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    return HTMLResponse(content=html)


def _fix_binary_file_schemas(node: object) -> None:
    """Recursively rewrite OpenAPI 3.1 binary-file schemas to the legacy binary form.

    FastAPI/Pydantic emit `{"type": "string", "contentMediaType": "..."}` for
    `UploadFile` fields under OpenAPI 3.1, but swagger-ui-dist@5 only renders a
    file-picker widget for the OpenAPI 3.0-style `{"type": "string", "format": "binary"}`.
    Without this, every file-upload endpoint needs a hand-written `openapi_extra`
    override just to get a working file input in the UI.
    """
    if isinstance(node, dict):
        if node.get("type") == "string" and "contentMediaType" in node:
            node.pop("contentMediaType", None)
            node.pop("contentEncoding", None)
            node["format"] = "binary"
        for value in node.values():
            _fix_binary_file_schemas(value)
    elif isinstance(node, list):
        for item in node:
            _fix_binary_file_schemas(item)


def patch_binary_file_schema(app: FastAPI) -> None:
    """Install a custom openapi() on `app` so file-upload fields render correctly.

    Call this once, right after creating the FastAPI app. After this, plain
    `file: UploadFile = File(...)` parameters get a working Swagger UI file
    picker with no per-endpoint `openapi_extra` boilerplate required.
    """

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        _fix_binary_file_schemas(schema)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi

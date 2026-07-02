"""
Custom themed docs pages for Swagger UI and ReDoc.
Uses CDN resources with ChaCC dark-mode CSS injected directly.
"""
from fastapi import Request
from fastapi.responses import HTMLResponse


SWAGGER_UI_CSS = """
/* === ChaCC dark theme for Swagger UI === */
:root {
  --chacc-teal: #00D2D3;
  --chacc-navy: #1A242B;
  --chacc-text: #F2F5F8;
  --chacc-card: #253038;
  --chacc-border: rgba(0, 210, 211, 0.24);
  --chacc-danger: #e74c3c;
}

html, body {
  background: var(--chacc-navy) !important;
  color: var(--chacc-text) !important;
}

.swagger-ui {
  background: var(--chacc-navy) !important;
  color: var(--chacc-text) !important;
}

/* Top navigation bar */
.swagger-ui .topbar {
  background: var(--chacc-navy) !important;
  border-bottom: 1px solid var(--chacc-border) !important;
}

.swagger-ui .topbar .download-url-wrapper,
.swagger-ui .topbar a.link,
.swagger-ui .topbar .link {
  color: var(--chacc-text) !important;
}

.swagger-ui .topbar .download-url-wrapper input[type="text"] {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: var(--chacc-border) !important;
  color: var(--chacc-text) !important;
}

/* Info section */
.swagger-ui .info {
  background: var(--chacc-card) !important;
  border: 1px solid var(--chacc-border) !important;
  border-radius: 8px !important;
}

.swagger-ui .info .title,
.swagger-ui .info h1,
.swagger-ui .info h2,
.swagger-ui .info h3,
.swagger-ui .info h4,
.swagger-ui .info h5 {
  color: var(--chacc-teal) !important;
}

.swagger-ui .info p,
.swagger-ui .info table {
  color: var(--chacc-text) !important;
}

/* Operation tags and summaries */
.swagger-ui .opblock-tag,
.swagger-ui .opblock .opblock-summary {
  background: var(--chacc-card) !important;
  border-color: var(--chacc-border) !important;
  color: var(--chacc-text) !important;
}

.swagger-ui .opblock-tag:hover,
.swagger-ui .opblock .opblock-summary:hover {
  background: rgba(0, 210, 211, 0.08) !important;
}

.swagger-ui .opblock .opblock-summary-description,
.swagger-ui .opblock .opblock-summary-path,
.swagger-ui .opblock .opblock-summary-method {
  color: var(--chacc-text) !important;
}

.swagger-ui .opblock-description-wrapper,
.swagger-ui .opblock-external-docs-wrapper,
.swagger-ui .opblock-body {
  background: var(--chacc-card) !important;
  border-color: var(--chacc-border) !important;
}

/* Model boxes */
.swagger-ui .model-box {
  background: var(--chacc-card) !important;
  border-color: var(--chacc-border) !important;
}

.swagger-ui .model-title {
  color: var(--chacc-teal) !important;
}

.swagger-ui .model .model-box {
  color: var(--chacc-text) !important;
}

/* Tables */
.swagger-ui table thead tr th,
.swagger-ui table thead tr td {
  background: rgba(0, 210, 211, 0.08) !important;
  color: var(--chacc-teal) !important;
  border-color: var(--chacc-border) !important;
}

.swagger-ui table tbody tr td {
  border-color: var(--chacc-border) !important;
  color: var(--chacc-text) !important;
}

/* Scheme container */
.swagger-ui .scheme-container {
  background: var(--chacc-card) !important;
  border-color: var(--chacc-border) !important;
}

/* Buttons */
.swagger-ui .btn {
  background: transparent !important;
  border: 1px solid var(--chacc-teal) !important;
  color: var(--chacc-teal) !important;
  text-shadow: none !important;
  box-shadow: none !important;
}

.swagger-ui .btn:hover {
  background: var(--chacc-teal) !important;
  color: #ffffff !important;
}

.swagger-ui .btn.cancel {
  border-color: var(--chacc-danger) !important;
  color: var(--chacc-danger) !important;
  background: transparent !important;
}

.swagger-ui .btn.cancel:hover {
  background: var(--chacc-danger) !important;
  color: #ffffff !important;
}

.swagger-ui .execute-btn {
  border-color: var(--chacc-teal) !important;
  color: var(--chacc-teal) !important;
  background: transparent !important;
}

.swagger-ui .execute-btn:hover {
  background: var(--chacc-teal) !important;
  color: #ffffff !important;
}

.swagger-ui .authorize__btn {
  border-color: var(--chacc-teal) !important;
  color: var(--chacc-teal) !important;
  background: transparent !important;
}

.swagger-ui .authorize__btn:hover {
  background: var(--chacc-teal) !important;
  color: #ffffff !important;
}

/* Response section */
.swagger-ui .response-col_description {
  color: var(--chacc-text) !important;
}

.swagger-ui .response-control-media-type__title {
  color: var(--chacc-teal) !important;
}

.swagger-ui .response-col_links .operation-link {
  color: var(--chacc-teal) !important;
}

/* Tabs */
.swagger-ui .tab li {
  color: var(--chacc-text) !important;
  border-color: var(--chacc-border) !important;
}

.swagger-ui .tab li.active {
  background: rgba(0, 210, 211, 0.08) !important;
  border-color: var(--chacc-teal) !important;
  color: var(--chacc-teal) !important;
}

/* Code blocks */
.swagger-ui .opblock-body pre {
  background: rgba(0, 0, 0, 0.3) !important;
  color: var(--chacc-text) !important;
  border-color: var(--chacc-border) !important;
}

.swagger-ui .markdown p,
.swagger-ui .markdown code,
.swagger-ui .markdown pre {
  color: var(--chacc-text) !important;
}

/* Inputs and selects */
.swagger-ui input[type="text"],
.swagger-ui input[type="password"],
.swagger-ui input[type="email"] {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: var(--chacc-border) !important;
  color: var(--chacc-text) !important;
}

.swagger-ui .select {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: var(--chacc-border) !important;
  color: var(--chacc-text) !important;
}

/* Model content */
.swagger-ui .model-box .model-box__model {
  color: var(--chacc-text) !important;
}

.swagger-ui .model .model-toggle {
  filter: invert(1);
}

.swagger-ui .parameters-col_description p,
.swagger-ui .parameters-col_description .model {
  color: var(--chacc-text) !important;
}

/* Loader */
.swagger-ui .loading-container {
  background: var(--chacc-navy) !important;
}

.swagger-ui .loading-container .throbber .rotator,
.swagger-ui .loading-container .throbber:before,
.swagger-ui .loading-container .throbber:after {
  background: var(--chacc-teal) !important;
}
"""

_REDOC_CSS = """
/* === ChaCC dark theme for ReDoc - Improved & Clean === */
:root {
  --chacc-teal: #00D2D3;
  --chacc-navy: #1A242B;
  --chacc-text: #F2F5F8;
  --chacc-card: #253038;
  --chacc-border: rgba(0, 210, 211, 0.24);
  --chacc-danger: #e74c3c;
}

html, body, .redoc-wrap, .redoc {
  background: var(--chacc-navy) !important;
  color: var(--chacc-text) !important;
}

/* Header */
.redoc .header,
.redoc .top-bar,
.redoc .topbar {
  background: var(--chacc-navy) !important;
  border-bottom: 1px solid var(--chacc-border) !important;
}

.redoc .header .logo img,
.redoc .top-bar .logo img {
  filter: brightness(0) invert(1);
}

/* Main content */
.redoc .api-info,
.redoc .introduction,
.redoc .section {
  background: var(--chacc-card) !important;
  border-bottom: 1px solid var(--chacc-border) !important;
  color: var(--chacc-text) !important;
}

/* Headings & Titles - Teal */
.redoc h1,
.redoc h2,
.redoc h3,
.redoc h4,
.redoc h5,
.redoc .title,
.redoc .api-info .title,
.redoc .section-title,
.redoc .operation-summary .title {
  color: var(--chacc-teal) !important;
}

/* Sidebar */
.redoc .menu-content,
.redoc .sidebar,
.redoc .nav,
.redoc .redoc-sidebar,
.redoc aside {
  background: var(--chacc-navy) !important;
  color: var(--chacc-text) !important;
  border-right: 1px solid var(--chacc-border) !important;
}

/* Sidebar items */
.redoc .menu-item,
.redoc .menu-item a,
.redoc .sidebar a,
.redoc .nav a,
.redoc .menu-item-link {
  color: var(--chacc-text) !important;
}

.redoc .menu-item.active,
.redoc .menu-item:hover,
.redoc .menu-item.active a,
.redoc .menu-item:hover a {
  background: rgba(0, 210, 211, 0.12) !important;
  color: var(--chacc-teal) !important;
}

.redoc .menu-item-section,
.redoc .menu-section-title {
  color: var(--chacc-teal) !important;
}

/* HTTP Methods & Tags */
.redoc .http-verb,
.redoc .method,
.redoc .operation-tag {
  color: var(--chacc-teal) !important;
  font-weight: 600;
}

/* Operation cards */
.redoc .operation-summary {
  background: var(--chacc-card) !important;
  border-color: var(--chacc-border) !important;
}

/* Code / Examples */
.redoc code,
.redoc pre,
.redoc .example,
.redoc .request-content,
.redoc .response-content {
  background: rgba(0, 0, 0, 0.35) !important;
  color: var(--chacc-text) !important;
  border-color: var(--chacc-border) !important;
}

.redoc .highlight code {
  color: #a5f3fc !important; /* light cyan for code */
}

/* Tables */
.redoc table thead tr th,
.redoc table thead tr td {
  background: rgba(0, 210, 211, 0.1) !important;
  color: var(--chacc-teal) !important;
  border-color: var(--chacc-border) !important;
}

.redoc table tbody tr td {
  color: var(--chacc-text) !important;
  border-color: var(--chacc-border) !important;
}

/* Models / Schemas */
.redoc .model-box {
  background: var(--chacc-card) !important;
  border-color: var(--chacc-border) !important;
}

.redoc .model-title,
.redoc .prop-type,
.redoc .schema__title {
  color: var(--chacc-teal) !important;
}

.redoc .prop-name,
.redoc .schema__property-name,
.redoc .model .property {
  color: var(--chacc-text) !important;
}

/* Links */
.redoc a,
.redoc .source-link {
  color: var(--chacc-teal) !important;
}

.redoc a:hover {
  color: #67f8f9 !important;
}

/* Inputs & Search */
.redoc input[type="text"],
.redoc input[type="search"],
.redoc .search-wrapper,
.redoc .search-input {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: var(--chacc-border) !important;
  color: var(--chacc-text) !important;
}

/* Buttons */
.redoc .btn,
.redoc button,
.redoc .redoc-btn {
  background: transparent !important;
  border: 1px solid var(--chacc-teal) !important;
  color: var(--chacc-teal) !important;
}

.redoc .btn:hover,
.redoc button:hover,
.redoc .redoc-btn:hover {
  background: var(--chacc-teal) !important;
  color: #ffffff !important;
}

.redoc .btn-danger,
.redoc .redoc-btn.btn-danger {
  border-color: var(--chacc-danger) !important;
  color: var(--chacc-danger) !important;
}

.redoc .btn-danger:hover {
  background: var(--chacc-danger) !important;
  color: #ffffff !important;
}

/* Tabs */
.redoc .tab,
.redoc .tab__item,
.redoc .tab-link {
  color: var(--chacc-text) !important;
}

.redoc .tab.active,
.redoc .tab__item.active,
.redoc .tab-link.active {
  color: var(--chacc-teal) !important;
  border-color: var(--chacc-teal) !important;
}

/* Scrollbar */
.redoc ::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.redoc ::-webkit-scrollbar-track {
  background: var(--chacc-navy);
}
.redoc ::-webkit-scrollbar-thumb {
  background: var(--chacc-border);
  border-radius: 4px;
}
.redoc ::-webkit-scrollbar-thumb:hover {
  background: var(--chacc-teal);
}

/* Strong force overrides for any missed white elements */
.redoc * {
  color: var(--chacc-text) !important;
}

.redoc h1, .redoc h2, .redoc h3, 
.redoc .title, .redoc .operation-summary .title,
.redoc .http-verb, .redoc .method,
.redoc .model-title, .redoc .prop-type {
  color: var(--chacc-teal) !important;
}
"""

_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChaCC API Backbone</title>
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

_REDOC_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChaCC API Backbone</title>
    <link rel="stylesheet" href="https://unpkg.io/redoc@latest/bundles/redoc.standalone.css">
    <style>
    html, body {
      background: var(--chacc-navy) !important;
      color: var(--chacc-text) !important;
    }
    {css}
    </style>
</head>
<body>
    <redoc spec-url="{openapi_url}"></redoc>
    <script src="https://unpkg.io/redoc@latest/bundles/redoc.standalone.js"></script>
</body>
</html>
"""

def get_themed_swagger_ui_html(request: Request, app_title: str) -> HTMLResponse:
    html = _SWAGGER_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    html = html.replace("{css}", SWAGGER_UI_CSS)
    return HTMLResponse(content=html)


def get_themed_redoc_html(request: Request, app_title: str) -> HTMLResponse:
    html = _REDOC_HTML.replace("{title}", app_title)
    html = html.replace("{openapi_url}", request.app.openapi_url)
    html = html.replace("{css}", _REDOC_CSS)
    return HTMLResponse(content=html)

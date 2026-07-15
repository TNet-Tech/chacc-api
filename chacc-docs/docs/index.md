<div class="hero">
  <div class="hero__badge">Plug &amp; Play API </div>
  <h1>Plug APIs like apps with <span>ChaCC API</span>.</h1>
  <p>
    Stop building the same API logic for every project. Build or Download a Python module, install it, and get a working API instantly.
    ChaCC handles the runtime, database, migrations, dependencies, CLI, and deployment.
  </p>
  <div class="hero__actions">
    <a class="md-button" href="overview/">Explore the platform</a>
    <a class="md-button" href="installation/">Start quickly</a>
    <a class="md-button" href="core-api/">View core endpoints</a>
  </div>
</div>

<div class="feature-grid">
  <article class="card">
    <h3>Pluggable modules</h3>
    <p>
      Package feature sets as <code>.chacc</code> archives, install them into the
      backbone, and mount their FastAPI routers with their own prefix and tags.
    </p>
  </article>
  <article class="card">
    <h3>Database-first</h3>
    <p>
      Models use <code>ChaCCBaseModel</code> with UUID, timestamps, soft-delete
      fields, and automatic registration through <code>ChaCCBaseModel</code>.
    </p>
  </article>
  <article class="card">
    <h3>Safe migrations</h3>
    <p>
      Startup migrations compare model metadata with the database, track applied
      operations, and support preview, safe auto, and full modes.
    </p>
  </article>
</div>

<div class="api-strip">
  <article class="card">
    <h3>Developer workflow</h3>
    <ol>
      <li>Create a module with <code>chacc create my_module</code>.</li>
      <li>Add models, routes, services, and tests inside the scaffold.</li>
      <li>Run the backbone in development mode with <code>chacc run server --dev</code>.</li>
      <li>Build and deploy the module as a <code>.chacc</code> package.</li>
    </ol>
  </article>
  <div class="code-card">
    <h3>Quick Guide Test run</h3>
    
    ```bash
    pip install chacc-api
    chacc create billing
    chacc run server --dev
    chacc build plugins/billing
    chacc deploy billing.chacc
    ```
  </div>
</div>

## Documentation structure

### Getting Started

- [Overview](overview.md) - Platform concepts and architecture

### Guides

- [Installation](installation.md) - Quick setup guide
- [Configuration](configuration.md) - Environment setup
- [Core API](core-api.md) - Built-in endpoints
- [Database and Migrations](database-migrations.md) - Data layer
- [CLI](cli.md) - Command reference
- [Deployment](deployment.md) - Production deployment

### Development

- [Modules](modules.md) - Building plugins
- [Available Modules](official-modules/index.md) - Official plugins

### Useful Information

- [Troubleshooting](troubleshooting.md) - Common issues
- [Changelog](changelog.md) - Release notes

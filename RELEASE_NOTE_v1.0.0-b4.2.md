# ChaCC API v1.0.0-b4.2 Release Notes

**Release Date:** 2026-07-02  
**Type:** Beta Patch

---

We're excited to announce the latest beta patch for ChaCC API! This release brings a polished dark‑mode welcome page, a more robust model discovery system, and safer, more reliable migrations. Several critical startup bugs have been squashed, making development and production startups smoother than ever.

---

## What's New

- **Dark‑Mode Welcome Page & Themed Docs** – The root endpoint (`/`) now serves an elegant, dark‑themed landing page featuring the ChaCC teal/navy palette, the project logo, and quick links to Swagger UI, ReDoc, and the chacc.dev documentation.  
- **Simplified Model Discovery** – Plugin models are now automatically discovered via SQLAlchemy’s declarative metadata. The manual `@register_model` decorator is no longer required – just inherit from `ChaCCBaseModel`.  
- **Safer Migration Handling** – A new dependency resolver and operation executor centralise migration logic. They handle PostgreSQL enum conflicts, validate table dependencies before applying foreign keys, and prevent spurious synthetic migrations on SQLite.

---

## Bug Fixes

- Fixed a startup crash caused by `Multiple classes found for path "User"` errors when `PLUGIN_AUTO_DISCOVERY=False` in development mode.  
- Removed the legacy `_model_registry` mechanism, eliminating duplicate table registration errors. Model discovery now relies exclusively on SQLAlchemy’s metadata.  
- Corrected SQLite `table_exists()` behaviour so that existing tables are properly recognised, preventing unnecessary synthetic `add_table` migrations.  
- Resolved a chicken‑and‑egg problem with audit schema initialisation: audit fields are now applied correctly regardless of service registration order via two idempotent passes.  
- When a module fails to load, it is now marked as disabled in the database – preventing repeated crash loops on restart.  
- Fixed crashes in route logging when module entry‑points had `None` paths or methods.

---

## Changed

- **Unified Startup Sequence** – Development and production modes now share the same loading pipeline: discover models → initialise database → run migrations → load entry points → apply deferred schema changes → optional follow‑up migration.  
- **Database Initialisation** – `initialize_database_models()` now discovers tables by enumerating `ChaCCBaseModel` subclasses, rather than iterating a removed registry.  
- **Backward Compatibility** – The old `register_model()` decorator is retained as a no‑op shim, so existing module code continues to work during the transition.

---

## Removed


---

## Upgrade Notes

- **Module Authors:** Remove any `@register_model` decorators from your model classes. Inherit from `ChaCCBaseModel` as before – the system now discovers models automatically via SQLAlchemy’s declarative metadata.  
- **Import Prefixes:** Ensure intra‑module imports use the bare module prefix (e.g., `from chacc_authentication.module.models.user import User`). Mixing `plugins.chacc_authentication` and bare prefixes can trigger duplicate‑class‑resolution errors.  
- **Fresh Start Recommended:** If you encountered the startup crash or migration errors in a previous beta, we strongly recommend running migrations fresh after upgrading.

---

## Verify the Update

Start the server with `chacc run server` and visit `http://localhost:8085/` to see the new welcome page in action.

---

*For a complete list of changes, please see the [CHANGELOG.md](https://chacc.dev/changelog/).*
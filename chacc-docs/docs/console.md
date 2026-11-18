# Web Console

The web console is a page for managing a running server. Open `/console`, for
example `http://localhost:8085/console`.

When the authentication module is loaded, the console asks you to log in. The
login lasts until you close the browser tab.

## Modules

![The Modules tab: install area, filter and the module list](assets/img/console-modules.png)

To install a module, drag its `.chacc` file onto the install area, or click it to
choose the file. Build the file with [`chacc build`](cli.md#build-a-module).

**Status** shows whether a module is on:

| Status | Meaning |
| --- | --- |
| Enabled | On. |
| Disabled | Off. |
| Failed to load | Turned off because it failed to start. Open its details to see why. |
| Not loaded | On, but a module it requires isn't installed. |

In **Depends on**, optional modules are in italics, and a module that isn't
installed is marked.

The **⋮** button on each row opens the module's actions:

![The row menu: Details, Disable, Uninstall](assets/img/console-row-menu.png)

Installing, enabling, disabling and uninstalling take effect after a restart. The
console then reminds you to restart. See [Restart the server](#restart-the-server).

## Module details

Click a module's name, or choose **Details** in its menu.

![Details of a running module, with its routes open](assets/img/console-module-details.png)

The popup shows:

- **State**, for example how many routes the module serves and where.
- **Facts** from `module_meta.json`: license, links, the modules it requires and
  the modules that use it, and the ChaCC version it needs.
- **Routes**, **Python packages** (with the installed versions), **Archive**
  (file, size and SHA-256) and **README**.

The README is shown as formatted Markdown, and `mermaid` code blocks are drawn as
diagrams. See [Module layout](modules.md#module-layout) for what module authors
can use.

![A module's README with a Mermaid diagram and a table](assets/img/console-module-readme.png)

When a module fails to start, its details say why:

![A module that failed to load, with the reason](assets/img/console-module-failed.png)

In production the module stays off. Fix the problem, then enable it and restart.
The reason is kept across restarts until the module loads.

To share a module's details, use the link `/console#module=<name>`.

## Dependency graph

![The dependency graph: modules, their dependencies and the load order](assets/img/console-dependencies.png)

Each module is a box. Arrows point from a module to the modules it depends on;
dashed arrows are optional dependencies. A module that can't load is red, with
the reason and how to fix it below the graph. **Load order** is the order the
server loads the modules in.

## Services

The **Services** tab checks the database, Redis, rate limiting and the server.
It checks again every 30 seconds while the console is open, or when you click
**Check again**.

![Services with Redis unreachable](assets/img/console-services-problem.png)

When a service is not working, or working with a fallback (**Limited**), the tab
shows a count and the top bar names the problem. Click the top bar to open the
tab. **Error details** has the original error. Passwords are never shown.

The same checks are available as [`GET /api/system/services`](core-api.md#service-status).

## Restart the server

**Restart server** in the top bar restarts the server and waits until it's back.
It needs the server to be started with `chacc run server`, and is off in
development mode, where the server reloads by itself. See
[Automatic Restarts](server-restarts.md).

## Development mode

In development mode the server loads modules from `plugins/`, while the module
list shows the modules installed in the database. The dependency graph shows
the modules in `plugins/`.

/*
 * ChaCC module console.
 *
 * Talks to the core API: GET/POST/DELETE {prefix}/modules..., GET {prefix}/modules/graph
 * and POST {prefix}/system/restart. When the authentication module is loaded these
 * return 401 without a token; the console then shows a login dialog, stores the
 * token for this browser tab only (sessionStorage) and retries the request.
 */
(function () {
    'use strict';

    const API_PREFIX = (function () {
        const meta = document.querySelector('meta[name="chacc-api-prefix"]');
        const value = meta ? meta.content : '/api';
        return value.includes('{{') ? '/api' : value.replace(/\/+$/, '');
    })();

    const TOKEN_KEY = 'chacc_console_token';
    const PENDING_KEY = 'chacc_console_pending_boot';
    const RESTART_TIMEOUT_MS = 120000;

    const $ = (sel) => document.querySelector(sel);
    const state = {
        info: null,          // /.well-known/chacc
        modules: [],
        graph: null,
        filter: '',
        restarting: false,
        loaded: false,
    };

    // ---------- small helpers ----------

    function el(tag, attrs, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs || {})) {
            if (value === null || value === undefined || value === false) continue;
            if (key === 'class') node.className = value;
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else node.setAttribute(key, value === true ? '' : value);
        }
        for (const child of children.flat()) {
            if (child === null || child === undefined || child === false) continue;
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        }
        return node;
    }

    function svg(tag, attrs, ...children) {
        const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
        for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
        for (const child of children.flat()) {
            if (child === null || child === undefined) continue;
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        }
        return node;
    }

    const storage = {
        get(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } },
        set(key, value) { try { sessionStorage.setItem(key, value); } catch (e) { /* ignore */ } },
        remove(key) { try { sessionStorage.removeItem(key); } catch (e) { /* ignore */ } },
    };

    function toast(message, kind) {
        const node = el('div', { class: 'toast' + (kind ? ' toast-' + kind : ''), role: kind === 'error' ? 'alert' : 'status' }, message);
        $('#toasts').append(node);
        setTimeout(() => node.remove(), kind === 'error' ? 9000 : 6000);
    }

    function detailText(data, fallback) {
        if (!data) return fallback;
        const detail = data.detail;
        if (typeof detail === 'string') return detail;
        if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('\n');
        return data.message || fallback;
    }

    class ApiError extends Error {
        constructor(status, data, message) {
            super(message);
            this.status = status;
            this.data = data;
        }
    }

    // ---------- auth ----------

    let loginPromise = null;

    function login() {
        if (loginPromise) return loginPromise;
        const dialog = $('#login-dialog');
        const form = $('#login-form');
        const error = $('#login-error');
        form.reset();
        const knownLogin = state.info && state.info.auth && state.info.auth.login_path;
        error.textContent = 'The server requires a login but no login endpoint is loaded. '
            + 'Check the server log: the authentication module may have failed to start.';
        error.hidden = Boolean(knownLogin);

        loginPromise = new Promise((resolve, reject) => {
            async function onSubmit(event) {
                event.preventDefault();
                const loginPath = state.info && state.info.auth && state.info.auth.login_path;
                if (!loginPath) {
                    error.textContent = 'The server did not report a login endpoint.';
                    error.hidden = false;
                    return;
                }
                const submit = $('#login-submit');
                submit.disabled = true;
                try {
                    const res = await fetch(loginPath, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username: form.username.value, password: form.password.value }),
                    });
                    const data = await res.json().catch(() => null);
                    if (!res.ok || !data || !data.access_token) {
                        throw new Error(detailText(data, 'Login failed (' + res.status + ').'));
                    }
                    storage.set(TOKEN_KEY, data.access_token);
                    cleanup();
                    dialog.close();
                    updateAuthUi();
                    resolve();
                } catch (e) {
                    error.textContent = e.message;
                    error.hidden = false;
                } finally {
                    submit.disabled = false;
                }
            }
            function onCancel(event) {
                if (event) event.preventDefault();
                cleanup();
                dialog.close();
                reject(new ApiError(401, null, 'Login cancelled.'));
            }
            function cleanup() {
                form.removeEventListener('submit', onSubmit);
                $('#login-cancel').removeEventListener('click', onCancel);
                dialog.removeEventListener('cancel', onCancel);
                loginPromise = null;
            }
            form.addEventListener('submit', onSubmit);
            $('#login-cancel').addEventListener('click', onCancel);
            dialog.addEventListener('cancel', onCancel);
            dialog.showModal();
            form.username.focus();
        });
        return loginPromise;
    }

    function updateAuthUi() {
        $('#logout-btn').hidden = !storage.get(TOKEN_KEY);
    }

    async function api(path, options, retried) {
        const opts = Object.assign({ cache: 'no-store' }, options || {});
        const headers = new Headers(opts.headers || {});
        const token = storage.get(TOKEN_KEY);
        if (token) headers.set('Authorization', 'Bearer ' + token);
        opts.headers = headers;

        const res = await fetch(API_PREFIX + path, opts);
        if (res.status === 401 && !retried) {
            storage.remove(TOKEN_KEY);
            updateAuthUi();
            await login();
            return api(path, options, true);
        }
        const data = await res.json().catch(() => null);
        if (!res.ok) throw new ApiError(res.status, data, detailText(data, 'Request failed (' + res.status + ').'));
        return data;
    }

    // ---------- server status ----------

    async function fetchInfo() {
        const res = await fetch('/.well-known/chacc', { cache: 'no-store' });
        if (!res.ok) throw new Error('status ' + res.status);
        return res.json();
    }

    function setStatus(kind, text) {
        $('.status').dataset.state = kind;
        $('.status-text').textContent = text;
    }

    const DEV_NOTE_KEY = 'chacc_console_dev_note_dismissed';

    function showInfo(info) {
        let dismissed = false;
        try { dismissed = localStorage.getItem(DEV_NOTE_KEY) === '1'; } catch (e) { /* ignore */ }
        $('#dev-note').hidden = info.mode !== 'development' || dismissed;
        setStatus('running', info.mode.charAt(0).toUpperCase() + info.mode.slice(1));
        $('.version').textContent = 'v' + info.version;
        const restartBtn = $('#restart-btn');
        restartBtn.disabled = !info.restart_supported;
        restartBtn.title = info.restart_supported
            ? 'Restart the server so module changes take effect'
            : info.mode === 'development'
                ? 'Disabled in development mode: the server reloads by itself when files change'
                : 'Unavailable: start the server with "chacc run server" to enable restarts';
        document.querySelector('[data-action="restart"]').hidden = !info.restart_supported;
        const pendingFor = storage.get(PENDING_KEY);
        $('#pending-banner').hidden = !(pendingFor && pendingFor === info.boot_id);
    }

    // Light status check; the restart flow polls on its own while it waits.
    const STATUS_INTERVAL_MS = 30000;
    let statusTimer = null;

    async function pollStatus() {
        clearTimeout(statusTimer);
        if (!state.restarting && !document.hidden) {
            try {
                state.info = await fetchInfo();
                showInfo(state.info);
            } catch (e) {
                setStatus('error', 'Unreachable');
            }
        }
        statusTimer = setTimeout(pollStatus, STATUS_INTERVAL_MS);
    }

    function markPending() {
        if (state.info) storage.set(PENDING_KEY, state.info.boot_id);
        $('#pending-banner').hidden = false;
    }

    // ---------- restart ----------

    async function restart() {
        if (state.restarting || (state.info && !state.info.restart_supported)) return;
        let response;
        try {
            response = await api('/system/restart', { method: 'POST' });
        } catch (e) {
            if (e.status !== 401) toast(e.message, 'error');
            return;
        }
        const oldBoot = response.boot_id || (state.info && state.info.boot_id);
        state.restarting = true;
        $('#restart-overlay').hidden = false;
        setStatus('loading', 'Restarting…');
        const started = Date.now();
        const text = $('#restart-text');

        while (Date.now() - started < RESTART_TIMEOUT_MS) {
            await new Promise((r) => setTimeout(r, 1000));
            const seconds = Math.round((Date.now() - started) / 1000);
            text.textContent = 'Waiting for the server to come back (' + seconds + 's).';
            try {
                const info = await fetchInfo();
                if (info.boot_id !== oldBoot && !info.restart_pending) {
                    state.info = info;
                    storage.remove(PENDING_KEY);
                    state.restarting = false;
                    $('#restart-overlay').hidden = true;
                    showInfo(info);
                    toast('Server restarted.');
                    await loadAll();
                    return;
                }
            } catch (e) { /* still down */ }
        }
        state.restarting = false;
        $('#restart-overlay').hidden = true;
        toast('The server did not come back within 2 minutes. Check the server logs.', 'error');
    }

    // ---------- modules ----------

    function confirmAction(title, text, okLabel) {
        const dialog = $('#confirm-dialog');
        $('#confirm-title').textContent = title;
        $('#confirm-text').textContent = text;
        $('#confirm-ok').textContent = okLabel || 'Confirm';
        dialog.returnValue = '';
        dialog.showModal();
        return new Promise((resolve) => {
            dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
        });
    }

    function reportResult(data) {
        toast(data.message || 'Done.');
        for (const warning of data.warnings || []) toast(warning, 'warning');
        markPending();
    }

    function reportError(e) {
        if (e.status === 401 && e.message === 'Login cancelled.') return;
        let message = e.message;
        const missing = e.data && e.data.missing_dependencies;
        if (e.status === 409 && missing && missing.required && missing.required.length) {
            message += '\nInstall first: ' + missing.required.join(', ');
        }
        toast(message, 'error');
    }

    async function moduleAction(module, action) {
        const name = module.name;
        if (action === 'uninstall') {
            const ok = await confirmAction(
                'Uninstall ' + (module.display_name || name) + '?',
                'This removes the module archive, its code and its database record. Its tables are kept.',
                'Uninstall'
            );
            if (!ok) return;
        }
        const method = action === 'uninstall' ? 'DELETE' : 'POST';
        try {
            const data = await api('/modules/' + encodeURIComponent(name) + '/' + action, { method });
            reportResult(data);
        } catch (e) {
            reportError(e);
        }
        await loadAll();
    }

    async function upload(file) {
        if (!file) return;
        if (!file.name.endsWith('.chacc')) {
            toast('Choose a .chacc module package.', 'error');
            return;
        }
        const zone = $('#dropzone');
        const text = zone.querySelector('.dropzone-text');
        const original = text.innerHTML;
        zone.classList.add('is-busy');
        text.textContent = 'Installing ' + file.name + '… resolving dependencies can take a while.';
        try {
            const body = new FormData();
            body.append('file', file);
            reportResult(await api('/modules/', { method: 'POST', body }));
        } catch (e) {
            reportError(e);
        } finally {
            zone.classList.remove('is-busy');
            text.innerHTML = original;
            $('#upload-input').value = '';
        }
        await loadAll();
    }

    function dependsOn(module) {
        const deps = module.dependencies || { required: [], optional: [] };
        const missing = module.missing_dependencies || { required: [], optional: [] };
        if (!deps.required.length && !deps.optional.length) return el('span', { class: 'muted' }, '—');
        const parts = [];
        for (const name of deps.required) {
            const bad = missing.required.includes(name);
            parts.push(el('span', { class: 'dep' + (bad ? ' dep-missing' : ''), title: bad ? 'Required, not installed' : 'Required' }, name));
        }
        for (const name of deps.optional) {
            const bad = missing.optional.includes(name);
            parts.push(el('span', { class: 'dep dep-optional' + (bad ? ' dep-missing-optional' : ''), title: bad ? 'Optional, not installed' : 'Optional' }, name));
        }
        const out = [];
        parts.forEach((part, i) => { if (i) out.push(', '); out.push(part); });
        return el('span', { class: 'deps' }, out);
    }

    function statusCell(m) {
        const missingRequired = (m.missing_dependencies && m.missing_dependencies.required) || [];
        if (m.is_enabled && missingRequired.length) {
            return el('span', { class: 'state state-blocked', title: 'Missing required module(s): ' + missingRequired.join(', ') }, 'Not loaded');
        }
        return el('span', { class: 'state ' + (m.is_enabled ? 'state-on' : 'state-off') }, m.is_enabled ? 'Enabled' : 'Disabled');
    }

    // ---------- row menu ----------

    const ICONS = {
        enable: '<polygon points="6 4 20 12 6 20 6 4"></polygon>',
        disable: '<rect x="6" y="4" width="4" height="16" rx="1"></rect><rect x="14" y="4" width="4" height="16" rx="1"></rect>',
        uninstall: '<polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6M14 11v6"></path><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>',
    };

    function menuIcon(name) {
        const icon = svg('svg', { viewBox: '0 0 24 24', 'aria-hidden': 'true' });
        icon.innerHTML = ICONS[name];
        return icon;
    }

    let menuOwner = null;

    function closeMenu() {
        const menu = $('#row-menu');
        if (menu.hidden) return;
        menu.hidden = true;
        if (menuOwner) menuOwner.setAttribute('aria-expanded', 'false');
        menuOwner = null;
    }

    function openMenu(button, m) {
        if (menuOwner === button) { closeMenu(); return; }
        closeMenu();
        const menu = $('#row-menu');
        const item = (action, label, cls) => el('button', {
            type: 'button', role: 'menuitem', class: 'menu-item' + (cls ? ' ' + cls : ''),
            onclick: () => { closeMenu(); moduleAction(m, action); },
        }, menuIcon(action), label);
        menu.replaceChildren(
            m.is_enabled ? item('disable', 'Disable') : item('enable', 'Enable', 'menu-item-primary'),
            item('uninstall', 'Uninstall…', 'menu-item-danger')
        );
        menu.hidden = false;
        const rect = button.getBoundingClientRect();
        const width = menu.offsetWidth;
        const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
        let top = rect.bottom + 6;
        if (top + menu.offsetHeight > window.innerHeight - 8) top = rect.top - menu.offsetHeight - 6;
        menu.style.left = left + 'px';
        menu.style.top = top + 'px';
        button.setAttribute('aria-expanded', 'true');
        menuOwner = button;
        menu.querySelector('.menu-item').focus();
    }

    document.addEventListener('click', (e) => {
        if (menuOwner && !e.target.closest('#row-menu') && !menuOwner.contains(e.target)) closeMenu();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && menuOwner) { const owner = menuOwner; closeMenu(); owner.focus(); }
    });
    window.addEventListener('resize', closeMenu);
    window.addEventListener('scroll', closeMenu, true);

    function renderModules() {
        closeMenu();
        const list = $('#module-list');
        list.replaceChildren();
        $('#module-count').textContent = state.loaded ? '(' + state.modules.length + ')' : '';
        const query = state.filter.trim().toLowerCase();
        const modules = state.modules
            .filter((m) => !query || [m.name, m.display_name, m.description].some((v) => (v || '').toLowerCase().includes(query)))
            .sort((a, b) => a.name.localeCompare(b.name));

        if (!state.modules.length) {
            list.append(el('div', { class: 'empty' }, state.loaded ? 'No modules installed yet. Drop a .chacc package above to install one.' : 'Loading modules…'));
            return;
        }
        if (!modules.length) {
            list.append(el('div', { class: 'empty' }, 'No modules match "' + state.filter + '".'));
            return;
        }

        for (const m of modules) {
            const subtitle = [m.name, m.description].filter(Boolean).join(' · ');
            const kebab = el('button', {
                type: 'button', class: 'kebab', 'aria-haspopup': 'menu', 'aria-expanded': 'false',
                'aria-label': 'Actions for ' + (m.display_name || m.name),
            }, el('span', {}), el('span', {}), el('span', {}));
            kebab.addEventListener('click', (e) => { e.stopPropagation(); openMenu(kebab, m); });
            list.append(el('div', { class: 'row', role: 'row' },
                el('div', { class: 'cell-module', role: 'cell' },
                    el('div', { class: 'module-title' }, m.display_name || m.name),
                    el('div', { class: 'module-sub', title: subtitle }, subtitle)),
                el('div', { class: 'cell-version', role: 'cell' }, m.version || '—'),
                el('div', { role: 'cell' }, statusCell(m)),
                el('div', { class: 'cell-deps', role: 'cell' }, dependsOn(m)),
                el('div', { class: 'col-actions', role: 'cell' }, kebab)
            ));
        }
    }

    // ---------- dependency graph ----------

    const NODE_W = 220;
    const NODE_H = 54;
    const COL_GAP = 90;
    const ROW_GAP = 22;
    const PAD = 12;

    function layout(nodes, edges) {
        const deps = new Map(nodes.map((n) => [n.name, []]));
        for (const e of edges) if (deps.has(e.from) && deps.has(e.to)) deps.get(e.from).push(e.to);
        const level = new Map();
        function depth(name, seen) {
            if (level.has(name)) return level.get(name);
            if (seen.has(name)) return 0; // cycle: stop here
            seen.add(name);
            let d = 0;
            for (const dep of deps.get(name)) d = Math.max(d, depth(dep, seen) + 1);
            seen.delete(name);
            level.set(name, d);
            return d;
        }
        nodes.forEach((n) => depth(n.name, new Set()));

        const columns = [];
        for (const n of nodes) (columns[level.get(n.name)] = columns[level.get(n.name)] || []).push(n);
        const pos = new Map();
        columns.forEach((col, x) => {
            col.sort((a, b) => a.name.localeCompare(b.name));
            col.forEach((n, y) => pos.set(n.name, { x: PAD + x * (NODE_W + COL_GAP), y: PAD + y * (NODE_H + ROW_GAP) }));
        });
        const width = PAD * 2 + Math.max(1, columns.length) * NODE_W + Math.max(0, columns.length - 1) * COL_GAP;
        const height = PAD * 2 + Math.max(1, ...columns.map((c) => c.length)) * (NODE_H + ROW_GAP) - ROW_GAP;
        return { pos, width, height };
    }

    function truncate(text, max) {
        return text.length > max ? text.slice(0, max - 1) + '…' : text;
    }

    function renderGraph() {
        const graph = state.graph;
        const root = $('#graph');
        root.replaceChildren();
        $('#graph-problems').replaceChildren();
        $('#load-order').replaceChildren();
        if (!graph) return;

        $('#graph-intro').textContent = graph.mode === 'production'
            ? 'Installed production modules (from ' + graph.source + '). Arrows point from a module to the modules it depends on.'
            : 'Development mode: modules in ' + graph.source + '. Arrows point from a module to the modules it depends on.';

        if (!graph.nodes.length) {
            root.setAttribute('width', 0);
            root.setAttribute('height', 0);
            $('#graph-problems').append(el('div', { class: 'empty' }, 'No modules installed.'));
            return;
        }

        const { pos, width, height } = layout(graph.nodes, graph.edges);
        root.setAttribute('width', width);
        root.setAttribute('height', height);
        root.setAttribute('viewBox', '0 0 ' + width + ' ' + height);

        const defs = svg('defs');
        for (const [id, cls] of [['arrow', 'arrow'], ['arrow-broken', 'arrow-broken'], ['arrow-broken-opt', 'arrow-broken-opt']]) {
            defs.append(svg('marker', { id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' },
                svg('path', { d: 'M 0 0 L 10 5 L 0 10 z', class: cls })));
        }
        root.append(defs);

        const edgeLayer = svg('g');
        for (const e of graph.edges) {
            const a = pos.get(e.from);
            const b = pos.get(e.to);
            if (!a || !b) continue;
            const optional = e.kind === 'optional';
            const broken = !e.satisfied;
            const x1 = a.x;
            const y1 = a.y + NODE_H / 2;
            const x2 = b.x + NODE_W;
            const y2 = b.y + NODE_H / 2;
            const bend = Math.max(40, Math.abs(x1 - x2) / 2);
            const marker = broken ? (optional ? 'arrow-broken-opt' : 'arrow-broken') : 'arrow';
            const path = svg('path', {
                d: 'M ' + x1 + ' ' + y1 + ' C ' + (x1 - bend) + ' ' + y1 + ', ' + (x2 + bend) + ' ' + y2 + ', ' + x2 + ' ' + y2,
                class: 'edge' + (optional ? ' edge-optional' : '') + (broken ? ' edge-broken' : ''),
                'marker-end': 'url(#' + marker + ')',
            });
            path.append(svg('title', {}, e.from + ' ' + (optional ? 'optionally uses ' : 'requires ') + e.to + (broken ? ' (not available)' : '')));
            edgeLayer.append(path);
        }
        root.append(edgeLayer);

        const labels = { ok: 'loads', blocked: 'blocked', disabled: 'disabled', missing: 'not installed' };
        for (const n of graph.nodes) {
            const p = pos.get(n.name);
            const g = svg('g', { class: 'node node-' + n.state, transform: 'translate(' + p.x + ',' + p.y + ')' });
            g.append(
                svg('title', {}, n.name + ' (' + labels[n.state] + ')' + (n.reason ? ': ' + n.reason : '')),
                svg('rect', { width: NODE_W, height: NODE_H, rx: 10 }),
                svg('text', { x: 12, y: 22 }, truncate(n.display_name || n.name, 27)),
                svg('text', { x: 12, y: 40, class: 'sub' }, truncate(n.state === 'missing' ? 'not installed' : n.name + (n.version ? ' · v' + n.version : ''), 28))
            );
            root.append(g);
        }

        const problems = [];
        for (const n of graph.nodes) {
            if (n.state === 'blocked') {
                problems.push(el('div', { class: 'problem' },
                    el('strong', {}, n.name), ' will not load: ' + n.reason,
                    el('div', { class: 'problem-fix' }, 'To fix: ' + graph.how_to_fix + ', then restart the server.')));
            } else if (n.state === 'ok' && n.missing_optional.length) {
                problems.push(el('div', { class: 'problem is-warning' },
                    el('strong', {}, n.name), ' loads with fewer features. Optional module(s) not installed: ' + n.missing_optional.join(', ') + '.'));
            }
        }
        const box = $('#graph-problems');
        if (problems.length) box.append(el('div', { class: 'problems' }, problems));
        else box.append(el('p', { class: 'all-good' }, 'All dependencies are satisfied.'));

        if (graph.load_order.length) {
            $('#load-order').append('Load order', el('ol', {}, graph.load_order.map((name) => el('li', {}, el('code', {}, name)))));
        }
    }

    // ---------- loading ----------

    async function loadAll() {
        try {
            const [modules, graph] = await Promise.all([api('/modules/'), api('/modules/graph')]);
            state.modules = modules.modules || [];
            state.graph = graph;
            state.loaded = true;
            renderModules();
            renderGraph();
        } catch (e) {
            if (e.status === 401) {
                const list = $('#module-list');
                list.replaceChildren(el('div', { class: 'empty' },
                    'Log in to see and manage modules. ',
                    el('button', { type: 'button', class: 'btn btn-small btn-primary', onclick: () => login().then(loadAll, () => {}) }, 'Log in')));
                return;
            }
            toast(e.message, 'error');
        }
    }

    // ---------- wiring ----------

    function selectTab(name) {
        document.querySelectorAll('.tab').forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.tab === name)));
        $('#panel-modules').hidden = name !== 'modules';
        $('#panel-graph').hidden = name !== 'graph';
        try { location.replace('#' + name); } catch (e) { /* ignore */ }
    }

    document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => selectTab(tab.dataset.tab)));
    $('#restart-btn').addEventListener('click', restart);
    document.querySelector('[data-action="restart"]').addEventListener('click', restart);
    $('#dev-note-close').addEventListener('click', () => {
        $('#dev-note').hidden = true;
        try { localStorage.setItem(DEV_NOTE_KEY, '1'); } catch (e) { /* ignore */ }
    });
    $('#filter').addEventListener('input', (e) => { state.filter = e.target.value; renderModules(); });
    $('#logout-btn').addEventListener('click', () => {
        storage.remove(TOKEN_KEY);
        updateAuthUi();
        state.modules = [];
        state.graph = null;
        state.loaded = false;
        renderModules();
        renderGraph();
        loadAll();
    });
    $('#upload-input').addEventListener('change', (e) => upload(e.target.files[0]));
    const zone = $('#dropzone');
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('is-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('is-over'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('is-over');
        upload(e.dataTransfer.files[0]);
    });

    selectTab(location.hash === '#graph' ? 'graph' : 'modules');
    updateAuthUi();

    (async function start() {
        try {
            state.info = await fetchInfo();
            showInfo(state.info);
        } catch (e) {
            setStatus('error', 'Unreachable');
        }
        statusTimer = setTimeout(pollStatus, STATUS_INTERVAL_MS);
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) pollStatus();
        });
        await loadAll();
    })();
})();

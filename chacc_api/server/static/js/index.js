const API_PREFIX = (function () {
    const meta = document.querySelector('meta[name="chacc-api-prefix"]');
    const value = meta ? meta.content : '/api';
    // Unrendered placeholder (e.g. template opened directly) -> default.
    return value.includes('{{') ? '/api' : value.replace(/\/+$/, '');
})();

/*
 * Keep listening to the server.
 *
 * Polls /.well-known/chacc (unprefixed, cheap). While the server is up we
 * check every few seconds; when it goes away (e.g. a restart) we poll fast
 * and show "Restarting…". A changed boot_id means a new process is serving.
 */
(function () {
    const status = document.querySelector('.status');
    const label = document.querySelector('.status-text');
    const versionEl = document.querySelector('.version-text');

    const UP_INTERVAL = 5000;
    const DOWN_INTERVAL = 1000;
    const TIMEOUT = 4000;

    let bootId = null;
    let mode = null;
    let wasDown = false;
    let timer = null;

    function setState(state, text) {
        if (status) status.dataset.state = state;
        if (label) label.textContent = text;
    }

    function capitalize(value) {
        return value.charAt(0).toUpperCase() + value.slice(1);
    }

    async function fetchJson(url) {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), TIMEOUT);
        try {
            const res = await fetch(url, { cache: 'no-store', signal: controller.signal });
            if (!res.ok) throw new Error(url + ' -> ' + res.status);
            return await res.json();
        } finally {
            clearTimeout(t);
        }
    }

    async function refreshMode() {
        try {
            const data = await fetchJson(API_PREFIX + '/health/live');
            mode = capitalize(data.mode || 'development');
        } catch (e) {
            mode = mode || 'Running';
        }
    }

    async function refreshVersion() {
        try {
            const data = await fetchJson(API_PREFIX + '/version');
            if (versionEl) versionEl.textContent = 'v' + data.version;
        } catch (e) {
            if (versionEl && versionEl.textContent.includes('Loading')) versionEl.textContent = 'unknown';
        }
    }

    function schedule(ms) {
        clearTimeout(timer);
        timer = setTimeout(poll, ms);
    }

    async function poll() {
        try {
            const info = await fetchJson('/.well-known/chacc');
            const restarted = bootId !== null && info.boot_id !== bootId;

            if (bootId === null || restarted) {
                await Promise.all([refreshMode(), refreshVersion()]);
            }
            bootId = info.boot_id;

            if (info.restart_pending) {
                setState('loading', 'Restarting…');
                schedule(DOWN_INTERVAL);
                return;
            }
            if (restarted || wasDown) {
                setState('running', restarted ? 'Restarted' : 'Reconnected');
                setTimeout(() => {
                    if (status && status.dataset.state === 'running') setState('running', mode);
                }, 3000);
            } else {
                setState('running', mode);
            }
            wasDown = false;
            schedule(UP_INTERVAL);
        } catch (e) {
            // Failing before we ever connected means the server is not reachable at all.
            setState(bootId === null ? 'error' : 'loading', bootId === null ? 'Unknown' : 'Restarting…');
            wasDown = true;
            schedule(DOWN_INTERVAL);
        }
    }

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) schedule(0);
    });

    poll();
})();

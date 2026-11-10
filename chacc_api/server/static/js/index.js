const API_PREFIX = (function () {
    const meta = document.querySelector('meta[name="chacc-api-prefix"]');
    const value = meta ? meta.content : '/api';
    // Unrendered placeholder (e.g. template opened directly) -> default.
    return value.includes('{{') ? '/api' : value.replace(/\/+$/, '');
})();

(async function () {
    const status = document.querySelector('.status');
    const label = document.querySelector('.status-text');

    function setState(state, text) {
        if (status) status.dataset.state = state;
        if (label) label.textContent = text;
    }

    try {
        const res = await fetch(API_PREFIX + '/health/live', { cache: 'no-store' });
        if (!res.ok) throw new Error('Health check failed');
        const data = await res.json();
        const raw = data.mode || 'development';
        setState('running', raw.charAt(0).toUpperCase() + raw.slice(1));
    } catch (e) {
        setState('error', 'Unknown');
    }
})();

(async function () {
    const el = document.querySelector('.version-text');
    try {
        const res = await fetch(API_PREFIX + '/version');
        if (!res.ok) throw new Error('Version fetch failed');
        const data = await res.json();
        if (el) el.textContent = 'v' + data.version;
    } catch (e) {
        if (el) el.textContent = 'unknown';
    }
})();

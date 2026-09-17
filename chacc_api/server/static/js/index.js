(async function () {
    try {
        const res = await fetch('/api/health/live');
        if (!res.ok) throw new Error('Health check failed');
        const data = await res.json();
        const mode = (data.mode || 'development').charAt(0).toUpperCase() + (data.mode || 'development').slice(1);
        const el = document.querySelector('.status-text');
        if (el) el.textContent = mode;
    } catch (e) {
        const el = document.querySelector('.status-text');
        if (el) el.textContent = 'Unknown';
    }
})();

(async function () {
    try {
        const res = await fetch('/api/version');
        if (!res.ok) throw new Error('Version fetch failed');
        const data = await res.json();
        const el = document.querySelector('.version-text');
        if (el) el.textContent = 'v' + data.version;
    } catch (e) {
        const el = document.querySelector('.version-text');
        if (el) el.textContent = 'unknown';
    }
})();

(async function () {
    // Poll the basic health endpoint for dependency resolution status.
    // Shows a message while the entrypoint is resolving dependencies.
    async function checkResolution() {
        try {
            const res = await fetch('/api/health');
            if (!res.ok) return;
            const data = await res.json();
            const state = (data.checks && data.checks.dependency_resolution) || 'done';

            if (state === 'running') {
                const banner = document.getElementById('resolution-banner');
                if (banner) banner.style.display = 'block';
                setTimeout(checkResolution, 2000);
            } else {
                const banner = document.getElementById('resolution-banner');
                if (banner) banner.style.display = 'none';
            }
        } catch (e) {
            // Health endpoint not available yet — retry briefly.
            setTimeout(checkResolution, 2000);
        }
    }

    checkResolution();
})();
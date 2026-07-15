(async function () {
    try {
        const res = await fetch('/health/live');
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

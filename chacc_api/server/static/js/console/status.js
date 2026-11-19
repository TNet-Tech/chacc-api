// The top bar: server mode and version, service problems, pending changes and restarts.
import { api } from './api.js';
import { $, storage, toast } from './dom.js';
import { loadAll } from './loader.js';
import { loadServices, serviceProblems } from './services.js';
import { state } from './state.js';

const PENDING_KEY = 'chacc_console_pending_boot';
const DEV_NOTE_KEY = 'chacc_console_dev_note_dismissed';
const RESTART_TIMEOUT_MS = 120000;
// Light status check; the restart flow polls on its own while it waits.
const STATUS_INTERVAL_MS = 30000;

export async function fetchInfo() {
    const res = await fetch('/.well-known/chacc', { cache: 'no-store' });
    if (!res.ok) throw new Error('status ' + res.status);
    return res.json();
}

export function setStatus(kind, text) {
    $('.status').dataset.state = kind;
    $('.status-text').textContent = text;
}

// Server mode, plus a note when a service has a problem.
export function updateTopStatus() {
    if (!state.info || state.restarting) return;
    const mode = state.info.mode.charAt(0).toUpperCase() + state.info.mode.slice(1);
    const problems = serviceProblems();
    const node = $('.status');
    if (!problems.length) {
        setStatus('running', mode);
        node.removeAttribute('title');
        node.classList.remove('is-clickable');
        return;
    }
    const down = problems.some((p) => p.status === 'down');
    const text = problems.length === 1
        ? problems[0].name + (down ? ' not working' : ' limited')
        : problems.length + ' services need attention';
    setStatus(down ? 'error' : 'warning', mode + ' · ' + text);
    node.title = 'Show services';
    node.classList.add('is-clickable');
}

export function showInfo(info) {
    let dismissed = false;
    try { dismissed = localStorage.getItem(DEV_NOTE_KEY) === '1'; } catch (e) { /* ignore */ }
    $('#dev-note').hidden = info.mode !== 'development' || dismissed;
    updateTopStatus();
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

export function dismissDevNote() {
    $('#dev-note').hidden = true;
    try { localStorage.setItem(DEV_NOTE_KEY, '1'); } catch (e) { /* ignore */ }
}

let statusTimer = null;

async function pollStatus() {
    clearTimeout(statusTimer);
    if (!state.restarting && !document.hidden) {
        try {
            state.info = await fetchInfo();
            showInfo(state.info);
            await loadServices();
        } catch (e) {
            setStatus('error', 'Unreachable');
        }
    }
    statusTimer = setTimeout(pollStatus, STATUS_INTERVAL_MS);
}

// Checks the server every 30 s, and right away when the tab becomes visible.
export function startPolling() {
    statusTimer = setTimeout(pollStatus, STATUS_INTERVAL_MS);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) pollStatus();
    });
}

// A module change needs a restart; remembered for this server run.
export function markPending() {
    if (state.info) storage.set(PENDING_KEY, state.info.boot_id);
    $('#pending-banner').hidden = false;
}

export async function restart() {
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

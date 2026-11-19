// The Services tab: database, Redis, rate limiting and the server.
import { api } from './api.js';
import { $, el } from './dom.js';
import { loginPrompt, noAccessPrompt } from './loader.js';
import { state } from './state.js';
import { updateTopStatus } from './status.js';

const SERVICE_LABELS = { ok: 'Working', degraded: 'Limited', down: 'Not working', disabled: 'Not set up' };

export function serviceProblems() {
    const services = (state.services && state.services.services) || [];
    return services.filter((s) => s.status === 'down' || s.status === 'degraded');
}

function duration(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d) return d + ' d ' + h + ' h';
    if (h) return h + ' h ' + m + ' min';
    if (m) return m + ' min';
    return '< 1 min';
}

function serviceCard(service) {
    const details = service.details.slice();
    if (service.id === 'server' && service.started_at) {
        details.splice(1, 0, { label: 'Uptime', value: duration(Date.now() / 1000 - service.started_at) });
    }
    return el('article', { class: 'service service-' + service.status },
        el('header', { class: 'service-head' },
            el('h3', { class: 'service-name', title: service.description || null }, service.name),
            el('span', { class: 'service-state' }, SERVICE_LABELS[service.status] || service.status)),
        service.message ? el('p', { class: 'service-message' }, service.message) : null,
        service.hint ? el('p', { class: 'service-hint' }, service.hint) : null,
        details.length
            ? el('dl', { class: 'service-details' }, details.flatMap((d) => [el('dt', {}, d.label), el('dd', {}, d.value)]))
            : null,
        service.error
            ? el('details', { class: 'service-tech' },
                el('summary', {}, 'Error details'),
                el('code', {}, service.error))
            : null);
}

export function renderServices() {
    const list = $('#services-list');
    const badge = $('#services-badge');
    const problems = serviceProblems();
    badge.hidden = !problems.length;
    badge.textContent = problems.length;
    badge.className = 'tab-badge' + (problems.some((p) => p.status === 'down') ? ' is-down' : '');
    badge.title = problems.map((p) => p.name + ': ' + SERVICE_LABELS[p.status]).join(', ');
    updateTopStatus();

    if (state.servicesError === 'login') {
        $('#services-checked').textContent = '';
        list.replaceChildren(loginPrompt('Log in to see the services.'));
        return;
    }
    if (state.servicesError === 'forbidden') {
        $('#services-checked').textContent = '';
        list.replaceChildren(noAccessPrompt());
        return;
    }
    if (!state.services) {
        list.replaceChildren(el('div', { class: 'empty' }, state.servicesError || 'Checking services…'));
        return;
    }
    const checked = new Date(state.services.checked_at * 1000);
    $('#services-checked').textContent = 'Checked ' + checked.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    // Keep the open/closed state of "Error details" across refreshes.
    const open = new Set([...list.querySelectorAll('details[open]')].map((d) => d.closest('.service').dataset.id));
    const cards = state.services.services.map((service) => {
        const card = serviceCard(service);
        card.dataset.id = service.id;
        const tech = card.querySelector('details');
        if (tech && open.has(service.id)) tech.open = true;
        return card;
    });
    list.replaceChildren(...cards);
}

let servicesLoading = null;

// Never opens the login dialog: it runs every 30 s in the background.
export function loadServices() {
    if (servicesLoading) return servicesLoading;
    servicesLoading = (async () => {
        try {
            state.services = await api('/system/services', { noLoginPrompt: true });
            state.servicesError = null;
        } catch (e) {
            state.services = null;
            state.servicesError = e.status === 401 ? 'login' : e.status === 403 ? 'forbidden' : 'Could not check the services: ' + e.message;
        } finally {
            servicesLoading = null;
        }
        renderServices();
    })();
    return servicesLoading;
}

export async function refreshServices() {
    const button = $('#services-refresh');
    button.disabled = true;
    try { await loadServices(); } finally { button.disabled = false; }
}

// Loads the module list, the dependency graph and the services, and handles being logged out.
import { api, authenticate, login, logout } from './api.js';
import { $, el, toast } from './dom.js';
import { renderGraph } from './graph.js';
import { renderModules } from './modules.js';
import { loadServices, renderServices } from './services.js';
import { state } from './state.js';

export function loginPrompt(text) {
    return el('div', { class: 'empty' }, text + ' ',
        el('button', { type: 'button', class: 'btn btn-small btn-primary', onclick: () => authenticate().then(loadAll, () => {}) }, 'Log in'));
}

// Logged in, but the account lacks the admin privilege (403).
export function noAccessPrompt() {
    return el('div', { class: 'empty' }, 'Your account can\'t manage this server. ',
        el('button', {
            type: 'button',
            class: 'btn btn-small btn-primary',
            onclick: () => { logout(); login().then(loadAll, () => {}); },
        }, 'Log in as someone else'));
}

// The prompt for a failed request, or null when it isn't about access.
function accessPrompt(error, text) {
    if (error.status === 401) return loginPrompt(text);
    if (error.status === 403) return noAccessPrompt();
    return null;
}

// The graph and the module list load independently: in development mode the
// graph is open while the module list may still need a login. There we show a
// "Log in" button rather than opening the dialog as soon as the page loads.
export async function loadAll() {
    const dev = Boolean(state.info && state.info.mode === 'development');
    const [modules, graph] = await Promise.allSettled([
        api('/modules/', { noLoginPrompt: dev }),
        api('/modules/graph'),
        loadServices(),
    ]);

    if (graph.status === 'fulfilled') {
        state.graph = graph.value;
        renderGraph();
    } else {
        state.graph = null;
        renderGraph();
        const prompt = accessPrompt(graph.reason, 'Log in to see the dependency graph.');
        if (prompt) {
            $('#graph-problems').replaceChildren(prompt);
        } else {
            toast(graph.reason.message, 'error');
        }
    }

    if (modules.status === 'fulfilled') {
        state.modules = modules.value.modules || [];
        state.loaded = true;
        renderModules();
    } else {
        state.modules = [];
        state.loaded = false;
        renderModules();
        const prompt = accessPrompt(modules.reason, 'Log in to see and manage modules.');
        if (prompt) {
            $('#module-list').replaceChildren(prompt);
        } else {
            toast(modules.reason.message, 'error');
        }
    }
}

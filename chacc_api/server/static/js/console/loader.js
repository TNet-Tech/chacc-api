// Loads the module list, the dependency graph and the services, and handles being logged out.
import { api, login } from './api.js';
import { $, el, toast } from './dom.js';
import { renderGraph } from './graph.js';
import { renderModules } from './modules.js';
import { loadServices, renderServices } from './services.js';
import { state } from './state.js';

export function loginPrompt(text) {
    return el('div', { class: 'empty' }, text + ' ',
        el('button', { type: 'button', class: 'btn btn-small btn-primary', onclick: () => login().then(loadAll, () => {}) }, 'Log in'));
}

// Logged out on a protected server: the tabs ask for a login instead of looking empty.
export function showLoginPrompt() {
    state.modules = [];
    state.graph = null;
    state.loaded = false;
    renderModules();
    renderGraph();
    $('#module-count').textContent = '';
    $('#module-list').replaceChildren(loginPrompt('Log in to see and manage modules.'));
    $('#graph-problems').replaceChildren(loginPrompt('Log in to see the dependency graph.'));
    state.services = null;
    state.servicesError = 'login';
    renderServices();
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
        if (graph.reason.status === 401) {
            $('#graph-problems').replaceChildren(loginPrompt('Log in to see the dependency graph.'));
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
        if (modules.reason.status === 401) {
            $('#module-list').replaceChildren(loginPrompt('Log in to see and manage modules.'));
        } else {
            toast(modules.reason.message, 'error');
        }
    }
}

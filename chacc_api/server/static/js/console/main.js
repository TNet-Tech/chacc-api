/*
 * ChaCC module console: entry point. Wires the page up and loads the data.
 *
 * Talks to the core API: GET/POST/DELETE {prefix}/modules..., GET {prefix}/modules/graph,
 * GET {prefix}/system/services and POST {prefix}/system/restart (see api.js for login).
 *
 *   api.js             API calls, login and the web console key
 *   access.js          shows only the login (or key) until access is granted
 *   loader.js          loads modules, graph and services; logged-out views
 *   status.js          top bar, polling, pending changes, restart
 *   modules.js         Modules tab table (row-menu.js, module-actions.js)
 *   module-details.js  module details popup (markdown.js for the README)
 *   graph.js           Dependencies tab
 *   services.js        Services tab
 *   dom.js, state.js   shared helpers and state
 */
import { unlock } from './access.js';
import { logout, updateAuthUi } from './api.js';
import { $ } from './dom.js';
import { loadAll } from './loader.js';
import { upload } from './module-actions.js';
import { openModuleDetails, setupModuleDialog } from './module-details.js';
import { renderModules } from './modules.js';
import { refreshServices, serviceProblems } from './services.js';
import { state } from './state.js';
import { dismissDevNote, restart, startPolling } from './status.js';

const TABS = ['modules', 'graph', 'services'];

function selectTab(name) {
    document.querySelectorAll('.tab').forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.tab === name)));
    for (const tab of TABS) $('#panel-' + tab).hidden = name !== tab;
    try { location.replace('#' + name); } catch (e) { /* ignore */ }
}

function setupDropzone() {
    const zone = $('#dropzone');
    $('#upload-input').addEventListener('change', (e) => upload(e.target.files[0]));
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('is-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('is-over'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('is-over');
        upload(e.dataTransfer.files[0]);
    });
}

document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => selectTab(tab.dataset.tab)));
$('#restart-btn').addEventListener('click', restart);
document.querySelector('[data-action="restart"]').addEventListener('click', restart);
$('#services-refresh').addEventListener('click', refreshServices);
$('.status').addEventListener('click', () => {
    if (serviceProblems().length) selectTab('services');
});
$('#dev-note-close').addEventListener('click', dismissDevNote);
$('#filter').addEventListener('input', (e) => { state.filter = e.target.value; renderModules(); });
// Logging out goes back to the gate: only the login (or key) dialog.
$('#logout-btn').addEventListener('click', () => {
    logout();
    location.reload();
});
setupDropzone();
setupModuleDialog();

// #module=<name> opens that module's details (a link you can share).
const linkedModule = location.hash.startsWith('#module=') ? decodeURIComponent(location.hash.slice(8)) : null;
selectTab(TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'modules');
updateAuthUi();

(async function start() {
    await unlock();
    startPolling();
    await loadAll();
    if (linkedModule) openModuleDetails(linkedModule);
})();

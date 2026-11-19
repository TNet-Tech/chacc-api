// The Modules tab: the table of installed modules.
import { $, el } from './dom.js';
import { moduleAction } from './module-actions.js';
import { openModuleDetails } from './module-details.js';
import { closeMenu, openMenu } from './row-menu.js';
import { state } from './state.js';

// The header is drawn here, next to the rows, so the two always match even
// if the page itself comes from an older cache.
const MODULE_COLUMNS = ['Module', 'Version', 'Author', 'Status', 'Depends on', 'Actions'];

function renderModuleHeader() {
    const head = document.querySelector('.table-head');
    if (head.dataset.columns === MODULE_COLUMNS.join('|')) return;
    head.replaceChildren(...MODULE_COLUMNS.map((label, i) => el('span', {
        role: 'columnheader',
        class: i === MODULE_COLUMNS.length - 1 ? 'col-actions' : null,
    }, label)));
    head.dataset.columns = MODULE_COLUMNS.join('|');
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
    if (!m.is_enabled && m.load_failure) {
        return el('span', { class: 'state state-blocked', title: m.load_failure }, 'Failed to load');
    }
    if (m.is_enabled && missingRequired.length) {
        return el('span', { class: 'state state-blocked', title: 'Missing required module(s): ' + missingRequired.join(', ') }, 'Not loaded');
    }
    return el('span', { class: 'state ' + (m.is_enabled ? 'state-on' : 'state-off') }, m.is_enabled ? 'Enabled' : 'Disabled');
}

function menuItems(m) {
    return [
        { icon: 'details', label: 'Details', onSelect: () => openModuleDetails(m.name) },
        m.is_enabled
            ? { icon: 'disable', label: 'Disable', onSelect: () => moduleAction(m, 'disable') }
            : { icon: 'enable', label: 'Enable', kind: 'primary', onSelect: () => moduleAction(m, 'enable') },
        { icon: 'uninstall', label: 'Uninstall…', kind: 'danger', onSelect: () => moduleAction(m, 'uninstall') },
    ];
}

export function renderModules() {
    closeMenu();
    renderModuleHeader();
    const list = $('#module-list');
    list.replaceChildren();
    $('#module-count').textContent = state.loaded ? '(' + state.modules.length + ')' : '';
    const query = state.filter.trim().toLowerCase();
    const modules = state.modules
        .filter((m) => !query || [m.name, m.display_name, m.description, m.author].some((v) => (v || '').toLowerCase().includes(query)))
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
        kebab.addEventListener('click', (e) => { e.stopPropagation(); openMenu(kebab, menuItems(m)); });
        list.append(el('div', { class: 'row', role: 'row' },
            el('div', { class: 'cell-module', role: 'cell' },
                el('button', {
                    type: 'button', class: 'module-title module-link',
                    title: 'Show details', onclick: () => openModuleDetails(m.name),
                }, m.display_name || m.name),
                el('div', { class: 'module-sub', title: subtitle }, subtitle)),
            el('div', { class: 'cell-version', role: 'cell' }, m.version || '—'),
            el('div', { class: 'cell-author' + (m.author ? '' : ' is-empty'), role: 'cell', title: m.author || null },
                m.author ? m.author : el('span', { class: 'muted' }, '—')),
            el('div', { role: 'cell' }, statusCell(m)),
            el('div', { class: 'cell-deps', role: 'cell' }, dependsOn(m)),
            el('div', { class: 'col-actions', role: 'cell' }, kebab)
        ));
    }
}

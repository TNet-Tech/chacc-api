// The module details popup.
import { api } from './api.js';
import { $, el } from './dom.js';
import { drawDiagrams, renderMarkdown } from './markdown.js';
import { moduleAction } from './module-actions.js';
import { state } from './state.js';

const STATE_CLASS = { loaded: 'ok', pending: 'info', stopping: 'info', disabled: 'off', failed: 'bad', blocked: 'bad' };

function formatDate(value) {
    if (!value) return null;
    // Naive timestamps from the database are UTC.
    const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : value + 'Z');
    return isNaN(date) ? value : date.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' bytes';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function link(url, label) {
    if (!/^https?:\/\//i.test(url || '')) return url;
    return el('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, label || url.replace(/^https?:\/\//, ''));
}

function moduleNames(names) {
    return names.length ? names.join(', ') : null;
}

function section(title, count, body) {
    return el('details', { class: 'md-section' },
        el('summary', {}, title, count !== null ? el('span', { class: 'md-count' }, count) : null),
        body);
}

function facts(d) {
    const links = [d.homepage && link(d.homepage, 'Homepage'), d.repository && link(d.repository, 'Repository'), d.support && link(d.support, 'Support')]
        .filter(Boolean).flatMap((a, i) => (i ? [' · ', a] : [a]));
    const rows = [
        ['API path', d.api_path],
        ['License', d.license],
        ['Needs ChaCC', d.required_chacc_version],
        ['Requires', moduleNames(d.dependencies.required.concat(d.dependencies.optional.map((n) => n + ' (optional)')))],
        ['Used by', moduleNames(d.used_by.required.concat(d.used_by.optional.map((n) => n + ' (optional)')))],
        ['Installed', formatDate(d.installed_at)],
        ['Updated', formatDate(d.updated_at) !== formatDate(d.installed_at) ? formatDate(d.updated_at) : null],
        ['Links', links.length ? el('span', {}, links) : null],
    ].filter(([, value]) => value);
    return el('dl', { class: 'md-facts' }, rows.flatMap(([label, value]) => [el('dt', {}, label), el('dd', {}, value)]));
}

function routesSection(routes) {
    return section('Routes', routes.length, el('ul', { class: 'md-routes' },
        routes.map((r) => el('li', {},
            r.methods.map((m) => el('span', { class: 'md-method md-method-' + m.toLowerCase() }, m)),
            el('code', {}, r.path)))));
}

function packagesSection(packages) {
    const missing = packages.filter((p) => !p.ok).length;
    return section('Python packages', missing ? missing + ' missing' : packages.length,
        el('ul', { class: 'md-packages' }, packages.map((p) => el('li', { class: p.ok ? '' : 'is-missing' },
            el('code', {}, p.requirement),
            el('span', {}, p.installed ? (p.ok ? p.installed : p.installed + ' (doesn’t fit)') : 'not installed')))));
}

function archiveSection(archive) {
    return section('Archive', null, el('dl', { class: 'md-facts' },
        el('dt', {}, 'File'), el('dd', {}, archive.file + ' · ' + formatSize(archive.size)),
        el('dt', {}, 'SHA-256'), el('dd', {}, el('code', { class: 'md-hash', title: archive.sha256 }, archive.sha256))));
}

function readmeSection(readme) {
    const node = section('README', null, el('div', { class: 'md-readme markdown' }, renderMarkdown(readme)));
    // Diagrams are drawn once the README is opened, so the library loads only when needed.
    node.addEventListener('toggle', () => { if (node.open) drawDiagrams(node); });
    return node;
}

function renderModuleDetails(d) {
    $('#md-title').textContent = d.display_name;
    $('#md-sub').textContent = ['v' + d.version, d.author ? 'by ' + d.author : null].filter(Boolean).join(' · ');

    const kind = STATE_CLASS[d.state.code] || 'info';
    $('#md-body').replaceChildren(...[
        el('div', { class: 'md-state md-state-' + kind }, d.state.message),
        d.state.reason && el('pre', { class: 'md-reason' }, d.state.reason),
        d.description && el('p', { class: 'md-desc' }, d.description),
        facts(d),
        d.routes.length && routesSection(d.routes),
        d.packages.length && packagesSection(d.packages),
        d.archive && archiveSection(d.archive),
        d.readme && readmeSection(d.readme),
    ].filter(Boolean));

    if (d.source === 'plugins') {  // changed on disk, not from the console
        $('#md-actions').replaceChildren();
        return;
    }
    const summary = state.modules.find((m) => m.name === d.name) || d;
    const act = (action, label, cls) => el('button', {
        type: 'button', class: 'btn ' + cls,
        onclick: async () => {
            $('#module-dialog').close();
            await moduleAction(summary, action);
        },
    }, label);
    $('#md-actions').replaceChildren(
        act('uninstall', 'Uninstall…', 'btn-ghost md-danger'),
        el('span', { class: 'md-spacer' }),
        d.is_enabled ? act('disable', 'Disable', 'btn-outline') : act('enable', 'Enable', 'btn-primary'));
}

export async function openModuleDetails(name) {
    const dialog = $('#module-dialog');
    $('#md-title').textContent = name;
    $('#md-sub').textContent = '';
    $('#md-body').replaceChildren(el('div', { class: 'empty' }, 'Loading…'));
    $('#md-actions').replaceChildren();
    if (!dialog.open) dialog.showModal();
    try {
        renderModuleDetails(await api('/modules/' + encodeURIComponent(name)));
    } catch (e) {
        if (e.status === 401) { dialog.close(); return; }
        $('#md-body').replaceChildren(el('div', { class: 'empty' }, 'Could not load the details: ' + e.message));
    }
}

export function setupModuleDialog() {
    const dialog = $('#module-dialog');
    $('#md-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (e) => {
        if (e.target === dialog) dialog.close(); // click on the backdrop
    });
}

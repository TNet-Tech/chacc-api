// Installing, enabling, disabling and uninstalling modules.
import { api } from './api.js';
import { $, toast } from './dom.js';
import { loadAll } from './loader.js';
import { markPending } from './status.js';

function confirmAction(title, text, okLabel) {
    const dialog = $('#confirm-dialog');
    $('#confirm-title').textContent = title;
    $('#confirm-text').textContent = text;
    $('#confirm-ok').textContent = okLabel || 'Confirm';
    dialog.returnValue = '';
    dialog.showModal();
    return new Promise((resolve) => {
        dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
    });
}

function reportResult(data) {
    toast(data.message || 'Done.');
    for (const warning of data.warnings || []) toast(warning, 'warning');
    markPending();
}

function reportError(e) {
    if (e.status === 401 && e.message === 'Login cancelled.') return;
    let message = e.message;
    const missing = e.data && e.data.missing_dependencies;
    if (e.status === 409 && missing && missing.required && missing.required.length) {
        message += '\nInstall first: ' + missing.required.join(', ');
    }
    // ChaCC's own 413 has a detail; without one, a proxy in front of it refused the file.
    if (e.status === 413 && !(e.data && e.data.detail)) {
        message = 'The file is too large for the proxy in front of the server (for nginx, raise client_max_body_size).';
    }
    toast(message, 'error');
}

// action: 'enable', 'disable' or 'uninstall' (which asks first).
export async function moduleAction(module, action) {
    const name = module.name;
    if (action === 'uninstall') {
        const ok = await confirmAction(
            'Uninstall ' + (module.display_name || name) + '?',
            'This removes the module archive, its code and its database record. Its tables are kept.',
            'Uninstall'
        );
        if (!ok) return;
    }
    const method = action === 'uninstall' ? 'DELETE' : 'POST';
    try {
        const data = await api('/modules/' + encodeURIComponent(name) + '/' + action, { method });
        reportResult(data);
    } catch (e) {
        reportError(e);
    }
    await loadAll();
}

export async function upload(file) {
    if (!file) return;
    if (!file.name.endsWith('.chacc')) {
        toast('Choose a .chacc module package.', 'error');
        return;
    }
    const zone = $('#dropzone');
    const text = zone.querySelector('.dropzone-text');
    const original = text.innerHTML;
    zone.classList.add('is-busy');
    text.textContent = 'Installing ' + file.name + '… resolving dependencies can take a while.';
    try {
        const body = new FormData();
        body.append('file', file);
        reportResult(await api('/modules/', { method: 'POST', body }));
    } catch (e) {
        reportError(e);
    } finally {
        zone.classList.remove('is-busy');
        text.innerHTML = original;
        $('#upload-input').value = '';
    }
    await loadAll();
}

/*
 * The access gate: on a protected server the console shows nothing but the
 * login (or web console key) dialog until the server accepts the user.
 * On an unprotected server it shows a warning instead.
 */
import { api, authMethod, authenticate, login, logout } from './api.js';
import { $, toast } from './dom.js';
import { state } from './state.js';
import { fetchInfo, setStatus, showInfo } from './status.js';

const UNPROTECTED = 'This web console isn\'t protected: anyone who can reach it can manage modules. '
    + 'Set CHACC_CONSOLE_KEY or install the authentication module.';

// Shows the gate card and waits until its button succeeds.
function gate(text, label, action) {
    $('#gate-text').textContent = text;
    $('#gate').hidden = false;
    return new Promise((resolve) => {
        $('#gate-btn').textContent = label;
        $('#gate-btn').onclick = () => action().then(resolve, () => {});
    });
}

// Opens the dialog right away; if it's closed, the gate card offers it again.
async function ask(text, label, action) {
    try {
        await action();
    } catch (e) {
        await gate(text, label, action);
    }
}

// Reads the server's info (/.well-known/chacc); until it answers, only a retry button shows.
async function connect() {
    for (;;) {
        try {
            state.info = await fetchInfo();
            showInfo(state.info);
            return;
        } catch (e) {
            setStatus('error', 'Unreachable');
            document.body.classList.add('gated');
            await gate('Could not reach the server.', 'Try again', () => Promise.resolve());
        }
    }
}

// Resolves once the user may use the console.
export async function unlock() {
    await connect();
    const method = authMethod();
    if (method === 'none') {
        $('#gate').hidden = true;
        document.body.classList.remove('gated');
        toast(UNPROTECTED, 'warning', 15000);
        return;
    }
    document.body.classList.add('gated');
    for (;;) {
        try {
            await api('/system/access', { noLoginPrompt: true });
            break;
        } catch (e) {
            if (e.status === 401) {
                logout();
                if (method === 'key') await ask('Enter the web console key to continue.', 'Enter key', authenticate);
                else await ask('Log in to use the web console.', 'Log in', authenticate);
            } else if (e.status === 403) {
                await gate('Your account can\'t manage this server.', 'Log in as someone else', () => { logout(); return login(); });
            } else {
                await gate(e.message || 'Could not reach the server.', 'Try again', () => Promise.resolve());
            }
        }
    }
    $('#gate').hidden = true;
    document.body.classList.remove('gated');
}

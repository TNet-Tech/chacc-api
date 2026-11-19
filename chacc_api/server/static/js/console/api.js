/*
 * Calls to the core API, and the login or key they may need.
 *
 * When the authentication module is loaded, protected routes return 401
 * without a token; the console then shows the login dialog, stores the token
 * for this browser tab only (sessionStorage) and retries the request.
 * Without the module, a server with CHACC_CONSOLE_KEY asks for that key
 * instead (sent as X-ChaCC-Key, kept the same way).
 */
import { $, storage } from './dom.js';
import { state } from './state.js';

const API_PREFIX = (function () {
    const meta = document.querySelector('meta[name="chacc-api-prefix"]');
    const value = meta ? meta.content : '/api';
    return value.includes('{{') ? '/api' : value.replace(/\/+$/, '');
})();

const TOKEN_KEY = 'chacc_console_token';
const CONSOLE_KEY = 'chacc_console_key';
const KEY_HEADER = 'X-ChaCC-Key';

class ApiError extends Error {
    constructor(status, data, message) {
        super(message);
        this.status = status;
        this.data = data;
    }
}

function detailText(data, fallback) {
    if (!data) return fallback;
    const detail = data.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('\n');
    return data.message || fallback;
}

let loginPromise = null;

export function login() {
    if (loginPromise) return loginPromise;
    const dialog = $('#login-dialog');
    const form = $('#login-form');
    const error = $('#login-error');
    form.reset();
    const knownLogin = state.info && state.info.auth && state.info.auth.login_path;
    error.textContent = 'The server requires a login but no login endpoint is loaded. '
        + 'Check the server log: the authentication module may have failed to start.';
    error.hidden = Boolean(knownLogin);

    loginPromise = new Promise((resolve, reject) => {
        async function onSubmit(event) {
            event.preventDefault();
            const loginPath = state.info && state.info.auth && state.info.auth.login_path;
            if (!loginPath) {
                error.textContent = 'The server did not report a login endpoint.';
                error.hidden = false;
                return;
            }
            const submit = $('#login-submit');
            submit.disabled = true;
            try {
                const res = await fetch(loginPath, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: form.username.value, password: form.password.value }),
                });
                const data = await res.json().catch(() => null);
                if (!res.ok || !data || !data.access_token) {
                    throw new Error(detailText(data, 'Login failed (' + res.status + ').'));
                }
                storage.set(TOKEN_KEY, data.access_token);
                cleanup();
                dialog.close();
                updateAuthUi();
                resolve();
            } catch (e) {
                error.textContent = e.message;
                error.hidden = false;
            } finally {
                submit.disabled = false;
            }
        }
        function onCancel(event) {
            if (event) event.preventDefault();
            cleanup();
            dialog.close();
            reject(new ApiError(401, null, 'Login cancelled.'));
        }
        function cleanup() {
            form.removeEventListener('submit', onSubmit);
            $('#login-cancel').removeEventListener('click', onCancel);
            dialog.removeEventListener('cancel', onCancel);
            loginPromise = null;
        }
        form.addEventListener('submit', onSubmit);
        $('#login-cancel').addEventListener('click', onCancel);
        dialog.addEventListener('cancel', onCancel);
        dialog.showModal();
        form.username.focus();
    });
    return loginPromise;
}

// "login", "key" or "none": how the server protects the console.
export function authMethod() {
    const auth = state.info && state.info.auth;
    if (!auth) return 'none';
    return auth.method || (auth.required ? 'login' : 'none');
}

let keyPromise = null;

// Asks for the web console key and checks it with the server before keeping it.
export function enterKey() {
    if (keyPromise) return keyPromise;
    const dialog = $('#key-dialog');
    const form = $('#key-form');
    const error = $('#key-error');
    form.reset();
    error.hidden = true;

    keyPromise = new Promise((resolve, reject) => {
        async function onSubmit(event) {
            event.preventDefault();
            const key = form.key.value;
            const submit = $('#key-submit');
            submit.disabled = true;
            try {
                const res = await fetch(API_PREFIX + '/system/access', { cache: 'no-store', headers: { [KEY_HEADER]: encodeURIComponent(key) } });
                if (res.status === 401) throw new Error('That key isn\'t right.');
                if (!res.ok) throw new Error('Could not check the key (' + res.status + ').');
                storage.set(CONSOLE_KEY, key);
                cleanup();
                dialog.close();
                updateAuthUi();
                resolve();
            } catch (e) {
                error.textContent = e.message;
                error.hidden = false;
            } finally {
                submit.disabled = false;
            }
        }
        function onCancel(event) {
            if (event) event.preventDefault();
            cleanup();
            dialog.close();
            reject(new ApiError(401, null, 'Cancelled.'));
        }
        function cleanup() {
            form.removeEventListener('submit', onSubmit);
            $('#key-cancel').removeEventListener('click', onCancel);
            dialog.removeEventListener('cancel', onCancel);
            keyPromise = null;
        }
        form.addEventListener('submit', onSubmit);
        $('#key-cancel').addEventListener('click', onCancel);
        dialog.addEventListener('cancel', onCancel);
        dialog.showModal();
        form.key.focus();
    });
    return keyPromise;
}

// The login dialog, or the key dialog on a server protected by a key.
export function authenticate() {
    return authMethod() === 'key' ? enterKey() : login();
}

export function logout() {
    storage.remove(TOKEN_KEY);
    storage.remove(CONSOLE_KEY);
    updateAuthUi();
}

export function updateAuthUi() {
    $('#logout-btn').hidden = !(storage.get(TOKEN_KEY) || storage.get(CONSOLE_KEY));
}

/*
 * Calls `API_PREFIX + path` and returns the JSON body. Throws ApiError.
 * options.noLoginPrompt: report a 401 instead of opening the login (or key) dialog.
 */
export async function api(path, options, retried) {
    const opts = Object.assign({ cache: 'no-store' }, options || {});
    const headers = new Headers(opts.headers || {});
    const token = storage.get(TOKEN_KEY);
    if (token) headers.set('Authorization', 'Bearer ' + token);
    const key = storage.get(CONSOLE_KEY);
    // URL-encoded so keys with any characters fit in a header.
    if (key) headers.set(KEY_HEADER, encodeURIComponent(key));
    opts.headers = headers;

    const res = await fetch(API_PREFIX + path, opts);
    if (res.status === 401 && !retried && !(options && options.noLoginPrompt)) {
        storage.remove(TOKEN_KEY);
        storage.remove(CONSOLE_KEY);
        updateAuthUi();
        await authenticate();
        return api(path, options, true);
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data, detailText(data, 'Request failed (' + res.status + ').'));
    return data;
}

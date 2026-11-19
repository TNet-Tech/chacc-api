/*
 * Calls to the core API, and the login or key they may need.
 *
 * When the authentication module is loaded, protected routes return 401
 * without a valid token. The console first renews the access token with the
 * refresh token; only when that fails does it show the login dialog. Tokens
 * are kept in localStorage, so every tab of this browser shares the login.
 * The module rotates refresh tokens, so tabs take turns renewing (Web Locks)
 * and reuse a token another tab just got.
 *
 * Without the module, a server with CHACC_CONSOLE_KEY asks for that key
 * instead (sent as X-ChaCC-Key, kept the same way).
 */
import { $, shared } from './dom.js';
import { state } from './state.js';

const API_PREFIX = (function () {
    const meta = document.querySelector('meta[name="chacc-api-prefix"]');
    const value = meta ? meta.content : '/api';
    return value.includes('{{') ? '/api' : value.replace(/\/+$/, '');
})();

const TOKEN_KEY = 'chacc_console_token';
const REFRESH_KEY = 'chacc_console_refresh_token';
const CONSOLE_KEY = 'chacc_console_key';
const AUTH_KEYS = [TOKEN_KEY, REFRESH_KEY, CONSOLE_KEY];
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
                saveTokens(data);
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
                shared.set(CONSOLE_KEY, key);
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

function saveTokens(data) {
    shared.set(TOKEN_KEY, data.access_token);
    if (data.refresh_token) shared.set(REFRESH_KEY, data.refresh_token);
}

// The authentication module's route next to its login, e.g. .../authentication/refresh.
function authRoute(name) {
    const loginPath = state.info && state.info.auth && state.info.auth.login_path;
    return loginPath ? loginPath.replace(/\/login$/, '/' + name) : null;
}

let refreshPromise = null;

/*
 * Renews the access token with the refresh token. Resolves true when there is
 * a new token. `failedToken` is the access token the server just refused: if
 * another tab has already replaced it, that token is used instead.
 */
function refreshTokens(failedToken) {
    if (refreshPromise) return refreshPromise;
    async function renew() {
        const current = shared.get(TOKEN_KEY);
        if (current && current !== failedToken) return true;  // another tab renewed it
        const refreshToken = shared.get(REFRESH_KEY);
        const path = authRoute('refresh');
        if (!refreshToken || !path) return false;
        try {
            const res = await fetch(path, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
            const data = await res.json().catch(() => null);
            if (res.ok && data && data.access_token) {
                saveTokens(data);
                return true;
            }
            // Refused: maybe another tab used this refresh token a moment ago.
            return Boolean(shared.get(TOKEN_KEY)) && shared.get(TOKEN_KEY) !== failedToken;
        } catch (e) {
            return false;
        }
    }
    const locks = navigator.locks;  // only on HTTPS and localhost
    refreshPromise = (locks ? locks.request('chacc-console-refresh', renew) : renew())
        .finally(() => { refreshPromise = null; });
    return refreshPromise;
}

// Ends the session on the server too (best effort) and forgets it in every tab.
export function logout() {
    const refreshToken = shared.get(REFRESH_KEY);
    const path = authRoute('revoke');
    if (refreshToken && path) {
        fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
            keepalive: true,
        }).catch(() => {});
    }
    forget();
}

// Forgets the stored login and key, without telling the server.
function forget() {
    for (const key of AUTH_KEYS) shared.remove(key);
    updateAuthUi();
}

export function updateAuthUi() {
    $('#logout-btn').hidden = !(shared.get(TOKEN_KEY) || shared.get(CONSOLE_KEY));
}

/*
 * Keeps tabs in step: logging out in one tab sends the others back to the
 * login, and logging in on one tab unlocks the others waiting at it.
 */
window.addEventListener('storage', (event) => {
    if (event.key !== null && !AUTH_KEYS.includes(event.key)) return;
    const loggedOut = !shared.get(TOKEN_KEY) && !shared.get(CONSOLE_KEY);
    const waiting = document.body.classList.contains('gated');
    if ((loggedOut && !waiting) || (!loggedOut && waiting)) location.reload();
});

/*
 * Calls `API_PREFIX + path` and returns the JSON body. Throws ApiError.
 * options.noLoginPrompt: report a 401 instead of opening the login (or key) dialog.
 */
export async function api(path, options, retried) {
    const opts = Object.assign({ cache: 'no-store' }, options || {});
    const headers = new Headers(opts.headers || {});
    const token = shared.get(TOKEN_KEY);
    if (token) headers.set('Authorization', 'Bearer ' + token);
    const key = shared.get(CONSOLE_KEY);
    // URL-encoded so keys with any characters fit in a header.
    if (key) headers.set(KEY_HEADER, encodeURIComponent(key));
    opts.headers = headers;

    const res = await fetch(API_PREFIX + path, opts);
    if (res.status === 401 && !retried) {
        // An expired access token is renewed quietly; a login is the last resort.
        if (token && await refreshTokens(token)) return api(path, options, true);
        forget();  // the session (or key) is no longer valid, in any tab
        if (!(options && options.noLoginPrompt)) {
            await authenticate();
            return api(path, options, true);
        }
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data, detailText(data, 'Request failed (' + res.status + ').'));
    return data;
}

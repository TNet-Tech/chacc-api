/*
 * Calls to the core API, and the login they may need.
 *
 * When the authentication module is loaded, protected routes return 401
 * without a token; the console then shows the login dialog, stores the token
 * for this browser tab only (sessionStorage) and retries the request.
 */
import { $, storage } from './dom.js';
import { state } from './state.js';

const API_PREFIX = (function () {
    const meta = document.querySelector('meta[name="chacc-api-prefix"]');
    const value = meta ? meta.content : '/api';
    return value.includes('{{') ? '/api' : value.replace(/\/+$/, '');
})();

const TOKEN_KEY = 'chacc_console_token';

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

export function logout() {
    storage.remove(TOKEN_KEY);
    updateAuthUi();
}

export function updateAuthUi() {
    $('#logout-btn').hidden = !storage.get(TOKEN_KEY);
}

/*
 * Calls `API_PREFIX + path` and returns the JSON body. Throws ApiError.
 * options.noLoginPrompt: report a 401 instead of opening the login dialog.
 */
export async function api(path, options, retried) {
    const opts = Object.assign({ cache: 'no-store' }, options || {});
    const headers = new Headers(opts.headers || {});
    const token = storage.get(TOKEN_KEY);
    if (token) headers.set('Authorization', 'Bearer ' + token);
    opts.headers = headers;

    const res = await fetch(API_PREFIX + path, opts);
    if (res.status === 401 && !retried && !(options && options.noLoginPrompt)) {
        storage.remove(TOKEN_KEY);
        updateAuthUi();
        await login();
        return api(path, options, true);
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data, detailText(data, 'Request failed (' + res.status + ').'));
    return data;
}

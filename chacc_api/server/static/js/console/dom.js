// Small DOM helpers shared by the console.

export const $ = (sel) => document.querySelector(sel);

export function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class') node.className = value;
        else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
}

export function svg(tag, attrs, ...children) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
    for (const child of children.flat()) {
        if (child === null || child === undefined) continue;
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
}

function safeStore(area) {
    return {
        get(key) { try { return area().getItem(key); } catch (e) { return null; } },
        set(key, value) { try { area().setItem(key, value); } catch (e) { /* ignore */ } },
        remove(key) { try { area().removeItem(key); } catch (e) { /* ignore */ } },
    };
}

// sessionStorage (this tab) and localStorage (all tabs) that never throw
// (private windows, blocked storage).
export const storage = safeStore(() => sessionStorage);
export const shared = safeStore(() => localStorage);

export function toast(message, kind, ms) {
    const node = el('div', { class: 'toast' + (kind ? ' toast-' + kind : ''), role: kind === 'error' ? 'alert' : 'status' }, message);
    $('#toasts').append(node);
    setTimeout(() => node.remove(), ms || (kind === 'error' ? 9000 : 6000));
}

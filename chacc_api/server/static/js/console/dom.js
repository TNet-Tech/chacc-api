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

// sessionStorage that never throws (private windows, blocked storage).
export const storage = {
    get(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } },
    set(key, value) { try { sessionStorage.setItem(key, value); } catch (e) { /* ignore */ } },
    remove(key) { try { sessionStorage.removeItem(key); } catch (e) { /* ignore */ } },
};

export function toast(message, kind) {
    const node = el('div', { class: 'toast' + (kind ? ' toast-' + kind : ''), role: kind === 'error' ? 'alert' : 'status' }, message);
    $('#toasts').append(node);
    setTimeout(() => node.remove(), kind === 'error' ? 9000 : 6000);
}

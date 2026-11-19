// The small menu that opens from a row's "⋮" button.
import { $, el, svg } from './dom.js';

const ICONS = {
    details: '<circle cx="12" cy="12" r="9"></circle><line x1="12" y1="11" x2="12" y2="16"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>',
    enable: '<polygon points="6 4 20 12 6 20 6 4"></polygon>',
    disable: '<rect x="6" y="4" width="4" height="16" rx="1"></rect><rect x="14" y="4" width="4" height="16" rx="1"></rect>',
    uninstall: '<polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6M14 11v6"></path><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>',
};

function menuIcon(name) {
    const icon = svg('svg', { viewBox: '0 0 24 24', 'aria-hidden': 'true' });
    icon.innerHTML = ICONS[name]; // fixed markup from ICONS above
    return icon;
}

let menuOwner = null;

export function closeMenu() {
    const menu = $('#row-menu');
    if (menu.hidden) return;
    menu.hidden = true;
    if (menuOwner) menuOwner.setAttribute('aria-expanded', 'false');
    menuOwner = null;
}

/*
 * Opens the menu under `button` (or closes it when it's already open there).
 * items: [{ icon, label, onSelect, kind }], kind: 'primary' or 'danger'.
 */
export function openMenu(button, items) {
    if (menuOwner === button) { closeMenu(); return; }
    closeMenu();
    const menu = $('#row-menu');
    menu.replaceChildren(...items.map((item) => el('button', {
        type: 'button', role: 'menuitem', class: 'menu-item' + (item.kind ? ' menu-item-' + item.kind : ''),
        onclick: () => { closeMenu(); item.onSelect(); },
    }, menuIcon(item.icon), item.label)));
    menu.hidden = false;
    const rect = button.getBoundingClientRect();
    const width = menu.offsetWidth;
    const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
    let top = rect.bottom + 6;
    if (top + menu.offsetHeight > window.innerHeight - 8) top = rect.top - menu.offsetHeight - 6;
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';
    button.setAttribute('aria-expanded', 'true');
    menuOwner = button;
    menu.querySelector('.menu-item').focus();
}

document.addEventListener('click', (e) => {
    if (menuOwner && !e.target.closest('#row-menu') && !menuOwner.contains(e.target)) closeMenu();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menuOwner) { const owner = menuOwner; closeMenu(); owner.focus(); }
});
window.addEventListener('resize', closeMenu);
window.addEventListener('scroll', closeMenu, true);

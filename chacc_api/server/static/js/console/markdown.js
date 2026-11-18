/*
 * A small Markdown viewer for module READMEs.
 *
 * READMEs come from installed modules, so they are not trusted: the output is
 * built from DOM nodes and text only (never innerHTML),
 * raw HTML tags are dropped (their text stays), and links and images
 * are kept only for http(s) and mailto URLs.
 *
 * Supports: headings, paragraphs, emphasis, strikethrough, inline code, fenced
 * code, links, autolinks, images, block quotes, nested and task lists, tables
 * and horizontal rules.
 *
 * Mermaid code blocks become diagrams: renderMarkdown() keeps their source and
 * drawDiagrams(container) draws them, loading the bundled Mermaid library the
 * first time one is shown.
 *
 * Usage: renderMarkdown(text) -> DocumentFragment
 *        drawDiagrams(element) -> Promise
 */

function h(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
        if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of [].concat(children || [])) {
        if (child === null || child === undefined) continue;
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
}

function safeUrl(url) {
    const value = (url || '').trim().replace(/^<(.*)>$/, '$1');
    return /^(https?:\/\/|mailto:)/i.test(value) ? value : null;
}

/* ---------- inline ---------- */

const PUNCTUATION = '\\`*_{}[]()#+-.!|~<>"\'';

// Finds the "]" that closes the "[" at `start`, allowing nested brackets.
function closingBracket(text, start) {
    let depth = 0;
    for (let i = start; i < text.length; i++) {
        if (text[i] === '\\') { i++; continue; }
        if (text[i] === '[') depth++;
        else if (text[i] === ']' && --depth === 0) return i;
    }
    return -1;
}

// Parses "(url "title")" at `start`; returns { url, title, end } or null.
function linkTarget(text, start) {
    if (text[start] !== '(') return null;
    let depth = 0;
    for (let i = start; i < text.length; i++) {
        if (text[i] === '\\') { i++; continue; }
        if (text[i] === '(') depth++;
        else if (text[i] === ')' && --depth === 0) {
            const inner = text.slice(start + 1, i).trim();
            const m = inner.match(/^(\S+?)(?:\s+["'(](.*)["')])?$/);
            return m ? { url: m[1], title: m[2] || null, end: i + 1 } : null;
        }
    }
    return null;
}

function isWordChar(ch) {
    return !!ch && /[\p{L}\p{N}]/u.test(ch);
}

// Finds the closing delimiter for emphasis that opened at `from`.
function closingDelimiter(text, delim, from) {
    let i = from;
    while ((i = text.indexOf(delim, i)) !== -1) {
        const before = text[i - 1];
        const after = text[i + delim.length];
        const single = delim.length === 1;
        const doubled = single && (after === delim || before === delim);
        const underscoreOk = delim[0] !== '_' || !isWordChar(after);
        if (i > from && before !== ' ' && before !== '\\' && !doubled && underscoreOk) return i;
        i += doubled ? 2 : 1;
    }
    return -1;
}

function inline(text) {
    const out = [];
    let buffer = '';
    const flush = () => {
        if (buffer) out.push(document.createTextNode(buffer));
        buffer = '';
    };
    const push = (node) => { flush(); out.push(node); };

    let i = 0;
    while (i < text.length) {
        const ch = text[i];
        const rest = text.slice(i);

        if (ch === '\\' && i + 1 < text.length) {
            if (text[i + 1] === '\n') { push(h('br')); i += 2; continue; }
            if (PUNCTUATION.includes(text[i + 1])) { buffer += text[i + 1]; i += 2; continue; }
        }

        if (ch === '\n') {
            if (buffer.endsWith('  ')) { buffer = buffer.replace(/ +$/, ''); push(h('br')); }
            else buffer += ' ';
            i++;
            continue;
        }

        if (ch === '`') {
            const run = rest.match(/^`+/)[0];
            const end = text.indexOf(run, i + run.length);
            if (end !== -1) {
                let code = text.slice(i + run.length, end).replace(/\n/g, ' ');
                if (/^ .* $/.test(code)) code = code.slice(1, -1);
                push(h('code', {}, code));
                i = end + run.length;
                continue;
            }
            buffer += run;
            i += run.length;
            continue;
        }

        if (ch === '!' && text[i + 1] === '[' || ch === '[') {
            const image = ch === '!';
            const open = image ? i + 1 : i;
            const close = closingBracket(text, open);
            const target = close !== -1 ? linkTarget(text, close + 1) : null;
            if (target) {
                const label = text.slice(open + 1, close);
                const url = safeUrl(target.url);
                if (image) {
                    push(url
                        ? h('img', { src: url, alt: label, title: target.title, loading: 'lazy', referrerpolicy: 'no-referrer' })
                        : document.createTextNode(label));
                } else if (url) {
                    push(h('a', { href: url, title: target.title, target: '_blank', rel: 'noopener noreferrer' }, inline(label)));
                } else {
                    // Relative or unknown links can't be opened from the console.
                    flush();
                    out.push(...inline(label));
                }
                i = target.end;
                continue;
            }
        }

        if (ch === '<') {
            const auto = rest.match(/^<((?:https?:\/\/|mailto:)[^\s<>]+)>/i);
            if (auto) {
                push(h('a', { href: auto[1], target: '_blank', rel: 'noopener noreferrer' }, auto[1].replace(/^mailto:/i, '')));
                i += auto[0].length;
                continue;
            }
            const br = rest.match(/^<br\s*\/?>/i);
            if (br) { push(h('br')); i += br[0].length; continue; }
            // Other HTML isn't rendered: drop the tag, keep the text around it.
            const tag = rest.match(/^<\/?[a-z][a-z0-9-]*(?:\s[^<>]*)?\/?>/i);
            if (tag) { i += tag[0].length; continue; }
        }

        if ((ch === 'h' || ch === 'w') && !isWordChar(text[i - 1])) {
            const bare = rest.match(/^(?:https?:\/\/|www\.)[^\s<]*[^\s<.,:;"')\]!?*_~]/i);
            if (bare) {
                const href = bare[0].startsWith('www.') ? 'https://' + bare[0] : bare[0];
                push(h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, bare[0]));
                i += bare[0].length;
                continue;
            }
        }

        const emphasis = rest.match(/^(\*\*|__|~~|\*|_)/);
        if (emphasis && text[i + emphasis[0].length] && !/\s/.test(text[i + emphasis[0].length])) {
            const delim = emphasis[0];
            const leftFlanking = delim[0] !== '_' || !isWordChar(text[i - 1]);
            const end = leftFlanking ? closingDelimiter(text, delim, i + delim.length) : -1;
            if (end !== -1) {
                const tag = delim === '~~' ? 'del' : delim.length === 2 ? 'strong' : 'em';
                push(h(tag, {}, inline(text.slice(i + delim.length, end))));
                i = end + delim.length;
                continue;
            }
        }

        buffer += ch;
        i++;
    }
    flush();
    return out;
}

/* ---------- blocks ---------- */

const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([^`\s]*)/;
const HEADING = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/;
const RULE = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
const QUOTE = /^ {0,3}> ?/;
const LIST_ITEM = /^( {0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)(.*)$/;
const TABLE_DIVIDER = /^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/;

function startsBlock(line) {
    return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line) || LIST_ITEM.test(line);
}

function splitRow(line) {
    let row = line.trim();
    if (row.startsWith('|')) row = row.slice(1);
    if (row.endsWith('|') && !row.endsWith('\\|')) row = row.slice(0, -1);
    const cells = [];
    let cell = '';
    for (let i = 0; i < row.length; i++) {
        if (row[i] === '\\' && row[i + 1] === '|') { cell += '|'; i++; }
        else if (row[i] === '|') { cells.push(cell.trim()); cell = ''; }
        else cell += row[i];
    }
    cells.push(cell.trim());
    return cells;
}

function table(header, divider, rows) {
    const align = splitRow(divider).map((c) => (c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : c.startsWith(':') ? 'left' : null));
    const cell = (tag, text, col) => h(tag, { style: align[col] ? 'text-align:' + align[col] : null }, inline(text));
    const heads = splitRow(header);
    return h('div', { class: 'md-table-wrap' }, h('table', {}, [
        h('thead', {}, h('tr', {}, heads.map((text, col) => cell('th', text, col)))),
        h('tbody', {}, rows.map((row) => {
            const cells = splitRow(row);
            return h('tr', {}, heads.map((_, col) => cell('td', cells[col] || '', col)));
        })),
    ]));
}

function indentOf(line) {
    return line.match(/^ */)[0].length;
}

function list(lines, start) {
    const first = lines[start].match(LIST_ITEM);
    const ordered = /\d/.test(first[2]);
    const marker = ordered ? first[2].slice(-1) : first[2];
    const items = [];
    let loose = false;
    let i = start;

    while (i < lines.length) {
        const m = lines[i].match(LIST_ITEM);
        const sameKind = m && (ordered ? /\d/.test(m[2]) && m[2].slice(-1) === marker : m[2] === marker);
        if (!sameKind || m[1].length > indentOf(lines[start]) + 1) break;

        const offset = m[1].length + m[2].length + Math.min(m[3].length || 1, 4);
        const body = [m[4]];
        i++;
        while (i < lines.length) {
            const line = lines[i];
            if (!line.trim()) {
                const next = lines.slice(i + 1).find((l) => l.trim());
                if (next !== undefined && indentOf(next) >= offset) { body.push(''); i++; continue; }
                break;
            }
            if (indentOf(line) >= offset) { body.push(line.slice(offset)); i++; continue; }
            if (body[body.length - 1].trim() && !startsBlock(line)) { body.push(line.trim()); i++; continue; }
            break;
        }
        items.push({ number: m[2], body });

        // A blank line between items makes the list loose (paragraphs keep their spacing).
        if (i < lines.length && !lines[i].trim()) {
            let j = i;
            while (j < lines.length && !lines[j].trim()) j++;
            const next = j < lines.length && lines[j].match(LIST_ITEM);
            if (next && (ordered ? /\d/.test(next[2]) : next[2] === marker) && next[1].length <= indentOf(lines[start]) + 1) {
                loose = true;
                i = j;
                continue;
            }
            break;
        }
    }
    if (items.some((item) => item.body.slice(0, -1).some((l) => !l.trim()))) loose = true;

    const listItems = items.map((item) => {
        let body = item.body;
        let checkbox = null;
        const task = body[0].match(/^\[([ xX])\][ \t]+(.*)$/);
        if (task) {
            checkbox = h('input', { type: 'checkbox', disabled: true, checked: task[1] !== ' ' });
            body = [task[2]].concat(body.slice(1));
        }
        let children = blocks(body);
        if (!loose) children = children.flatMap((node) => (node.tagName === 'P' ? [...node.childNodes] : [node]));
        return h('li', { class: checkbox ? 'md-task' : null }, [checkbox, checkbox ? ' ' : null].concat(children));
    });
    const startAt = ordered ? parseInt(items[0].number, 10) : 1;
    const node = h(ordered ? 'ol' : 'ul', { start: ordered && startAt !== 1 ? startAt : null }, listItems);
    return { node, next: i };
}

function blocks(lines) {
    const out = [];
    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        if (!line.trim()) { i++; continue; }

        let m = line.match(FENCE);
        if (m) {
            const fence = m[1];
            const closing = new RegExp('^ {0,3}' + (fence[0] === '`' ? '`' : '~') + '{' + fence.length + ',}\\s*$');
            const code = [];
            i++;
            while (i < lines.length && !closing.test(lines[i])) code.push(lines[i++]);
            i++;
            const codeBlock = h('pre', {}, h('code', { class: m[2] ? 'language-' + m[2] : null }, code.join('\n')));
            // Diagrams start as their source; drawDiagrams() replaces them with drawings.
            out.push(m[2].toLowerCase() === 'mermaid'
                ? h('div', { class: 'md-diagram', 'data-source': code.join('\n') }, codeBlock)
                : codeBlock);
            continue;
        }

        m = line.match(HEADING);
        if (m) {
            out.push(h('h' + m[1].length, {}, inline(m[2] || '')));
            i++;
            continue;
        }

        if (RULE.test(line)) { out.push(h('hr')); i++; continue; }

        if (QUOTE.test(line)) {
            const quoted = [];
            while (i < lines.length && lines[i].trim() && (QUOTE.test(lines[i]) || !startsBlock(lines[i]))) {
                quoted.push(lines[i].replace(QUOTE, ''));
                i++;
            }
            out.push(h('blockquote', {}, blocks(quoted)));
            continue;
        }

        if (LIST_ITEM.test(line)) {
            const result = list(lines, i);
            out.push(result.node);
            i = result.next;
            continue;
        }

        if (line.includes('|') && i + 1 < lines.length && TABLE_DIVIDER.test(lines[i + 1]) && lines[i + 1].includes('-')) {
            const rows = [];
            let j = i + 2;
            while (j < lines.length && lines[j].trim() && lines[j].includes('|')) rows.push(lines[j++]);
            out.push(table(line, lines[i + 1], rows));
            i = j;
            continue;
        }

        if (/^ {4,}/.test(line)) {
            const code = [];
            while (i < lines.length && (/^ {4,}/.test(lines[i]) || (!lines[i].trim() && /^ {4,}/.test(lines[i + 1] || '')))) {
                code.push(lines[i].slice(4));
                i++;
            }
            out.push(h('pre', {}, h('code', {}, code.join('\n'))));
            continue;
        }

        const para = [line.trim()];
        i++;
        while (i < lines.length && lines[i].trim() && !startsBlock(lines[i])) {
            if (/^ {0,3}=+[ \t]*$/.test(lines[i]) || /^ {0,3}-+[ \t]*$/.test(lines[i])) break;
            para.push(lines[i].trim());
            i++;
        }
        const underline = lines[i] && lines[i].match(/^ {0,3}(=+|-+)[ \t]*$/);
        if (underline) {
            out.push(h(underline[1][0] === '=' ? 'h1' : 'h2', {}, inline(para.join('\n'))));
            i++;
            continue;
        }
        const content = inline(para.join('\n'));
        if (content.some((node) => node.nodeType !== Node.TEXT_NODE || node.textContent.trim())) out.push(h('p', {}, content));
    }
    return out;
}

export function renderMarkdown(text) {
    const source = String(text || '')
        .replace(/\r\n?/g, '\n')
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/\t/g, '    ');
    const fragment = document.createDocumentFragment();
    fragment.append(...blocks(source.split('\n')));
    return fragment;
}

/* ---------- Mermaid diagrams ---------- */

// Bundled with the console (see ../vendor/README.md), loaded the first time a diagram is shown.
const MERMAID_URL = '/static/js/vendor/mermaid-11.17.2.min.js';
let mermaidReady = null;
let diagramCount = 0;

function loadMermaid() {
    if (!mermaidReady) {
        mermaidReady = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = MERMAID_URL;
            script.onload = () => {
                // strict: no scripts, click handlers or raw HTML labels in diagrams.
                window.mermaid.initialize({
                    startOnLoad: false,
                    securityLevel: 'strict',
                    theme: 'base',
                    fontFamily: 'inherit',
                    // The console's colours (see console.css :root).
                    themeVariables: {
                        darkMode: true,
                        background: '#26343D',
                        primaryColor: '#123B40',
                        primaryTextColor: '#F2F5F8',
                        primaryBorderColor: '#00A9AA',
                        secondaryColor: '#212D35',
                        tertiaryColor: '#1A242B',
                        lineColor: '#AEB9C2',
                        textColor: '#F2F5F8',
                        noteBkgColor: '#1D3438',
                        noteTextColor: '#F2F5F8',
                        noteBorderColor: '#2F3F4A',
                        edgeLabelBackground: '#26343D',
                    },
                });
                resolve(window.mermaid);
            };
            script.onerror = () => {
                mermaidReady = null; // try again next time
                reject(new Error('The diagram library could not be loaded.'));
            };
            document.head.append(script);
        });
    }
    return mermaidReady;
}

function diagramFailed(block, message) {
    block.classList.add('is-failed');
    block.prepend(h('p', { class: 'md-diagram-note' }, message));
}

/*
 * Draws the Mermaid diagrams inside `container`. Call it when they become
 * visible. A diagram that can't be drawn keeps its source with a short note.
 */
export async function drawDiagrams(container) {
    const blocks = [...container.querySelectorAll('.md-diagram:not(.is-drawn):not(.is-failed)')];
    if (!blocks.length) return;
    blocks.forEach((block) => block.classList.add('is-drawn'));
    let mermaid;
    try {
        mermaid = await loadMermaid();
    } catch (error) {
        blocks.forEach((block) => { block.classList.remove('is-drawn'); diagramFailed(block, 'Couldn’t draw this diagram: ' + error.message); });
        return;
    }
    for (const block of blocks) {
        const id = 'chacc-diagram-' + ++diagramCount;
        try {
            // Mermaid cleans the SVG it returns (DOMPurify) under securityLevel 'strict'.
            const { svg } = await mermaid.render(id, block.dataset.source);
            const drawing = h('div', { class: 'md-diagram-drawing', role: 'img', 'aria-label': 'Diagram' });
            drawing.innerHTML = svg;
            block.replaceChildren(drawing);
        } catch (error) {
            block.classList.remove('is-drawn');
            const detail = String((error && error.message) || error).split('\n')[0].replace(/[\s:.]+$/, '');
            diagramFailed(block, 'Couldn’t draw this diagram' + (detail ? ': ' + detail + '.' : '.'));
        } finally {
            // Mermaid leaves its scratch element behind when a diagram has an error.
            const scratch = document.getElementById('d' + id);
            if (scratch) scratch.remove();
        }
    }
}

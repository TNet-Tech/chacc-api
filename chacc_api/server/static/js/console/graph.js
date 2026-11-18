// The Dependencies tab: modules as boxes, arrows to what they depend on.
import { $, el, svg } from './dom.js';
import { state } from './state.js';

const NODE_W = 220;
const NODE_H = 54;
const COL_GAP = 90;
const ROW_GAP = 22;
const PAD = 12;

// Columns by dependency depth: a module sits right of everything it depends on.
function layout(nodes, edges) {
    const deps = new Map(nodes.map((n) => [n.name, []]));
    for (const e of edges) if (deps.has(e.from) && deps.has(e.to)) deps.get(e.from).push(e.to);
    const level = new Map();
    function depth(name, seen) {
        if (level.has(name)) return level.get(name);
        if (seen.has(name)) return 0; // cycle: stop here
        seen.add(name);
        let d = 0;
        for (const dep of deps.get(name)) d = Math.max(d, depth(dep, seen) + 1);
        seen.delete(name);
        level.set(name, d);
        return d;
    }
    nodes.forEach((n) => depth(n.name, new Set()));

    const columns = [];
    for (const n of nodes) (columns[level.get(n.name)] = columns[level.get(n.name)] || []).push(n);
    const pos = new Map();
    columns.forEach((col, x) => {
        col.sort((a, b) => a.name.localeCompare(b.name));
        col.forEach((n, y) => pos.set(n.name, { x: PAD + x * (NODE_W + COL_GAP), y: PAD + y * (NODE_H + ROW_GAP) }));
    });
    const width = PAD * 2 + Math.max(1, columns.length) * NODE_W + Math.max(0, columns.length - 1) * COL_GAP;
    const height = PAD * 2 + Math.max(1, ...columns.map((c) => c.length)) * (NODE_H + ROW_GAP) - ROW_GAP;
    return { pos, width, height };
}

function truncate(text, max) {
    return text.length > max ? text.slice(0, max - 1) + '…' : text;
}

function arrowMarkers() {
    const defs = svg('defs');
    for (const [id, cls] of [['arrow', 'arrow'], ['arrow-broken', 'arrow-broken'], ['arrow-broken-opt', 'arrow-broken-opt']]) {
        defs.append(svg('marker', { id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' },
            svg('path', { d: 'M 0 0 L 10 5 L 0 10 z', class: cls })));
    }
    return defs;
}

function edgesLayer(edges, pos) {
    const layer = svg('g');
    for (const e of edges) {
        const a = pos.get(e.from);
        const b = pos.get(e.to);
        if (!a || !b) continue;
        const optional = e.kind === 'optional';
        const broken = !e.satisfied;
        const x1 = a.x;
        const y1 = a.y + NODE_H / 2;
        const x2 = b.x + NODE_W;
        const y2 = b.y + NODE_H / 2;
        const bend = Math.max(40, Math.abs(x1 - x2) / 2);
        const marker = broken ? (optional ? 'arrow-broken-opt' : 'arrow-broken') : 'arrow';
        const path = svg('path', {
            d: 'M ' + x1 + ' ' + y1 + ' C ' + (x1 - bend) + ' ' + y1 + ', ' + (x2 + bend) + ' ' + y2 + ', ' + x2 + ' ' + y2,
            class: 'edge' + (optional ? ' edge-optional' : '') + (broken ? ' edge-broken' : ''),
            'marker-end': 'url(#' + marker + ')',
        });
        path.append(svg('title', {}, e.from + ' ' + (optional ? 'optionally uses ' : 'requires ') + e.to + (broken ? ' (not available)' : '')));
        layer.append(path);
    }
    return layer;
}

const NODE_LABELS = { ok: 'loads', blocked: 'blocked', disabled: 'disabled', missing: 'not installed' };

function nodeBox(n, p) {
    return svg('g', { class: 'node node-' + n.state, transform: 'translate(' + p.x + ',' + p.y + ')' },
        svg('title', {}, n.name + ' (' + NODE_LABELS[n.state] + ')' + (n.reason ? ': ' + n.reason : '')),
        svg('rect', { width: NODE_W, height: NODE_H, rx: 10 }),
        svg('text', { x: 12, y: 22 }, truncate(n.display_name || n.name, 27)),
        svg('text', { x: 12, y: 40, class: 'sub' }, truncate(n.state === 'missing' ? 'not installed' : n.name + (n.version ? ' · v' + n.version : ''), 28)));
}

function problemList(graph) {
    const problems = [];
    for (const n of graph.nodes) {
        if (n.state === 'blocked') {
            problems.push(el('div', { class: 'problem' },
                el('strong', {}, n.name), ' will not load: ' + n.reason,
                el('div', { class: 'problem-fix' }, 'To fix: ' + graph.how_to_fix + ', then restart the server.')));
        } else if (n.state === 'ok' && n.missing_optional.length) {
            problems.push(el('div', { class: 'problem is-warning' },
                el('strong', {}, n.name), ' loads with fewer features. Optional module(s) not installed: ' + n.missing_optional.join(', ') + '.'));
        }
    }
    return problems.length
        ? el('div', { class: 'problems' }, problems)
        : el('p', { class: 'all-good' }, 'All dependencies are satisfied.');
}

export function renderGraph() {
    const graph = state.graph;
    const root = $('#graph');
    root.replaceChildren();
    $('#graph-problems').replaceChildren();
    $('#load-order').replaceChildren();
    const hasGraph = Boolean(graph && graph.nodes.length);
    document.querySelector('.legend').hidden = !hasGraph;
    $('.graph-wrap').hidden = !hasGraph;
    if (!graph) {
        $('#graph-intro').textContent = '';
        return;
    }

    $('#graph-intro').textContent = graph.mode === 'production'
        ? 'Installed production modules (from ' + graph.source + '). Arrows point from a module to the modules it depends on.'
        : 'Development mode: modules in ' + graph.source + '. Arrows point from a module to the modules it depends on.';

    if (!graph.nodes.length) {
        root.setAttribute('width', 0);
        root.setAttribute('height', 0);
        $('#graph-problems').append(el('div', { class: 'empty' }, 'No modules installed.'));
        return;
    }

    const { pos, width, height } = layout(graph.nodes, graph.edges);
    root.setAttribute('width', width);
    root.setAttribute('height', height);
    root.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    root.append(arrowMarkers(), edgesLayer(graph.edges, pos), ...graph.nodes.map((n) => nodeBox(n, pos.get(n.name))));

    $('#graph-problems').append(problemList(graph));
    if (graph.load_order.length) {
        $('#load-order').append('Load order', el('ol', {}, graph.load_order.map((name) => el('li', {}, el('code', {}, name)))));
    }
}

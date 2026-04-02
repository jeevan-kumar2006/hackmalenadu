/* ============================================
   Lokus-Synapse — Frontend Application
   ============================================ */

const API = '';  // Same origin — Flask serves frontend

// ── State ──
const state = {
    graphMode: 'files',        // 'files' | 'concepts'
    graphLayout: 'force',      // 'force' | 'hierarchical'
    graphFilter: 'all',        // 'all' | 'code' | 'notes'
    similarityThreshold: 0.08,
    vaultPath: null,
    scanPoll: null,
    network: null,
    allNodes: [],
    allEdges: [],
    files: [],
    selectedNodeId: null,
    sidebarOpen: true,
    detailsOpen: true,
};

// ── DOM References ──
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    welcomeScreen: $('#welcomeScreen'),
    workspace: $('#workspace'),
    scanDialog: $('#scanDialog'),
    scanOverlay: $('#scanOverlay'),
    scanPhaseText: $('#scanPhaseText'),
    scanCurrentFile: $('#scanCurrentFile'),
    scanProgressFill: $('#scanProgressFill'),
    scanStatsText: $('#scanStatsText'),
    vaultPath: $('#vaultPath'),
    searchInput: $('#searchInput'),
    searchResults: $('#searchResults'),
    fileTree: $('#fileTree'),
    sidebarStats: $('#sidebarStats'),
    graphContainer: $('#graphContainer'),
    graphEmpty: $('#graphEmpty'),
    detailsContent: $('#detailsContent'),
    detailsPanel: $('#detailsPanel'),
    statusCenter: $('#statusCenter'),
    statusFiles: $('#statusFiles'),
    statusConcepts: $('#statusConcepts'),
    statusEdges: $('#statusEdges'),
    toastContainer: $('#toastContainer'),
    similaritySlider: $('#similaritySlider'),
    similarityValue: $('#similarityValue'),
    welcomeCanvas: $('#welcomeCanvas'),
};

// ── File Extension Helpers ──

const EXT_COLORS = {
    '.py': 'var(--c-py)', '.c': 'var(--c-c)', '.h': 'var(--c-c)',
    '.cpp': 'var(--c-cpp)', '.hpp': 'var(--c-cpp)', '.cc': 'var(--c-cpp)', '.cxx': 'var(--c-cpp)',
    '.js': 'var(--c-js)', '.jsx': 'var(--c-js)', '.mjs': 'var(--c-js)',
    '.ts': 'var(--c-ts)', '.tsx': 'var(--c-ts)',
    '.java': 'var(--c-java)', '.kt': 'var(--c-java)',
    '.rs': 'var(--c-rs)',
    '.go': 'var(--c-go)',
    '.md': 'var(--c-md)', '.markdown': 'var(--c-md)', '.rst': 'var(--c-md)',
    '.txt': 'var(--c-txt)',
};

const EXT_ICONS = {
    '.py': 'fa-brands fa-python',
    '.c': 'fa-solid fa-c',
    '.h': 'fa-solid fa-c',
    '.cpp': 'fa-solid fa-c',
    '.hpp': 'fa-solid fa-c',
    '.cc': 'fa-solid fa-c',
    '.cxx': 'fa-solid fa-c',
    '.js': 'fa-brands fa-js',
    '.jsx': 'fa-brands fa-react',
    '.ts': 'fa-solid fa-code',
    '.tsx': 'fa-brands fa-react',
    '.java': 'fa-brands fa-java',
    '.rs': 'fa-solid fa-gear',
    '.go': 'fa-brands fa-golang',
    '.md': 'fa-solid fa-file-lines',
    '.txt': 'fa-solid fa-file-lines',
};

const NOTE_EXTS = new Set(['.md', '.markdown', '.rst', '.txt']);

function extColor(ext) { return EXT_COLORS[ext] || 'var(--c-default)'; }
function extIcon(ext) { return EXT_ICONS[ext] || 'fa-solid fa-file-code'; }
function isNote(ext) { return NOTE_EXTS.has(ext); }
function isCode(ext) { return !isNote(ext); }

// ── API Calls ──

async function apiGet(url) {
    const res = await fetch(API + url);
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    return res.json();
}

async function apiPost(url, body) {
    const res = await fetch(API + url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    return res.json();
}

// ── Toast Notifications ──

function toast(message, type = 'info', duration = 4000) {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    const icons = { info: 'fa-circle-info', success: 'fa-circle-check', error: 'fa-circle-xmark', warning: 'fa-triangle-exclamation' };
    el.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${message}</span>`;
    dom.toastContainer.appendChild(el);
    requestAnimationFrame(() => el.classList.add('visible'));
    setTimeout(() => {
        el.classList.remove('visible');
        setTimeout(() => el.remove(), 300);
    }, duration);
}

// ── Welcome Background Canvas ──

function initWelcomeCanvas() {
    const canvas = dom.welcomeCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, particles = [], mouse = { x: -1000, y: -1000 };
    const PARTICLE_COUNT = 80;

    function resize() {
        w = canvas.width = canvas.parentElement.clientWidth;
        h = canvas.height = canvas.parentElement.clientHeight;
    }

    function createParticles() {
        particles = [];
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            particles.push({
                x: Math.random() * w, y: Math.random() * h,
                vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4,
                r: Math.random() * 2 + 1,
            });
        }
    }

    function draw() {
        ctx.clearRect(0, 0, w, h);
        // Draw connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(0,229,160,${0.08 * (1 - dist / 150)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
        // Draw particles
        for (const p of particles) {
            // Mouse repulsion
            const mdx = p.x - mouse.x;
            const mdy = p.y - mouse.y;
            const mdist = Math.sqrt(mdx * mdx + mdy * mdy);
            if (mdist < 120 && mdist > 0) {
                p.vx += (mdx / mdist) * 0.15;
                p.vy += (mdy / mdist) * 0.15;
            }
            p.x += p.vx;
            p.y += p.vy;
            p.vx *= 0.99;
            p.vy *= 0.99;
            if (p.x < 0) p.x = w;
            if (p.x > w) p.x = 0;
            if (p.y < 0) p.y = h;
            if (p.y > h) p.y = 0;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0,229,160,0.35)';
            ctx.fill();
        }
        if (dom.welcomeScreen.style.display !== 'none') {
            requestAnimationFrame(draw);
        }
    }

    resize();
    createParticles();
    draw();

    window.addEventListener('resize', () => { resize(); createParticles(); });
    canvas.parentElement.addEventListener('mousemove', (e) => {
        const rect = canvas.parentElement.getBoundingClientRect();
        mouse.x = e.clientX - rect.left;
        mouse.y = e.clientY - rect.top;
    });
}

// ── Scan Dialog ──

function openScanDialog() {
    dom.scanDialog.classList.add('visible');
    if (state.vaultPath) dom.vaultPath.value = state.vaultPath;
    dom.vaultPath.focus();
}

function closeScanDialog() {
    dom.scanDialog.classList.remove('visible');
}

async function startScan(path) {
    closeScanDialog();
    dom.scanOverlay.style.display = 'flex';
    dom.scanPhaseText.textContent = 'Scanning Files...';
    dom.scanCurrentFile.textContent = 'Preparing...';
    dom.scanProgressFill.style.width = '0%';
    dom.scanStatsText.textContent = '0 / 0 files';

    try {
        await apiPost('/api/scan', { path: path });
        pollScanStatus();
    } catch (err) {
        dom.scanOverlay.style.display = 'none';
        toast(err.message, 'error');
    }
}

async function startDemo() {
    dom.scanOverlay.style.display = 'flex';
    dom.scanPhaseText.textContent = 'Generating Demo Data...';
    dom.scanCurrentFile.textContent = 'Creating sample files...';
    dom.scanProgressFill.style.width = '10%';
    dom.scanStatsText.textContent = 'Preparing...';

    try {
        await apiPost('/api/demo');
        pollScanStatus();
    } catch (err) {
        dom.scanOverlay.style.display = 'none';
        toast(err.message, 'error');
    }
}

function pollScanStatus() {
    if (state.scanPoll) clearInterval(state.scanPoll);
    state.scanPoll = setInterval(async () => {
        try {
            const s = await apiGet('/api/scan/status');
            const pct = s.total > 0 ? Math.round((s.scanned / s.total) * 100) : 0;
            dom.scanProgressFill.style.width = pct + '%';
            dom.scanStatsText.textContent = `${s.scanned} / ${s.total} files`;

            if (s.phase === 'extracting') {
                dom.scanPhaseText.textContent = 'Extracting Concepts...';
                dom.scanCurrentFile.textContent = s.current || 'Processing...';
            } else if (s.phase === 'building') {
                dom.scanPhaseText.textContent = 'Building Knowledge Graph...';
                dom.scanCurrentFile.textContent = s.current || 'Computing similarities...';
                dom.scanProgressFill.style.width = '90%';
            } else if (s.phase === 'done') {
                clearInterval(state.scanPoll);
                state.scanPoll = null;
                dom.scanProgressFill.style.width = '100%';
                setTimeout(() => {
                    dom.scanOverlay.style.display = 'none';
                    toast('Scan complete! Knowledge graph ready.', 'success');
                    showWorkspace();
                }, 500);
            } else if (s.phase === 'error') {
                clearInterval(state.scanPoll);
                state.scanPoll = null;
                dom.scanOverlay.style.display = 'none';
                toast('Scan error: ' + (s.error || 'Unknown error'), 'error');
            }
        } catch (err) {
            // Ignore polling errors (server might be busy)
        }
    }, 400);
}

// ── Show Workspace ──

async function showWorkspace() {
    dom.welcomeScreen.style.display = 'none';
    dom.workspace.style.display = 'flex';

    try {
        const [stats, files, graphData] = await Promise.all([
            apiGet('/api/stats'),
            apiGet('/api/files'),
            apiGet('/api/graph?mode=' + state.graphMode),
        ]);
        updateStatusBar(stats);
        state.files = files;
        renderFileTree(files);
        renderGraph(graphData);
    } catch (err) {
        toast('Failed to load data: ' + err.message, 'error');
    }
}

// ── Status Bar ──

function updateStatusBar(stats) {
    dom.statusFiles.textContent = stats.fileCount + ' files';
    dom.statusConcepts.textContent = stats.conceptCount + ' concepts';
    dom.statusEdges.textContent = stats.edgeCount + ' links';
}

// ── File Tree ──

function renderFileTree(files) {
    if (!files.length) {
        dom.fileTree.innerHTML = '<div class="tree-empty">No files found</div>';
        dom.sidebarStats.innerHTML = '';
        return;
    }

    // Build directory tree
    const tree = {};
    for (const f of files) {
        const parts = f.directory.split('/').filter(Boolean);
        let node = tree;
        for (const part of parts) {
            if (!node[part]) node[part] = { __files: [] };
            node = node[part];
        }
        node.__files = node.__files || [];
        node.__files.push(f);
    }

    let html = '';
    function renderNode(obj, depth) {
        const dirs = Object.keys(obj).filter(k => k !== '__files');
        dirs.sort();
        for (const dir of dirs) {
            const indent = depth * 16;
            html += `<div class="tree-dir" style="padding-left:${indent}px">
                <span class="tree-dir-toggle"><i class="fas fa-chevron-right"></i></span>
                <i class="fas fa-folder tree-dir-icon"></i>
                <span class="tree-dir-name">${dir}</span>
            </div>
            <div class="tree-dir-children">`;
            renderNode(obj[dir], depth + 1);
            html += '</div>';
        }
        const files = obj.__files || [];
        files.sort((a, b) => a.filename.localeCompare(b.filename));
        for (const f of files) {
            const indent = depth * 16;
            const color = extColor(f.extension);
            const icon = extIcon(f.extension);
            html += `<div class="tree-file" data-id="${f.id}" style="padding-left:${indent + 20}px"
                      title="${f.path}">
                <i class="${icon}" style="color:${color}"></i>
                <span class="tree-file-name">${f.filename}</span>
            </div>`;
        }
    }
    renderNode(tree, 0);
    dom.fileTree.innerHTML = html;

    // Directory toggle
    dom.fileTree.querySelectorAll('.tree-dir').forEach(el => {
        el.addEventListener('click', () => {
            el.classList.toggle('open');
            const children = el.nextElementSibling;
            if (children) children.style.display = el.classList.contains('open') ? 'block' : 'none';
        });
    });

    // File click → select node in graph
    dom.fileTree.querySelectorAll('.tree-file').forEach(el => {
        el.addEventListener('click', () => {
            const id = parseInt(el.dataset.id);
            selectGraphNode(id);
            el.classList.add('active');
            dom.fileTree.querySelectorAll('.tree-file.active').forEach(e => {
                if (e !== el) e.classList.remove('active');
            });
        });
    });

    // Stats
    const extCounts = {};
    for (const f of files) {
        extCounts[f.extension] = (extCounts[f.extension] || 0) + 1;
    }
    let statsHtml = '';
    for (const [ext, count] of Object.entries(extCounts).sort((a, b) => b[1] - a[1])) {
        statsHtml += `<div class="stat-row">
            <span class="stat-dot" style="background:${extColor(ext)}"></span>
            <span class="stat-ext">${ext}</span>
            <span class="stat-count">${count}</span>
        </div>`;
    }
    dom.sidebarStats.innerHTML = statsHtml;
}

// ── Graph Rendering ──

function renderGraph(data) {
    state.allNodes = data.nodes || [];
    state.allEdges = data.edges || [];
    applyFiltersAndRender();
}

function applyFiltersAndRender() {
    let nodes = [...state.allNodes];
    let edges = [...state.allEdges];

    // Filter by type
    if (state.graphFilter === 'code') {
        if (state.graphMode === 'files') {
            const codeIds = new Set(nodes.filter(n => !isNote(n.extension)).map(n => n.id));
            nodes = nodes.filter(n => codeIds.has(n.id));
            edges = edges.filter(e => codeIds.has(e.from) && codeIds.has(e.to));
        }
    } else if (state.graphFilter === 'notes') {
        if (state.graphMode === 'files') {
            const noteIds = new Set(nodes.filter(n => isNote(n.extension)).map(n => n.id));
            nodes = nodes.filter(n => noteIds.has(n.id));
            edges = edges.filter(e => noteIds.has(e.from) && noteIds.has(e.to));
        }
    }

    // Filter by similarity threshold
    edges = edges.filter(e => e.weight >= state.similarityThreshold);
    const edgeIds = new Set(edges.map(e => e.from + '-' + e.to));
    const connectedNodes = new Set();
    for (const e of edges) {
        connectedNodes.add(e.from);
        connectedNodes.add(e.to);
    }
    // Keep nodes that are connected OR are isolated (show as single nodes)
    if (edges.length > 0) {
        // Only show connected nodes when edges exist
        nodes = nodes.filter(n => connectedNodes.has(n.id));
    }

    if (nodes.length === 0) {
        dom.graphContainer.style.display = 'none';
        dom.graphEmpty.style.display = 'flex';
        if (state.network) { state.network.destroy(); state.network = null; }
        return;
    }

    dom.graphContainer.style.display = 'block';
    dom.graphEmpty.style.display = 'none';

    // Vis.js data
    const visNodes = new vis.DataSet(nodes.map(n => {
        const isConceptMode = state.graphMode === 'concepts';
        let color, shape, font, size;

        if (isConceptMode) {
            const catColors = {
                'keyword': { bg: '#1a3a2e', border: '#00e5a0' },
                'identifier': { bg: '#2a2a1a', border: '#ffd43b' },
                'function': { bg: '#1a2a3a', border: '#4da6ff' },
                'default': { bg: '#1a2438', border: '#5a6b84' },
            };
            const cc = catColors[n.category] || catColors['default'];
            color = { background: cc.bg, border: cc.border, highlight: { background: cc.border, border: cc.border } };
            shape = 'dot';
            size = Math.max(8, Math.min(30, (n.fileCount || 1) * 6));
            font = { color: '#e4e8f1', size: 11, face: 'IBM Plex Sans' };
        } else {
            const ec = extColor(n.extension);
            color = { background: '#0f1624', border: ec, highlight: { background: ec, border: ec }, hover: { background: '#1a2438', border: ec } };
            shape = 'dot';
            size = Math.max(10, Math.min(35, (n.conceptCount || 1) * 3 + 8));
            font = { color: '#e4e8f1', size: 11, face: 'IBM Plex Sans', strokeWidth: 3, strokeColor: '#0a0f1a' };
        }

        return {
            id: n.id, label: n.label, title: n.title || n.label,
            color, shape, font, size,
        };
    }));

    const visEdges = new vis.DataSet(edges.map(e => {
        const alpha = Math.min(1, e.weight * 1.5);
        const width = Math.max(0.5, Math.min(4, e.weight * 8));
        return {
            from: e.from, to: e.to,
            title: e.title || `Weight: ${e.weight.toFixed(3)}`,
            color: { color: `rgba(0,229,160,${alpha * 0.5})`, highlight: `rgba(0,229,160,${alpha})` },
            width,
            smooth: { type: 'continuous', roundness: 0.15 },
            arrows: { to: { enabled: false } },
        };
    }));

    const options = {
        physics: state.graphLayout === 'force' ? {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -60,
                centralGravity: 0.005,
                springLength: 140,
                springConstant: 0.04,
                damping: 0.4,
                avoidOverlap: 0.6,
            },
            stabilization: { iterations: 150, fit: true },
            maxVelocity: 30,
        } : {
            enabled: false,
        },
        layout: state.graphLayout === 'hierarchical' ? {
            hierarchical: {
                enabled: true,
                direction: 'LR',
                sortMethod: 'directed',
                levelSeparation: 200,
                nodeSpacing: 60,
            },
        } : {},
        interaction: {
            hover: true,
            tooltipDelay: 200,
            zoomView: true,
            dragView: true,
            multiselect: false,
            navigationButtons: false,
            keyboard: { enabled: true },
        },
        nodes: { borderWidthSelected: 2 },
        edges: { selectionWidth: 2 },
    };

    if (state.network) {
        state.network.setData({ nodes: visNodes, edges: visEdges });
        state.network.setOptions(options);
    } else {
        state.network = new vis.Network(dom.graphContainer, { nodes: visNodes, edges: visEdges }, options);
        state.network.on('click', onGraphClick);
        state.network.on('doubleClick', onGraphDoubleClick);
        state.network.on('hoverNode', onGraphHover);
        state.network.on('blurNode', () => {
            dom.statusCenter.textContent = 'Ready';
        });
    }

    // Fit after stabilization
    if (state.graphLayout === 'force') {
        state.network.once('stabilizationIterationsDone', () => {
            state.network.fit({ animation: { duration: 500, easingFunction: 'easeOutQuad' } });
        });
    } else {
        setTimeout(() => {
            state.network.fit({ animation: { duration: 500, easingFunction: 'easeOutQuad' } });
        }, 100);
    }
}

function onGraphClick(params) {
    if (params.nodes.length === 1) {
        selectGraphNode(params.nodes[0]);
    } else if (params.nodes.length === 0 && params.edges.length === 0) {
        deselectGraphNode();
    }
}

function onGraphDoubleClick(params) {
    if (params.nodes.length === 1) {
        // Focus on node and its neighbors
        const nodeId = params.nodes[0];
        const connected = state.network.getConnectedNodes(nodeId);
        connected.push(nodeId);
        state.network.focus(nodeId, {
            scale: 1.2,
            animation: { duration: 400, easingFunction: 'easeOutQuad' },
            locked: false,
        });
    }
}

function onGraphHover(params) {
    if (params.node) {
        const node = state.allNodes.find(n => n.id === params.node);
        if (node) {
            const label = state.graphMode === 'concepts'
                ? `${node.label} (${node.fileCount || 0} files)`
                : node.path || node.label;
            dom.statusCenter.textContent = label;
        }
    }
}

async function selectGraphNode(nodeId) {
    state.selectedNodeId = nodeId;

    // Highlight in network
    if (state.network) {
        const connected = state.network.getConnectedNodes(nodeId);
        connected.push(nodeId);
        const allIds = state.allNodes.map(n => n.id);
        const dimmed = allIds.filter(id => !connected.includes(id));

        state.network.setSelection({ nodes: [nodeId] }, { highlightEdges: true });

        // Dim unconnected nodes
        const update = dimmed.map(id => ({ id, color: { background: '#0a0f1a', border: '#1a2438' }, font: { color: '#2a3a56' } }));
        const highlightNode = state.allNodes.find(n => n.id === nodeId);
        if (highlightNode) {
            const ec = state.graphMode === 'concepts' ? '#00e5a0' : extColor(highlightNode.extension);
            update.push({ id: nodeId, color: { background: ec, border: '#ffffff' }, font: { color: '#ffffff', size: 13 } });
        }
        state.network.body.data.nodes.update(update);
    }

    // Highlight in file tree
    dom.fileTree.querySelectorAll('.tree-file').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.id) === nodeId);
    });

    // Load details
    if (state.graphMode === 'files') {
        loadFileDetails(nodeId);
    }
    // Open details panel
    if (!state.detailsOpen) toggleDetailsPanel();
}

function deselectGraphNode() {
    state.selectedNodeId = null;
    if (state.network) {
        // Restore all node colors
        const update = state.allNodes.map(n => {
            const ec = state.graphMode === 'concepts' ? '#00e5a0' : extColor(n.extension);
            return { id: n.id, color: { background: '#0f1624', border: ec }, font: { color: '#e4e8f1', size: 11 } };
        });
        state.network.body.data.nodes.update(update);
        state.network.unselectAll();
    }
    dom.fileTree.querySelectorAll('.tree-file.active').forEach(el => el.classList.remove('active'));
    dom.detailsContent.innerHTML = `<div class="details-empty">
        <i class="fas fa-mouse-pointer"></i>
        <p>Click a node to view file details and extracted concepts</p>
    </div>`;
}

async function loadFileDetails(fid) {
    try {
        const detail = await apiGet('/api/files/' + fid);
        renderFileDetails(detail);
    } catch (err) {
        dom.detailsContent.innerHTML = `<div class="details-error"><i class="fas fa-exclamation-triangle"></i> Failed to load details</div>`;
    }
}

function renderFileDetails(detail) {
    const color = extColor(detail.extension);
    const icon = extIcon(detail.extension);

    let conceptsHtml = '';
    if (detail.concepts && detail.concepts.length > 0) {
        conceptsHtml = `<div class="detail-section">
            <h4><i class="fas fa-tags"></i> Extracted Concepts</h4>
            <div class="concept-tags">`;
        for (const c of detail.concepts.slice(0, 30)) {
            const w = Math.min(1, c.weight * 10);
            conceptsHtml += `<span class="concept-tag" style="--w:${w}" title="Weight: ${c.weight.toFixed(4)}">${c.name}</span>`;
        }
        if (detail.concepts.length > 30) {
            conceptsHtml += `<span class="concept-tag concept-more">+${detail.concepts.length - 30} more</span>`;
        }
        conceptsHtml += '</div></div>';
    }

    let connectionsHtml = '';
    if (detail.connections && detail.connections.length > 0) {
        connectionsHtml = `<div class="detail-section">
            <h4><i class="fas fa-link"></i> Related Files (${detail.connections.length})</h4>
            <div class="connections-list">`;
        for (const conn of detail.connections.sort((a, b) => b.weight - a.weight)) {
            const cColor = extColor(conn.extension);
            const cIcon = extIcon(conn.extension);
            const shared = (conn.shared || []).slice(0, 5).join(', ');
            connectionsHtml += `<div class="connection-item" data-id="${conn.other_id}">
                <i class="${cIcon}" style="color:${cColor}"></i>
                <div class="conn-info">
                    <span class="conn-name">${conn.filename}</span>
                    <span class="conn-shared">${shared || 'Related by similarity'}</span>
                </div>
                <span class="conn-weight">${conn.weight.toFixed(2)}</span>
            </div>`;
        }
        connectionsHtml += '</div></div>';
    }

    // Content preview (first 2000 chars)
    let previewHtml = '';
    if (detail.content) {
        const preview = detail.content.substring(0, 2000);
        const escaped = preview.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        previewHtml = `<div class="detail-section">
            <h4><i class="fas fa-eye"></i> Preview</h4>
            <pre class="code-preview">${escaped}${detail.content.length > 2000 ? '\n...' : ''}</pre>
        </div>`;
    }

    dom.detailsContent.innerHTML = `
        <div class="detail-header-card">
            <div class="detail-file-icon" style="background:${color}20;color:${color}">
                <i class="${icon}"></i>
            </div>
            <div class="detail-file-info">
                <h3>${detail.filename}</h3>
                <p class="detail-path">${detail.path}</p>
            </div>
        </div>
        <div class="detail-meta">
            <div class="meta-item">
                <span class="meta-label">Type</span>
                <span class="meta-value" style="color:${color}">${detail.extension}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Size</span>
                <span class="meta-value">${formatBytes(detail.size)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Concepts</span>
                <span class="meta-value">${detail.concepts ? detail.concepts.length : 0}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Links</span>
                <span class="meta-value">${detail.connections ? detail.connections.length : 0}</span>
            </div>
        </div>
        ${conceptsHtml}
        ${connectionsHtml}
        ${previewHtml}
    `;

    // Click on connection → navigate
    dom.detailsContent.querySelectorAll('.connection-item').forEach(el => {
        el.addEventListener('click', () => {
            const id = parseInt(el.dataset.id);
            selectGraphNode(id);
            if (state.network) {
                state.network.focus(id, {
                    scale: 1.0,
                    animation: { duration: 400, easingFunction: 'easeOutQuad' },
                });
            }
        });
    });
}

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
    return bytes.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

// ── Search ──

let searchDebounce = null;

async function handleSearch(query) {
    if (query.length < 2) {
        dom.searchResults.classList.remove('visible');
        return;
    }
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(async () => {
        try {
            const results = await apiGet('/api/search?q=' + encodeURIComponent(query));
            renderSearchResults(results);
        } catch (err) {
            // Silently ignore
        }
    }, 250);
}

function renderSearchResults(results) {
    if (!results.files.length && !results.concepts.length) {
        dom.searchResults.innerHTML = '<div class="search-empty">No results found</div>';
        dom.searchResults.classList.add('visible');
        return;
    }

    let html = '';

    // Concepts section
    if (results.concepts.length > 0) {
        html += '<div class="search-section-title">Concepts</div>';
        for (const c of results.concepts) {
            html += `<div class="search-result-item" data-type="concept" data-name="${c.name}">
                <div class="sr-icon" style="background:var(--accent-bg);color:var(--accent)"><i class="fas fa-tag"></i></div>
                <div class="sr-info">
                    <span class="sr-name">${c.name}</span>
                    <span class="sr-path">${c.category}</span>
                </div>
            </div>`;
        }
    }

    // Files section
    if (results.files.length > 0) {
        html += '<div class="search-section-title">Files</div>';
        for (const f of results.files) {
            const color = extColor(f.extension);
            const icon = extIcon(f.extension);
            html += `<div class="search-result-item" data-type="file" data-id="${f.id}">
                <div class="sr-icon" style="background:${color}15;color:${color}"><i class="${icon}"></i></div>
                <div class="sr-info">
                    <span class="sr-name">${f.filename}</span>
                    <span class="sr-path">${f.path}</span>
                </div>
            </div>`;
        }
    }

    dom.searchResults.innerHTML = html;
    dom.searchResults.classList.add('visible');

    // Click handlers
    dom.searchResults.querySelectorAll('.search-result-item').forEach(el => {
        el.addEventListener('click', () => {
            dom.searchResults.classList.remove('visible');
            dom.searchInput.value = '';
            if (el.dataset.type === 'file') {
                const id = parseInt(el.dataset.id);
                selectGraphNode(id);
                if (state.network) {
                    state.network.focus(id, { scale: 1.0, animation: { duration: 400 } });
                }
            }
        });
    });
}

// ── Sidebar & Panels ──

function toggleSidebar() {
    state.sidebarOpen = !state.sidebarOpen;
    const sidebar = $('#sidebar');
    const icon = $('#btnToggleSidebar i');
    if (state.sidebarOpen) {
        sidebar.style.width = 'var(--sidebar-w)';
        sidebar.style.minWidth = 'var(--sidebar-w)';
        sidebar.style.opacity = '1';
        sidebar.style.overflow = '';
        icon.className = 'fas fa-angles-left';
    } else {
        sidebar.style.width = '0px';
        sidebar.style.minWidth = '0px';
        sidebar.style.opacity = '0';
        sidebar.style.overflow = 'hidden';
        icon.className = 'fas fa-angles-right';
    }
}

function toggleDetailsPanel() {
    state.detailsOpen = !state.detailsOpen;
    const panel = $('#detailsPanel');
    if (state.detailsOpen) {
        panel.style.width = 'var(--details-w)';
        panel.style.minWidth = 'var(--details-w)';
        panel.style.opacity = '1';
        panel.style.overflow = '';
    } else {
        panel.style.width = '0px';
        panel.style.minWidth = '0px';
        panel.style.opacity = '0';
        panel.style.overflow = 'hidden';
    }
}

// ── Graph Controls ──

async function toggleGraphMode() {
    state.graphMode = state.graphMode === 'files' ? 'concepts' : 'files';
    const btn = $('#btnGraphMode');
    btn.querySelector('span').textContent = state.graphMode === 'files' ? 'File Graph' : 'Concept Graph';
    btn.classList.toggle('active', state.graphMode === 'concepts');

    try {
        const data = await apiGet('/api/graph?mode=' + state.graphMode);
        renderGraph(data);
        toast(`Switched to ${state.graphMode} view`, 'info', 2000);
    } catch (err) {
        toast('Failed to switch view: ' + err.message, 'error');
    }
}

async function toggleLayout() {
    state.graphLayout = state.graphLayout === 'force' ? 'hierarchical' : 'force';
    const btn = $('#btnLayout');
    btn.querySelector('i').className = state.graphLayout === 'force' ? 'fas fa-sitemap' : 'fas fa-circle-nodes';
    applyFiltersAndRender();
    toast(`Layout: ${state.graphLayout === 'force' ? 'Force-directed' : 'Hierarchical'}`, 'info', 2000);
}

function setGraphFilter(filter) {
    state.graphFilter = filter;
    $$('.toolbar-btn[data-filter]').forEach(b => b.classList.toggle('active', b.dataset.filter === filter));
    applyFiltersAndRender();
}

// ── Event Bindings ──

function init() {
    initWelcomeCanvas();

    // Welcome buttons
    $('#btnDemo').addEventListener('click', startDemo);
    $('#btnSetVault').addEventListener('click', openScanDialog);
    $('#btnScan').addEventListener('click', openScanDialog);

    // Scan dialog
    $('#btnCloseDialog').addEventListener('click', closeScanDialog);
    $('#btnCancelScan').addEventListener('click', closeScanDialog);
    $('#btnStartScan').addEventListener('click', () => {
        const path = dom.vaultPath.value.trim();
        if (!path) { toast('Please enter a vault path', 'warning'); return; }
        state.vaultPath = path;
        startScan(path);
    });
    dom.scanDialog.addEventListener('click', (e) => {
        if (e.target === dom.scanDialog) closeScanDialog();
    });

    // Search
    dom.searchInput.addEventListener('input', (e) => handleSearch(e.target.value.trim()));
    dom.searchInput.addEventListener('focus', () => {
        if (dom.searchInput.value.trim().length >= 2) dom.searchResults.classList.add('visible');
    });
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) dom.searchResults.classList.remove('visible');
    });
    dom.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { dom.searchResults.classList.remove('visible'); dom.searchInput.blur(); }
    });

    // Graph controls
    $('#btnGraphMode').addEventListener('click', toggleGraphMode);
    $('#btnLayout').addEventListener('click', toggleLayout);
    $$('.toolbar-btn[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => setGraphFilter(btn.dataset.filter));
    });

    // Zoom controls
    $('#btnZoomIn').addEventListener('click', () => {
        if (state.network) {
            const scale = state.network.getScale();
            state.network.moveTo({ scale: scale * 1.3, animation: { duration: 200 } });
        }
    });
    $('#btnZoomOut').addEventListener('click', () => {
        if (state.network) {
            const scale = state.network.getScale();
            state.network.moveTo({ scale: scale / 1.3, animation: { duration: 200 } });
        }
    });
    $('#btnFitGraph').addEventListener('click', () => {
        if (state.network) state.network.fit({ animation: { duration: 400 } });
    });

    // Similarity slider
    dom.similaritySlider.addEventListener('input', (e) => {
        state.similarityThreshold = parseInt(e.target.value) / 100;
        dom.similarityValue.textContent = state.similarityThreshold.toFixed(2);
    });
    dom.similaritySlider.addEventListener('change', () => {
        applyFiltersAndRender();
    });

    // Sidebar
    $('#btnToggleSidebar').addEventListener('click', toggleSidebar);
    $('#btnCloseDetails').addEventListener('click', toggleDetailsPanel);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === 'f' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            dom.searchInput.focus();
        }
        if (e.key === 'Escape') {
            deselectGraphNode();
            dom.searchResults.classList.remove('visible');
        }
    });

    // Check if there's existing data
    checkExistingData();
}

async function checkExistingData() {
    try {
        const stats = await apiGet('/api/stats');
        if (stats.fileCount > 0) {
            // Auto-load existing data
            showWorkspace();
        }
    } catch (err) {
        // Server not running — stay on welcome
    }
}
// Boot
document.addEventListener('DOMContentLoaded', init);

ENGINEER_UI_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ProdMind Engineer Evidence Graph</title>
  <style>
    :root { font-family: Inter, ui-sans-serif, system-ui, sans-serif; color-scheme: dark; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #080d1a; color: #eef2ff; }
    header { padding: 24px 30px 18px; border-bottom: 1px solid #26314c; background: #0d1427; }
    h1 { margin: 0 0 6px; font-size: 24px; }
    p { color: #9aa7c7; }
    .warning { display: inline-block; padding: 6px 10px; border-radius: 8px; background: #422006; color: #fed7aa; font-size: 12px; }
    main { padding: 22px 30px 46px; }
    .toolbar { display: grid; grid-template-columns: 1fr 1fr 1.8fr 1.2fr auto; gap: 9px; margin-bottom: 18px; }
    input, textarea, button { border-radius: 9px; border: 1px solid #33415f; padding: 10px 11px; font: inherit; }
    input, textarea { background: #0d1427; color: #fff; min-width: 0; }
    button { background: #7c8cff; color: #08101f; border: 0; font-weight: 750; cursor: pointer; }
    button:disabled { opacity: .5; }
    .summary { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
    .pill { border: 1px solid #33415f; border-radius: 999px; padding: 5px 9px; color: #cbd5e1; font-size: 12px; background: #0d1427; }
    .graph-wrap { overflow: auto; border: 1px solid #26314c; border-radius: 16px; background: radial-gradient(circle at 50% 0%, #111d38 0, #0a1020 55%); }
    #graph { position: relative; min-width: 1120px; min-height: 520px; }
    #edges { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
    .node { position: absolute; width: 180px; min-height: 88px; padding: 11px; border: 1px solid #3b4868; border-radius: 12px; background: #121a30; box-shadow: 0 10px 30px rgba(0,0,0,.25); }
    .node.context { border-color: #3b82f6; }
    .node.evidence { border-color: #8b5cf6; }
    .node.diagnosis { border-color: #22c55e; background: #10251f; }
    .node.history { border-color: #f59e0b; background: #2a1d0a; }
    .kind { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: #93a4c8; margin-bottom: 6px; }
    .label { font-size: 12px; line-height: 1.4; overflow-wrap: anywhere; }
    .source { margin-top: 7px; font-size: 10px; color: #7280a0; overflow-wrap: anywhere; }
    .edge-label { font-size: 10px; fill: #93a4c8; }
    .empty { padding: 80px 30px; text-align: center; color: #7f8ba8; }
    .actions { margin-top: 14px; border: 1px solid #26314c; border-radius: 12px; padding: 14px; background: #0d1427; }
    .actions li { color: #b8c1dc; margin: 5px 0; }
    .ai-panel { margin-top: 14px; border: 1px solid #26314c; border-radius: 12px; padding: 14px; background: #0d1427; }
    .ai-row { display: grid; grid-template-columns: 1fr auto; gap: 9px; margin-top: 10px; }
    .ai-result { margin-top: 12px; color: #cbd5e1; font-size: 13px; line-height: 1.5; }
    .ai-result .claim { border-left: 2px solid #8b5cf6; padding-left: 9px; margin: 8px 0; }
    @media (max-width: 950px) { .toolbar { grid-template-columns: 1fr 1fr; } main { padding: 18px; } }
  </style>
</head>
<body>
<header>
  <h1>ProdMind · Engineer Evidence Graph</h1>
  <p>Inspect layered service topology and how current evidence supports a root-cause diagnosis.</p>
  <span class="warning">Demo viewer. Graph data still requires project scope + engineer authentication.</span>
</header>
<main>
  <div class="toolbar">
    <input id="project" value="demo" placeholder="Project ID" />
    <input id="key" type="password" placeholder="Engineer API key" autocomplete="off" />
    <input id="trace" placeholder="W3C Trace ID" autocomplete="off" />
    <input id="action" placeholder="action (optional)" />
    <button id="load">Build graph</button>
  </div>
  <div id="summary" class="summary"></div>
  <div class="graph-wrap"><div id="graph"><svg id="edges"></svg><div id="empty" class="empty">Enter project, engineer key, and Trace ID.</div></div></div>
  <div id="actions" class="actions" hidden></div>
  <div class="ai-panel">
    <strong>Evidence-grounded AI Investigator</strong>
    <p>Optional, engineer-only, and read-only. Deterministic RCA remains authoritative.</p>
    <div class="ai-row">
      <textarea id="ai-question" rows="2" placeholder="Ask a follow-up about this trace"></textarea>
      <button id="ask-ai">Ask AI</button>
    </div>
    <div id="ai-result" class="ai-result"></div>
  </div>
</main>
<script>
  const projectEl = document.getElementById('project');
  const keyEl = document.getElementById('key');
  const traceEl = document.getElementById('trace');
  const actionEl = document.getElementById('action');
  const loadEl = document.getElementById('load');
  const graphEl = document.getElementById('graph');
  const edgesEl = document.getElementById('edges');
  const emptyEl = document.getElementById('empty');
  const summaryEl = document.getElementById('summary');
  const actionsEl = document.getElementById('actions');
  const aiQuestionEl = document.getElementById('ai-question');
  const askAiEl = document.getElementById('ask-ai');
  const aiResultEl = document.getElementById('ai-result');
  let aiSessionId = null;

  const params = new URLSearchParams(location.search);
  if (params.get('trace_id')) traceEl.value = params.get('trace_id');
  if (params.get('project')) projectEl.value = params.get('project');
  if (params.get('action')) actionEl.value = params.get('action');

  loadEl.addEventListener('click', loadGraph);
  askAiEl.addEventListener('click', askAI);
  traceEl.addEventListener('keydown', e => { if (e.key === 'Enter') loadGraph(); });

  async function loadGraph() {
    const project = projectEl.value.trim();
    const key = keyEl.value;
    const trace = traceEl.value.trim();
    if (!project || !key || !trace) {
      showError('Project ID, Engineer API key, and Trace ID are required.');
      return;
    }
    loadEl.disabled = true;
    aiSessionId = null;
    aiResultEl.textContent = '';
    try {
      const response = await fetch('/api/v1/investigate/trace/graph', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-ProdMind-Project': project,
          'X-ProdMind-Engineer-Key': key
        },
        body: JSON.stringify({
          trace_id: trace,
          question: 'Why did my last operation fail?',
          action: actionEl.value || null
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      render(data);
    } catch (error) {
      showError(error.message);
    } finally {
      loadEl.disabled = false;
    }
  }

  async function askAI() {
    const project = projectEl.value.trim();
    const key = keyEl.value;
    const trace = traceEl.value.trim();
    const question = aiQuestionEl.value.trim();
    if (!project || !key || !trace || !question) {
      aiResultEl.textContent = 'Project ID, Engineer API key, Trace ID, and a question are required.';
      return;
    }
    askAiEl.disabled = true;
    try {
      const response = await fetch('/api/v1/investigator/trace', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-ProdMind-Project': project,
          'X-ProdMind-Engineer-Key': key
        },
        body: JSON.stringify({
          trace_id: trace,
          question,
          action: actionEl.value || null,
          session_id: aiSessionId
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      aiSessionId = data.session_id;
      renderAI(data);
    } catch (error) {
      aiResultEl.textContent = `AI Investigator unavailable: ${error.message}`;
    } finally {
      askAiEl.disabled = false;
    }
  }

  function renderAI(data) {
    const claims = (data.claims || []).map(claim =>
      `<div class="claim">${esc(claim.summary)} <small>[${claim.evidence_ids.map(esc).join(', ')}]</small></div>`
    ).join('');
    const missing = data.missing_evidence?.length
      ? `<p><strong>Missing evidence:</strong> ${data.missing_evidence.map(esc).join('; ')}</p>` : '';
    const next = data.next_steps?.length
      ? `<p><strong>Read-only next steps:</strong> ${data.next_steps.map(esc).join(', ')}</p>` : '';
    aiResultEl.innerHTML = `<p>${esc(data.answer)}</p>${claims}${missing}${next}<small>Session ${esc(data.session_id)} · turn ${esc(data.turn)} · ${esc(data.provider)}${data.model ? ` / ${esc(data.model)}` : ''}</small>`;
  }

  function render(data) {
    clear();
    emptyEl.hidden = true;
    const root = data.root_cause;
    summaryEl.innerHTML = [pill(data.incident_id), pill(data.status), root ? pill(root.category) : '', root ? pill(`${Math.round(root.confidence * 100)}%`) : '', pill(`${data.nodes.length} nodes / ${data.edges.length} edges`)].join('');

    const levels = computeLevels(data);
    const columns = new Map();
    data.nodes.forEach(node => {
      const level = levels.get(node.id) ?? 0;
      if (!columns.has(level)) columns.set(level, []);
      columns.get(level).push(node);
    });
    const maxLevel = Math.max(0, ...columns.keys());
    const maxRows = Math.max(1, ...[...columns.values()].map(v => v.length));
    const width = Math.max(1120, 230 * (maxLevel + 1) + 70);
    const height = Math.max(520, 120 * maxRows + 90);
    graphEl.style.width = `${width}px`;
    graphEl.style.height = `${height}px`;

    const nodeMap = new Map();
    for (const [level, items] of columns.entries()) {
      items.sort((a,b) => order(a.kind) - order(b.kind) || a.id.localeCompare(b.id));
      const startY = Math.max(28, (height - items.length * 112) / 2);
      items.forEach((node, row) => {
        const el = document.createElement('div');
        el.className = `node ${node.role}`;
        el.style.left = `${35 + level * 225}px`;
        el.style.top = `${startY + row * 112}px`;
        el.innerHTML = `<div class="kind">${esc(node.kind)}</div><div class="label">${esc(node.label)}</div>${node.source ? `<div class="source">${esc(node.source)}</div>` : ''}`;
        graphEl.appendChild(el);
        nodeMap.set(node.id, el);
      });
    }
    requestAnimationFrame(() => drawEdges(data.edges, nodeMap, width, height));

    if (data.recommended_actions?.length) {
      actionsEl.hidden = false;
      actionsEl.innerHTML = `<strong>Recommended actions</strong><ol>${data.recommended_actions.map(x => `<li>${esc(x)}</li>`).join('')}</ol>`;
    }
  }

  function computeLevels(data) {
    const incoming = new Map(data.nodes.map(n => [n.id, 0]));
    const outgoing = new Map(data.nodes.map(n => [n.id, []]));
    data.edges.forEach(e => { incoming.set(e.target, (incoming.get(e.target)||0)+1); outgoing.get(e.source)?.push(e.target); });
    const level = new Map();
    const queue = [];
    data.nodes.forEach(n => { if ((incoming.get(n.id)||0) === 0) { level.set(n.id, 0); queue.push(n.id); } });
    while (queue.length) {
      const source = queue.shift();
      for (const target of outgoing.get(source) || []) {
        level.set(target, Math.max(level.get(target)||0, (level.get(source)||0)+1));
        incoming.set(target, (incoming.get(target)||1)-1);
        if (incoming.get(target) === 0) queue.push(target);
      }
    }
    data.nodes.forEach(n => { if (!level.has(n.id)) level.set(n.id, 0); });
    return level;
  }

  function drawEdges(edges, nodes, width, height) {
    edgesEl.setAttribute('viewBox', `0 0 ${width} ${height}`);
    edgesEl.innerHTML = '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#64748b"/></marker></defs>';
    const base = graphEl.getBoundingClientRect();
    edges.forEach(edge => {
      const a = nodes.get(edge.source)?.getBoundingClientRect();
      const b = nodes.get(edge.target)?.getBoundingClientRect();
      if (!a || !b) return;
      const x1=a.right-base.left, y1=a.top-base.top+a.height/2, x2=b.left-base.left, y2=b.top-base.top+b.height/2, mid=(x1+x2)/2;
      const path=document.createElementNS('http://www.w3.org/2000/svg','path');
      const stroke=edge.relation === 'calls' ? '#38bdf8' : edge.relation === 'context_for' ? '#f59e0b' : '#64748b';
      path.setAttribute('d',`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2-8} ${y2}`); path.setAttribute('fill','none'); path.setAttribute('stroke',stroke); path.setAttribute('marker-end','url(#arrow)'); edgesEl.appendChild(path);
      const text=document.createElementNS('http://www.w3.org/2000/svg','text'); text.setAttribute('x',mid); text.setAttribute('y',(y1+y2)/2-5); text.setAttribute('text-anchor','middle'); text.setAttribute('class','edge-label'); text.textContent=edge.relation.replaceAll('_',' '); edgesEl.appendChild(text);
    });
  }

  function showError(message) { clear(); emptyEl.hidden=false; emptyEl.textContent=`Cannot build graph: ${message}`; }
  function clear() { graphEl.querySelectorAll('.node').forEach(n=>n.remove()); edgesEl.innerHTML=''; summaryEl.innerHTML=''; actionsEl.hidden=true; actionsEl.innerHTML=''; }
  function pill(v) { return `<span class="pill">${esc(v)}</span>`; }
  function order(k) { return ['user_action','http','trace','service','operation','log','exception','database','dependency','metric','root_cause','history'].indexOf(k); }
  function esc(v) { return String(v).replace(/[&<>'"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
</script>
</body>
</html>'''

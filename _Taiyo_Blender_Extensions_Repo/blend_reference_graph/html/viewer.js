(function () {
  const graphData = window.BRG_GRAPH_DATA || { meta: {}, nodes: [], edges: [] };
  const svg = document.getElementById("graph");
  const meta = document.getElementById("meta");
  const details = document.getElementById("details");
  const filters = document.getElementById("filters");
  const legend = document.getElementById("legend");
  const search = document.getElementById("search");

  const colors = {
    OBJECT: "#72b7ff",
    MESH: "#c49aff",
    COLLECTION: "#f5c65b",
    ARMATURE: "#ff7b79",
    BONE: "#ff9ad5",
    CONSTRAINT: "#f59b54",
    MODIFIER: "#74d47b",
    GEONODES: "#74d47b",
    NODEGROUP: "#5ecf9f",
    MATERIAL: "#c9a06b",
    IMAGE: "#76d9ea",
    WARNING: "#ff6262",
  };
  const activeTypes = new Set(graphData.nodes.map((node) => node.type));
  const nodeById = new Map(graphData.nodes.map((node) => [node.id, node]));
  const state = { scale: 1, tx: 0, ty: 0, selected: null, query: "" };

  let root;
  let edgeLayer;
  let nodeLayer;
  let draggedNode = null;

  function init() {
    meta.textContent = [
      graphData.meta.target_name ? `Target: ${graphData.meta.target_name}` : "",
      graphData.meta.mode ? `Mode: ${graphData.meta.mode}` : "",
      `Nodes: ${graphData.nodes.length}`,
      `Edges: ${graphData.edges.length}`,
      graphData.meta.generated_at || "",
    ].filter(Boolean).join("   ");
    buildFilters();
    render();
    fitView();
  }

  function buildFilters() {
    const types = [...new Set(graphData.nodes.map((node) => node.type))].sort();
    filters.innerHTML = "";
    legend.innerHTML = "";
    for (const type of types) {
      const row = document.createElement("label");
      row.className = "filter";
      row.innerHTML = `<input type="checkbox" checked data-type="${type}"><span class="swatch" style="background:${colors[type] || "#aaa"}"></span>${type}`;
      row.querySelector("input").addEventListener("change", (event) => {
        if (event.target.checked) activeTypes.add(type);
        else activeTypes.delete(type);
        applyVisibility();
      });
      filters.appendChild(row);

      const leg = document.createElement("div");
      leg.className = "filter";
      leg.innerHTML = `<span class="swatch" style="background:${colors[type] || "#aaa"}"></span>${type}`;
      legend.appendChild(leg);
    }
  }

  function layoutNodes() {
    const nodes = graphData.nodes;
    const index = new Map(nodes.map((node, i) => [node.id, i]));
    const outgoing = new Map(nodes.map((node) => [node.id, 0]));
    const incoming = new Map(nodes.map((node) => [node.id, 0]));
    for (const edge of graphData.edges) {
      outgoing.set(edge.from, (outgoing.get(edge.from) || 0) + 1);
      incoming.set(edge.to, (incoming.get(edge.to) || 0) + 1);
    }
    const targetId = graphData.meta.target_id || (nodes[0] && nodes[0].id);
    for (const node of nodes) {
      const i = index.get(node.id);
      let column = 0;
      if (node.id === targetId) column = 0;
      else if ((incoming.get(node.id) || 0) > (outgoing.get(node.id) || 0)) column = 1;
      else column = -1;
      if (node.type === "COLLECTION") column = Math.min(column, -1);
      if (node.type === "MESH" || node.type === "MODIFIER" || node.type === "NODEGROUP") column = Math.max(column, 1);
      node.x = 360 + column * 280;
      node.y = 120 + (i % 12) * 84 + Math.floor(i / 12) * 34;
      node.w = Math.max(150, Math.min(260, String(node.label || node.name).length * 7 + 54));
      node.h = 38;
    }
  }

  function render() {
    layoutNodes();
    svg.innerHTML = `<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#7b8593"></path></marker></defs>`;
    root = makeSvg("g", { id: "viewport" });
    edgeLayer = makeSvg("g", {});
    nodeLayer = makeSvg("g", {});
    root.append(edgeLayer, nodeLayer);
    svg.appendChild(root);

    for (const edge of graphData.edges) {
      const from = nodeById.get(edge.from);
      const to = nodeById.get(edge.to);
      if (!from || !to) continue;
      const line = makeSvg("line", {
        class: "edge",
        x1: from.x + from.w,
        y1: from.y + from.h / 2,
        x2: to.x,
        y2: to.y + to.h / 2,
        "data-from": edge.from,
        "data-to": edge.to,
      });
      edgeLayer.appendChild(line);
    }

    for (const node of graphData.nodes) {
      const group = makeSvg("g", { class: "node", transform: `translate(${node.x},${node.y})`, "data-id": node.id, "data-type": node.type });
      group.appendChild(makeSvg("rect", { width: node.w, height: node.h, fill: colors[node.type] || "#c8ccd2" }));
      const text = makeSvg("text", { x: 13, y: 24 });
      text.textContent = node.label || node.name;
      group.appendChild(text);
      group.addEventListener("pointerdown", (event) => beginNodeDrag(event, node, group));
      group.addEventListener("click", (event) => {
        event.stopPropagation();
        selectNode(node.id);
      });
      nodeLayer.appendChild(group);
    }

    wirePanZoom();
    applyTransform();
    applyVisibility();
  }

  function makeSvg(tag, attrs) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    return el;
  }

  function selectNode(id) {
    state.selected = id;
    const node = nodeById.get(id);
    document.querySelectorAll(".node").forEach((el) => el.classList.toggle("selected", el.dataset.id === id));
    if (!node) return;
    const rows = Object.entries(node.details || {}).map(([key, value]) => {
      const display = Array.isArray(value) ? value.join(", ") : String(value);
      return `<div class="detail-row"><div class="detail-key">${escapeHtml(key)}</div><div>${escapeHtml(display || "-")}</div></div>`;
    }).join("");
    details.innerHTML = `<h2>Details</h2><div class="detail-row"><div class="detail-key">Type</div><div>${escapeHtml(node.type)}</div></div><div class="detail-row"><div class="detail-key">Name</div><div>${escapeHtml(node.name)}</div></div>${rows}`;
  }

  function applyVisibility() {
    const query = state.query.toLowerCase();
    document.querySelectorAll(".node").forEach((el) => {
      const node = nodeById.get(el.dataset.id);
      const typeVisible = activeTypes.has(el.dataset.type);
      const text = JSON.stringify(node || {}).toLowerCase();
      const searchVisible = !query || text.includes(query);
      el.classList.toggle("dim", !typeVisible || !searchVisible);
    });
    document.querySelectorAll(".edge").forEach((el) => {
      const fromVisible = isNodeVisible(el.dataset.from);
      const toVisible = isNodeVisible(el.dataset.to);
      el.classList.toggle("dim", !fromVisible || !toVisible);
    });
  }

  function isNodeVisible(id) {
    const node = nodeById.get(id);
    if (!node || !activeTypes.has(node.type)) return false;
    return !state.query || JSON.stringify(node).toLowerCase().includes(state.query.toLowerCase());
  }

  function fitView() {
    const box = svg.getBoundingClientRect();
    if (!graphData.nodes.length || !box.width || !box.height) return;
    const minX = Math.min(...graphData.nodes.map((node) => node.x));
    const maxX = Math.max(...graphData.nodes.map((node) => node.x + node.w));
    const minY = Math.min(...graphData.nodes.map((node) => node.y));
    const maxY = Math.max(...graphData.nodes.map((node) => node.y + node.h));
    state.scale = Math.min(1.2, Math.max(0.35, Math.min((box.width - 80) / (maxX - minX || 1), (box.height - 80) / (maxY - minY || 1))));
    state.tx = (box.width - (minX + maxX) * state.scale) / 2;
    state.ty = (box.height - (minY + maxY) * state.scale) / 2;
    applyTransform();
  }

  function applyTransform() {
    if (root) root.setAttribute("transform", `translate(${state.tx},${state.ty}) scale(${state.scale})`);
  }

  function beginNodeDrag(event, node, group) {
    event.stopPropagation();
    draggedNode = {
      node,
      group,
      startX: event.clientX,
      startY: event.clientY,
      nodeX: node.x,
      nodeY: node.y,
    };
    group.setPointerCapture(event.pointerId);
  }

  function updateEdgesForNode(node) {
    document.querySelectorAll(`.edge[data-from="${CSS.escape(node.id)}"]`).forEach((line) => {
      line.setAttribute("x1", node.x + node.w);
      line.setAttribute("y1", node.y + node.h / 2);
    });
    document.querySelectorAll(`.edge[data-to="${CSS.escape(node.id)}"]`).forEach((line) => {
      line.setAttribute("x2", node.x);
      line.setAttribute("y2", node.y + node.h / 2);
    });
  }

  function wirePanZoom() {
    let start = null;
    svg.onpointerdown = (event) => {
      start = { x: event.clientX, y: event.clientY, tx: state.tx, ty: state.ty };
      svg.classList.add("dragging");
    };
    svg.onpointermove = (event) => {
      if (draggedNode) {
        const dx = (event.clientX - draggedNode.startX) / state.scale;
        const dy = (event.clientY - draggedNode.startY) / state.scale;
        draggedNode.node.x = draggedNode.nodeX + dx;
        draggedNode.node.y = draggedNode.nodeY + dy;
        draggedNode.group.setAttribute("transform", `translate(${draggedNode.node.x},${draggedNode.node.y})`);
        updateEdgesForNode(draggedNode.node);
        return;
      }
      if (!start) return;
      state.tx = start.tx + event.clientX - start.x;
      state.ty = start.ty + event.clientY - start.y;
      applyTransform();
    };
    svg.onpointerup = svg.onpointerleave = () => {
      draggedNode = null;
      start = null;
      svg.classList.remove("dragging");
    };
    svg.onwheel = (event) => {
      event.preventDefault();
      const delta = event.deltaY > 0 ? 0.9 : 1.1;
      state.scale = Math.max(0.2, Math.min(2.5, state.scale * delta));
      applyTransform();
    };
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  document.getElementById("reload").addEventListener("click", () => window.location.reload());
  document.getElementById("fit").addEventListener("click", fitView);
  search.addEventListener("input", (event) => {
    state.query = event.target.value;
    applyVisibility();
  });

  init();
}());

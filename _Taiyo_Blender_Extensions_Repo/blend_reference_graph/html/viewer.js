(function () {
  const graphData = window.BRG_GRAPH_DATA || { meta: {}, nodes: [], edges: [] };
  const svg = document.getElementById("graph");
  const graphWrap = document.getElementById("graph-wrap");
  const selectionBox = document.getElementById("selection-box");
  const meta = document.getElementById("meta");
  const details = document.getElementById("details");
  const legend = document.getElementById("legend");
  const search = document.getElementById("search");
  const githubUrl = "https://github.com/Taiyo1031/taiyo-blender-scripts/tree/main/_Taiyo_Blender_Extensions_Repo/blend_reference_graph";
  const panelSwapKey = "brg.panels.swapped";

  const colors = {
    COLLECTION: "#f5c65b",
    OBJECT: "#72b7ff",
    MESH: "#c49aff",
    ARMATURE: "#ff7b79",
    BONE: "#ff9ad5",
    CONSTRAINT: "#f59b54",
    MODIFIER: "#74d47b",
    GEONODES: "#74d47b",
    NODEGROUP: "#5ecf9f",
    MATERIAL: "#c9a06b",
    IMAGE: "#76d9ea",
    ACTION: "#9ecb70",
    DRIVER: "#ffb36b",
    LIBRARY: "#8ea0ff",
    SAFE_DELETE: "#ff6f91",
    WARNING: "#ff6262",
  };
  const typeOrder = [
    "COLLECTION",
    "OBJECT",
    "MESH",
    "ARMATURE",
    "BONE",
    "CONSTRAINT",
    "MODIFIER",
    "GEONODES",
    "NODEGROUP",
    "MATERIAL",
    "IMAGE",
    "ACTION",
    "DRIVER",
    "LIBRARY",
    "SAFE_DELETE",
    "WARNING",
  ];
  const nodeById = new Map(graphData.nodes.map((node) => [node.id, node]));
  const selectedIds = new Set();
  const state = {
    scale: 1,
    tx: 0,
    ty: 0,
    query: "",
    spaceDown: false,
    boxMode: false,
  };

  let root;
  let edgeLayer;
  let nodeLayer;
  let interaction = null;

  function init() {
    meta.textContent = [
      graphData.meta.target_name ? `Target: ${graphData.meta.target_name}` : "",
      graphData.meta.mode ? `Mode: ${graphData.meta.mode}` : "",
      `Nodes: ${graphData.nodes.length}`,
      `Edges: ${graphData.edges.length}`,
      graphData.meta.generated_at || "",
    ].filter(Boolean).join("   ");
    buildLegend();
    syncPanelSwap();
    render();
    fitView();
    updateDetails();
  }

  function buildLegend() {
    const present = new Set(graphData.nodes.map((node) => node.type));
    legend.innerHTML = "";
    for (const type of typeOrder) {
      if (!present.has(type)) continue;
      const row = document.createElement("div");
      row.className = "filter";
      row.innerHTML = `<span class="swatch" style="background:${colors[type] || "#aaa"}"></span>${type}`;
      legend.appendChild(row);
    }
  }

  function layoutNodes() {
    const targetId = graphData.meta.target_id || (graphData.nodes[0] && graphData.nodes[0].id);
    const levels = new Map();
    if (targetId && nodeById.has(targetId)) {
      levels.set(targetId, 0);
      const queue = [targetId];
      while (queue.length) {
        const current = queue.shift();
        const currentLevel = levels.get(current);
        for (const edge of graphData.edges) {
          let next;
          let proposed;
          if (edge.from === current) {
            next = edge.to;
            proposed = currentLevel + 1;
          } else if (edge.to === current) {
            next = edge.from;
            proposed = currentLevel - 1;
          } else {
            continue;
          }
          if (!levels.has(next)) {
            levels.set(next, proposed);
            queue.push(next);
          }
        }
      }
    }

    const columns = new Map();
    for (const node of graphData.nodes) {
      let level = levels.get(node.id);
      if (level === undefined) level = 2;
      if (node.type === "COLLECTION") level = Math.min(level, -1);
    if (["MESH", "MODIFIER", "GEONODES", "NODEGROUP", "MATERIAL", "IMAGE"].includes(node.type)) {
        level = Math.max(level, 1);
      }
      if (["ACTION", "DRIVER", "LIBRARY"].includes(node.type)) {
        level = Math.max(level, 2);
      }
      if (node.type === "SAFE_DELETE") level = Math.min(level, -1);
      if (!columns.has(level)) columns.set(level, []);
      columns.get(level).push(node);
    }

    for (const [level, nodes] of columns) {
      nodes.sort((a, b) => `${a.type}:${a.name}`.localeCompare(`${b.type}:${b.name}`));
      const nodeHeight = 82;
      const gap = 32;
      const totalHeight = nodes.length * nodeHeight + Math.max(0, nodes.length - 1) * gap;
      nodes.forEach((node, index) => {
        node.x = 500 + level * 380;
        node.y = 400 - totalHeight / 2 + index * (nodeHeight + gap);
        node.w = 286;
        node.h = node.type === "COLLECTION" && node.path ? 88 : 70;
      });
    }
  }

  function render() {
    layoutNodes();
    svg.innerHTML = `<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#687586"></path></marker></defs>`;
    root = makeSvg("g", { id: "viewport" });
    edgeLayer = makeSvg("g", {});
    nodeLayer = makeSvg("g", {});
    root.append(edgeLayer, nodeLayer);
    svg.appendChild(root);

    for (const edge of graphData.edges) {
      const from = nodeById.get(edge.from);
      const to = nodeById.get(edge.to);
      if (!from || !to) continue;
      edgeLayer.appendChild(makeEdge(edge, from, to));
    }

    for (const node of graphData.nodes) {
      nodeLayer.appendChild(makeNode(node));
    }

    wireInteractions();
    applyTransform();
    applySearch();
    refreshSelection();
  }

  function makeEdge(edge, from, to) {
    const geometry = edgeGeometry(from, to);
    const relation = edge.label || edge.relation || "reference";
    const displayRelation = truncateMiddle(relation, 28);
    const labelWidth = Math.min(184, Math.max(44, displayRelation.length * 6.4 + 16));
    const group = makeSvg("g", {
      class: "edge-group",
      "data-from": edge.from,
      "data-to": edge.to,
    });
    const path = makeSvg("path", {
      class: "edge",
      d: geometry.d,
    });
    const label = makeSvg("g", {
      class: "edge-label",
      transform: `translate(${geometry.labelX},${geometry.labelY})`,
    });
    label.appendChild(makeSvg("rect", {
      x: -labelWidth / 2,
      y: -10,
      width: labelWidth,
      height: 20,
      rx: 4,
    }));
    const labelText = makeSvg("text", { x: 0, y: 4 });
    labelText.textContent = displayRelation;
    label.appendChild(labelText);
    const title = makeSvg("title", {});
    title.textContent = relation;
    group.append(path, label, title);
    return group;
  }

  function edgeGeometry(from, to) {
    const fromX = from.x + from.w;
    const fromY = from.y + from.h / 2;
    const toX = to.x;
    const toY = to.y + to.h / 2;
    const bend = Math.max(70, Math.abs(toX - fromX) * 0.42);
    return {
      d: `M ${fromX} ${fromY} C ${fromX + bend} ${fromY}, ${toX - bend} ${toY}, ${toX} ${toY}`,
      labelX: (fromX + toX) / 2,
      labelY: (fromY + toY) / 2,
    };
  }

  function makeNode(node) {
    const group = makeSvg("g", {
      class: "node",
      transform: `translate(${node.x},${node.y})`,
      "data-id": node.id,
      "data-type": node.type,
      style: `--node-color:${colors[node.type] || "#aab3bf"}`,
    });
    group.appendChild(makeSvg("rect", {
      class: "node-selection-halo",
      x: -5,
      y: -5,
      width: node.w + 10,
      height: node.h + 10,
      rx: 10,
    }));
    group.appendChild(makeSvg("rect", { class: "node-body", width: node.w, height: node.h }));
    group.appendChild(makeSvg("rect", {
      class: "node-accent",
      width: 7,
      height: node.h,
      rx: 4,
      fill: colors[node.type] || "#aab3bf",
    }));

    const typeText = makeSvg("text", { class: "node-type", x: 18, y: 17 });
    typeText.textContent = node.type;
    group.appendChild(typeText);

    const selectedBadge = makeSvg("g", {
      class: "node-selected-badge",
      transform: `translate(${node.w - 82},7)`,
    });
    selectedBadge.appendChild(makeSvg("rect", { width: 74, height: 19, rx: 4 }));
    const selectedText = makeSvg("text", { x: 37, y: 13 });
    selectedText.textContent = "SELECTED";
    selectedBadge.appendChild(selectedText);
    group.appendChild(selectedBadge);

    const nameLines = wrapText(node.name, 34, 2);
    nameLines.forEach((line, index) => {
      const text = makeSvg("text", { class: "node-name", x: 18, y: 39 + index * 16 });
      text.textContent = line;
      group.appendChild(text);
    });

    if (node.type === "COLLECTION" && node.path) {
      const pathText = makeSvg("text", { class: "node-path", x: 18, y: node.h - 10 });
      pathText.textContent = truncateMiddle(node.path, 47);
      group.appendChild(pathText);
    }

    const title = makeSvg("title", {});
    title.textContent = node.path ? `${node.name}\n${node.path}` : node.name;
    group.appendChild(title);
    group.addEventListener("pointerdown", (event) => beginNodeDrag(event, node));
    return group;
  }

  function wrapText(value, maxChars, maxLines) {
    const text = String(value || "");
    if (text.length <= maxChars) return [text];
    const lines = [];
    let rest = text;
    while (rest && lines.length < maxLines) {
      if (lines.length === maxLines - 1) {
        lines.push(rest.length > maxChars ? `${rest.slice(0, maxChars - 1)}…` : rest);
        break;
      }
      let split = rest.lastIndexOf("_", maxChars);
      if (split < Math.floor(maxChars * 0.55)) split = maxChars;
      lines.push(rest.slice(0, split));
      rest = rest.slice(split).replace(/^_/, "");
    }
    return lines;
  }

  function truncateMiddle(value, maxChars) {
    const text = String(value || "");
    if (text.length <= maxChars) return text;
    const side = Math.floor((maxChars - 1) / 2);
    return `${text.slice(0, side)}…${text.slice(-side)}`;
  }

  function makeSvg(tag, attrs) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    return el;
  }

  function beginNodeDrag(event, node) {
    if (event.button !== 0) return;
    event.stopPropagation();
    if (event.shiftKey) {
      if (selectedIds.has(node.id)) selectedIds.delete(node.id);
      else selectedIds.add(node.id);
    } else if (!selectedIds.has(node.id)) {
      selectedIds.clear();
      selectedIds.add(node.id);
    }
    if (!selectedIds.has(node.id)) {
      refreshSelection();
      return;
    }
    interaction = {
      type: "nodes",
      startX: event.clientX,
      startY: event.clientY,
      positions: [...selectedIds].map((id) => {
        const selected = nodeById.get(id);
        return { node: selected, x: selected.x, y: selected.y };
      }),
    };
    svg.setPointerCapture(event.pointerId);
    refreshSelection();
  }

  function beginBoxSelection(event) {
    interaction = {
      type: "box",
      startX: event.clientX,
      startY: event.clientY,
      currentX: event.clientX,
      currentY: event.clientY,
      additive: event.shiftKey,
    };
    svg.setPointerCapture(event.pointerId);
    svg.classList.add("box-selecting");
    updateSelectionBox();
  }

  function beginPan(event) {
    interaction = {
      type: "pan",
      startX: event.clientX,
      startY: event.clientY,
      tx: state.tx,
      ty: state.ty,
    };
    svg.setPointerCapture(event.pointerId);
    svg.classList.add("dragging");
  }

  function wireInteractions() {
    svg.onpointerdown = (event) => {
      if (event.button === 1 || (event.button === 0 && state.spaceDown)) {
        event.preventDefault();
        beginPan(event);
      } else if (event.button === 0) {
        beginBoxSelection(event);
      }
    };
    svg.onpointermove = (event) => {
      if (!interaction) return;
      if (interaction.type === "nodes") {
        const dx = (event.clientX - interaction.startX) / state.scale;
        const dy = (event.clientY - interaction.startY) / state.scale;
        for (const item of interaction.positions) {
          item.node.x = item.x + dx;
          item.node.y = item.y + dy;
          const group = nodeElement(item.node.id);
          if (group) group.setAttribute("transform", `translate(${item.node.x},${item.node.y})`);
          updateEdgesForNode(item.node);
        }
      } else if (interaction.type === "pan") {
        state.tx = interaction.tx + event.clientX - interaction.startX;
        state.ty = interaction.ty + event.clientY - interaction.startY;
        applyTransform();
      } else if (interaction.type === "box") {
        interaction.currentX = event.clientX;
        interaction.currentY = event.clientY;
        updateSelectionBox();
      }
    };
    svg.onpointerup = (event) => finishInteraction(event);
    svg.onpointercancel = () => cancelInteraction();
    svg.onwheel = (event) => {
      event.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;
      const graphX = (mouseX - state.tx) / state.scale;
      const graphY = (mouseY - state.ty) / state.scale;
      const factor = event.deltaY > 0 ? 0.9 : 1.1;
      const nextScale = Math.max(0.2, Math.min(2.5, state.scale * factor));
      state.tx = mouseX - graphX * nextScale;
      state.ty = mouseY - graphY * nextScale;
      state.scale = nextScale;
      applyTransform();
    };

    window.addEventListener("keydown", (event) => {
      if (event.code === "Space") {
        state.spaceDown = true;
        if (document.activeElement !== search) event.preventDefault();
      } else if (event.key.toLowerCase() === "b" && document.activeElement !== search) {
        state.boxMode = true;
        svg.classList.add("box-selecting");
      } else if (event.key === "Escape") {
        cancelInteraction();
        state.boxMode = false;
        svg.classList.remove("box-selecting");
      }
    });
    window.addEventListener("keyup", (event) => {
      if (event.code === "Space") state.spaceDown = false;
    });
  }

  function finishInteraction(event) {
    if (!interaction) return;
    if (interaction.type === "box") {
      interaction.currentX = event.clientX;
      interaction.currentY = event.clientY;
      const moved = Math.abs(interaction.currentX - interaction.startX) > 3
        || Math.abs(interaction.currentY - interaction.startY) > 3;
      if (moved) applyBoxSelection();
      else selectedIds.clear();
      selectionBox.style.display = "none";
      svg.classList.remove("box-selecting");
      state.boxMode = false;
      refreshSelection();
    }
    svg.classList.remove("dragging");
    interaction = null;
  }

  function cancelInteraction() {
    if (interaction && interaction.type === "nodes") {
      for (const item of interaction.positions) {
        item.node.x = item.x;
        item.node.y = item.y;
        const group = nodeElement(item.node.id);
        if (group) group.setAttribute("transform", `translate(${item.x},${item.y})`);
        updateEdgesForNode(item.node);
      }
    }
    interaction = null;
    selectionBox.style.display = "none";
    svg.classList.remove("dragging", "box-selecting");
  }

  function updateSelectionBox() {
    if (!interaction || interaction.type !== "box") return;
    const rect = graphWrap.getBoundingClientRect();
    const left = Math.min(interaction.startX, interaction.currentX) - rect.left;
    const top = Math.min(interaction.startY, interaction.currentY) - rect.top;
    selectionBox.style.display = "block";
    selectionBox.style.left = `${left}px`;
    selectionBox.style.top = `${top}px`;
    selectionBox.style.width = `${Math.abs(interaction.currentX - interaction.startX)}px`;
    selectionBox.style.height = `${Math.abs(interaction.currentY - interaction.startY)}px`;
  }

  function applyBoxSelection() {
    const svgRect = svg.getBoundingClientRect();
    const left = (Math.min(interaction.startX, interaction.currentX) - svgRect.left - state.tx) / state.scale;
    const right = (Math.max(interaction.startX, interaction.currentX) - svgRect.left - state.tx) / state.scale;
    const top = (Math.min(interaction.startY, interaction.currentY) - svgRect.top - state.ty) / state.scale;
    const bottom = (Math.max(interaction.startY, interaction.currentY) - svgRect.top - state.ty) / state.scale;
    const hits = graphData.nodes.filter((node) => (
      node.x < right
      && node.x + node.w > left
      && node.y < bottom
      && node.y + node.h > top
    ));
    if (!interaction.additive) selectedIds.clear();
    for (const node of hits) {
      if (interaction.additive && selectedIds.has(node.id)) selectedIds.delete(node.id);
      else selectedIds.add(node.id);
    }
  }

  function refreshSelection() {
    document.querySelectorAll(".node").forEach((el) => {
      el.classList.toggle("selected", selectedIds.has(el.dataset.id));
    });
    document.querySelectorAll(".edge-group").forEach((el) => {
      el.classList.toggle(
        "selected",
        selectedIds.has(el.dataset.from) || selectedIds.has(el.dataset.to),
      );
    });
    updateDetails();
  }

  function updateDetails() {
    const selected = [...selectedIds].map((id) => nodeById.get(id)).filter(Boolean);
    if (!selected.length) {
      details.innerHTML = "<h2>Details</h2><p>Select a node or drag a selection box.</p>";
      return;
    }
    if (selected.length > 1) {
      const counts = {};
      for (const node of selected) counts[node.type] = (counts[node.type] || 0) + 1;
      const types = Object.entries(counts).map(([type, count]) => `${type}: ${count}`).join(", ");
      const names = selected.map((node) => `<li>${escapeHtml(node.name)}</li>`).join("");
      details.innerHTML = `<h2>Selection</h2><div class="detail-row"><div class="detail-key">Nodes</div><div>${selected.length}</div></div><div class="detail-row"><div class="detail-key">Types</div><div>${escapeHtml(types)}</div></div><div class="detail-row"><div class="detail-key">Names</div><ul class="detail-list">${names}</ul></div>`;
      return;
    }
    const node = selected[0];
    const rows = Object.entries(node.details || {}).map(([key, value]) => {
      const display = Array.isArray(value) ? value.join("\n") : String(value);
      return `<div class="detail-row"><div class="detail-key">${escapeHtml(key)}</div><div>${escapeHtml(display || "-").replace(/\n/g, "<br>")}</div></div>`;
    }).join("");
    const pathRow = node.path
      ? `<div class="detail-row"><div class="detail-key">Path</div><div>${escapeHtml(node.path)}</div></div>`
      : "";
    details.innerHTML = `<h2>Details</h2><div class="detail-row"><div class="detail-key">Type</div><div>${escapeHtml(node.type)}</div></div><div class="detail-row"><div class="detail-key">Name</div><div>${escapeHtml(node.name)}</div></div>${pathRow}${rows}`;
  }

  function applySearch() {
    const query = state.query.toLowerCase();
    const matches = [];
    document.querySelectorAll(".node").forEach((el) => {
      const node = nodeById.get(el.dataset.id);
      const text = JSON.stringify(node || {}).toLowerCase();
      const hit = Boolean(query) && text.includes(query);
      if (hit && node) matches.push(node);
      el.classList.toggle("dim", Boolean(query) && !hit);
      el.classList.toggle("search-hit", hit);
    });
    document.querySelectorAll(".edge-group").forEach((el) => {
      const from = nodeById.get(el.dataset.from);
      const to = nodeById.get(el.dataset.to);
      const visible = !query
        || JSON.stringify(from || {}).toLowerCase().includes(query)
        || JSON.stringify(to || {}).toLowerCase().includes(query);
      el.classList.toggle("dim", !visible);
    });
    if (query && matches.length) focusNodes(matches);
  }

  function fitView() {
    const box = svg.getBoundingClientRect();
    if (!graphData.nodes.length || !box.width || !box.height) return;
    const minX = Math.min(...graphData.nodes.map((node) => node.x));
    const maxX = Math.max(...graphData.nodes.map((node) => node.x + node.w));
    const minY = Math.min(...graphData.nodes.map((node) => node.y));
    const maxY = Math.max(...graphData.nodes.map((node) => node.y + node.h));
    state.scale = Math.min(1.15, Math.max(0.22, Math.min(
      (box.width - 100) / (maxX - minX || 1),
      (box.height - 100) / (maxY - minY || 1),
    )));
    state.tx = (box.width - (minX + maxX) * state.scale) / 2;
    state.ty = (box.height - (minY + maxY) * state.scale) / 2;
    applyTransform();
  }

  function focusNodes(nodes) {
    const box = svg.getBoundingClientRect();
    if (!nodes.length || !box.width || !box.height) return;
    const minX = Math.min(...nodes.map((node) => node.x));
    const maxX = Math.max(...nodes.map((node) => node.x + node.w));
    const minY = Math.min(...nodes.map((node) => node.y));
    const maxY = Math.max(...nodes.map((node) => node.y + node.h));
    const padding = nodes.length === 1 ? 240 : 150;
    const nextScale = Math.min(1.25, Math.max(0.35, Math.min(
      (box.width - padding) / (maxX - minX || 1),
      (box.height - padding) / (maxY - minY || 1),
    )));
    state.scale = nextScale;
    state.tx = (box.width - (minX + maxX) * state.scale) / 2;
    state.ty = (box.height - (minY + maxY) * state.scale) / 2;
    applyTransform();
  }

  function applyTransform() {
    if (root) root.setAttribute("transform", `translate(${state.tx},${state.ty}) scale(${state.scale})`);
  }

  function nodeElement(id) {
    return [...document.querySelectorAll(".node")].find((el) => el.dataset.id === id);
  }

  function updateEdgesForNode(node) {
    document.querySelectorAll(".edge-group").forEach((group) => {
      if (group.dataset.from !== node.id && group.dataset.to !== node.id) return;
      const from = nodeById.get(group.dataset.from);
      const to = nodeById.get(group.dataset.to);
      const geometry = edgeGeometry(from, to);
      group.querySelector(".edge").setAttribute("d", geometry.d);
      group.querySelector(".edge-label").setAttribute(
        "transform",
        `translate(${geometry.labelX},${geometry.labelY})`,
      );
    });
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

  function syncPanelSwap() {
    document.body.classList.toggle("panels-swapped", localStorage.getItem(panelSwapKey) === "1");
  }

  function togglePanelSwap() {
    const next = !document.body.classList.contains("panels-swapped");
    localStorage.setItem(panelSwapKey, next ? "1" : "0");
    syncPanelSwap();
    fitView();
  }

  function exportJson() {
    const payload = `${JSON.stringify(graphData, null, 2)}\n`;
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const targetName = graphData.meta.target_name || "blend_reference_graph";
    link.href = url;
    link.download = `${fileSafeName(targetName)}_graph.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function fileSafeName(value) {
    return String(value || "graph").replace(/[\\/:*?"<>|\s]+/g, "_").replace(/^_+|_+$/g, "") || "graph";
  }

  document.getElementById("reload").addEventListener("click", () => window.location.reload());
  document.getElementById("fit").addEventListener("click", fitView);
  document.getElementById("export-json").addEventListener("click", exportJson);
  document.getElementById("swap-panels").addEventListener("click", togglePanelSwap);
  document.getElementById("github").addEventListener("click", () => {
    window.open(githubUrl, "_blank", "noopener");
  });
  search.addEventListener("input", (event) => {
    state.query = event.target.value;
    applySearch();
  });

  init();
}());

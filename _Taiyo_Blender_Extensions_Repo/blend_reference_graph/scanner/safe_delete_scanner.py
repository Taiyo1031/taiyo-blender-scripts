def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_safe_delete_preview(graph, target_id, filters):
    if not target_id or target_id not in graph.nodes or not _allowed(filters, "SAFE_DELETE"):
        return
    preview_id = f"SafeDelete:{target_id}"
    target = graph.nodes[target_id]
    incoming = [
        edge for edge in graph.edges
        if edge["to"] == target_id and edge["from"] != preview_id
    ]
    outgoing = [
        edge for edge in graph.edges
        if edge["from"] == target_id and edge["to"] != preview_id
    ]
    blockers = [_edge_summary(graph, edge) for edge in incoming]
    references = [_edge_summary(graph, edge) for edge in outgoing]
    status = "Blocked" if blockers else "No blockers in scanned graph"
    graph.add_node(
        preview_id,
        "SAFE_DELETE",
        "Safe Delete Preview",
        "SAFE DELETE",
        details={
            "target": f"{target['type']} {target['name']}",
            "status": status,
            "blocker_count": len(blockers),
            "blockers": blockers,
            "outgoing_reference_count": len(references),
            "outgoing_references": references,
            "scope": "Preview is limited to references included in this graph scan.",
        },
    )
    graph.add_edge(preview_id, target_id, "previews_delete", "safe delete")
    for edge in incoming:
        graph.add_edge(edge["from"], preview_id, "delete_blocker", "blocks delete")


def _edge_summary(graph, edge):
    source = graph.nodes.get(edge["from"], {"type": "?", "name": edge["from"]})
    target = graph.nodes.get(edge["to"], {"type": "?", "name": edge["to"]})
    label = edge.get("label") or edge.get("relation", "reference")
    return f"{source['type']} {source['name']} --{label}--> {target['type']} {target['name']}"

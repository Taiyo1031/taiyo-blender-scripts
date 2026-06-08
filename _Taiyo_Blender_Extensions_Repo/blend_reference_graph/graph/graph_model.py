class GraphData:
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self._edge_keys = set()

    def add_node(self, node_id, node_type, name, label=None, path="", details=None):
        if not node_id or node_id in self.nodes:
            return
        self.nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "name": name,
            "label": label or name,
            "path": path,
            "details": details or {},
        }

    def add_edge(self, from_id, to_id, relation, label):
        if not from_id or not to_id:
            return
        if from_id not in self.nodes or to_id not in self.nodes:
            return
        key = (from_id, to_id, relation)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append({
            "from": from_id,
            "to": to_id,
            "relation": relation,
            "label": label,
        })

    def as_payload(self, meta):
        return {
            "meta": {
                **meta,
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
            },
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
        }

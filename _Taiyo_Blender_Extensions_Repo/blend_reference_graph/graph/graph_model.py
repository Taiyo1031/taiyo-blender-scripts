from collections import Counter

from ..version import VERSION


class GraphData:
    def __init__(self):
        self.meta = {"scope": "TARGET", "version": VERSION, "scan_seconds": 0.0, "truncated": []}
        self.node_limits = {}
        self.type_counts = Counter()
        self.nodes = {}
        self.edges = []
        self._edge_keys = set()

    def add_node(self, node_id, node_type, name, label=None, path="", details=None, group=None):
        if not node_id or node_id in self.nodes:
            return
        limit = self.node_limits.get(node_type)
        if limit is not None and self.type_counts[node_type] >= limit:
            message = f"{node_type}: limited to {limit} nodes"
            if message not in self.meta["truncated"]:
                self.meta["truncated"].append(message)
            return
        self.type_counts[node_type] += 1
        self.nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "group": group or node_type,
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
                **self.meta,
                **meta,
                "type_counts": dict(self.type_counts),
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
            },
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
        }

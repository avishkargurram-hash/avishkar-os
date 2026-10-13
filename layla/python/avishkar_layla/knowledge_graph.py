"""LaylaKnowledgeGraph -- Mission Layla Part 5. See CONTRACT.md SS26.

A real, minimal, from-scratch graph engine: typed nodes and edges with
confidence/provenance, real BFS-based neighbor/path queries, no seed
data of any kind. Persisted through the same `LaylaMemoryPolicy` every
other Layla component uses -- not a second knowledge system. Avishkar's
existing Knowledge Framework (Phase 6) is vector-search over documents;
this is a structurally different concern (typed entity relationships),
additive, not a duplicate or a replacement.

Referential integrity is enforced: `add_edge()` refuses to create an
edge to/from a node that doesn't exist -- a real, cheap correctness
check this mission's forensic audit confirmed GENESIS's own
`core/knowledge_graph.py` does not perform. No entity is ever seeded
by default (contrast GENESIS's `seed_foundation_knowledge()`, confirmed
by that same audit to hardcode the owner's real email address directly
in source) -- every node/edge in this graph is written only by an
explicit runtime call.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .errors import LaylaError
from .memory_policy import LaylaMemoryPolicy

_KIND = "long_term"
_NODE_INDEX_KEY = "kg:__node_index__"
_EDGE_INDEX_KEY = "kg:__edge_index__"


class NodeNotFoundError(LaylaError):
    """add_edge() referenced a source_id/target_id with no such node --
    referential integrity, enforced, not assumed.
    """


def _iso(epoch_seconds: float) -> str:
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class GraphNode:
    id: str
    node_type: str
    label: str
    properties: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    confidence: float = 1.0
    provenance: str = "user"
    created_at: str = ""
    updated_at: str = ""


@dataclasses.dataclass(frozen=True)
class GraphEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    confidence: float = 1.0
    created_at: str = ""


class LaylaKnowledgeGraph:
    def __init__(self, memory: LaylaMemoryPolicy, *, clock: Callable[[], float] = time.time) -> None:
        self._memory = memory
        self._clock = clock
        self._lock = threading.Lock()  # ADR-0024 discipline: guards each index's read-modify-write

    def _node_key(self, node_id: str) -> str:
        return f"kg:node:{node_id}"

    def _edge_key(self, edge_id: str) -> str:
        return f"kg:edge:{edge_id}"

    def add_node(
        self, node_id: str, node_type: str, label: str, properties: Optional[Mapping[str, Any]] = None, *,
        confidence: float = 1.0, provenance: str = "user",
    ) -> GraphNode:
        now = _iso(self._clock())
        existing = self.get_node(node_id)
        node = GraphNode(
            id=node_id, node_type=node_type, label=label, properties=dict(properties or {}),
            confidence=confidence, provenance=provenance,
            created_at=existing.created_at if existing else now, updated_at=now,
        )
        self._memory.remember(_KIND, self._node_key(node_id), dataclasses.asdict(node), provenance="knowledge-graph")
        with self._lock:
            index_record = self._memory.recall(_KIND, _NODE_INDEX_KEY)
            ids = set(index_record.value) if index_record else set()
            ids.add(node_id)
            self._memory.remember(_KIND, _NODE_INDEX_KEY, sorted(ids), provenance="knowledge-graph")
        return node

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        record = self._memory.recall(_KIND, self._node_key(node_id))
        return GraphNode(**record.value) if record is not None else None

    def add_edge(
        self, edge_id: str, source_id: str, target_id: str, relation_type: str,
        properties: Optional[Mapping[str, Any]] = None, *, confidence: float = 1.0,
    ) -> GraphEdge:
        if self.get_node(source_id) is None:
            raise NodeNotFoundError(f"add_edge: no node {source_id!r} (source) -- add_node() first")
        if self.get_node(target_id) is None:
            raise NodeNotFoundError(f"add_edge: no node {target_id!r} (target) -- add_node() first")
        edge = GraphEdge(
            id=edge_id, source_id=source_id, target_id=target_id, relation_type=relation_type,
            properties=dict(properties or {}), confidence=confidence, created_at=_iso(self._clock()),
        )
        self._memory.remember(_KIND, self._edge_key(edge_id), dataclasses.asdict(edge), provenance="knowledge-graph")
        with self._lock:
            index_record = self._memory.recall(_KIND, _EDGE_INDEX_KEY)
            ids = set(index_record.value) if index_record else set()
            ids.add(edge_id)
            self._memory.remember(_KIND, _EDGE_INDEX_KEY, sorted(ids), provenance="knowledge-graph")
        return edge

    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        record = self._memory.recall(_KIND, self._edge_key(edge_id))
        return GraphEdge(**record.value) if record is not None else None

    def list_nodes(self) -> Tuple[GraphNode, ...]:
        index_record = self._memory.recall(_KIND, _NODE_INDEX_KEY)
        if index_record is None:
            return ()
        nodes = (self.get_node(nid) for nid in index_record.value)
        return tuple(n for n in nodes if n is not None)

    def list_edges(self) -> Tuple[GraphEdge, ...]:
        index_record = self._memory.recall(_KIND, _EDGE_INDEX_KEY)
        if index_record is None:
            return ()
        edges = (self.get_edge(eid) for eid in index_record.value)
        return tuple(e for e in edges if e is not None)

    def query_by_type(self, node_type: str) -> Tuple[GraphNode, ...]:
        return tuple(n for n in self.list_nodes() if n.node_type == node_type)

    def neighbors(self, node_id: str) -> Tuple[GraphEdge, ...]:
        """Every edge touching this node, either direction -- real
        adjacency computed from the real edge list, not cached/stale.
        """
        return tuple(e for e in self.list_edges() if e.source_id == node_id or e.target_id == node_id)

    def _adjacency(self) -> Dict[str, Tuple[str, ...]]:
        adj: Dict[str, list] = collections.defaultdict(list)
        for edge in self.list_edges():
            adj[edge.source_id].append(edge.target_id)
            adj[edge.target_id].append(edge.source_id)  # undirected traversal for BFS/path purposes
        return {k: tuple(v) for k, v in adj.items()}

    def bfs(self, start_id: str, *, max_depth: int = 3) -> Dict[str, int]:
        """Real breadth-first search -- {node_id: depth}, start_id at
        depth 0. Returns {} if start_id has no node.
        """
        if self.get_node(start_id) is None:
            return {}
        adjacency = self._adjacency()
        visited = {start_id: 0}
        queue = collections.deque([start_id])
        while queue:
            current = queue.popleft()
            depth = visited[current]
            if depth >= max_depth:
                continue
            for neighbor in adjacency.get(current, ()):
                if neighbor not in visited:
                    visited[neighbor] = depth + 1
                    queue.append(neighbor)
        return visited

    def shortest_path(self, source_id: str, target_id: str) -> Optional[Tuple[str, ...]]:
        """Real BFS shortest-path (unweighted). None if no path exists
        or either node is missing.
        """
        if self.get_node(source_id) is None or self.get_node(target_id) is None:
            return None
        if source_id == target_id:
            return (source_id,)
        adjacency = self._adjacency()
        parent: Dict[str, Optional[str]] = {source_id: None}
        queue = collections.deque([source_id])
        while queue:
            current = queue.popleft()
            if current == target_id:
                path = [current]
                while parent[path[-1]] is not None:
                    path.append(parent[path[-1]])
                return tuple(reversed(path))
            for neighbor in adjacency.get(current, ()):
                if neighbor not in parent:
                    parent[neighbor] = current
                    queue.append(neighbor)
        return None

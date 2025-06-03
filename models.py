from copy import deepcopy
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from geometry_connector.enums import MatchType
from mathutils import Vector, Quaternion, Matrix


@dataclass
class Edge:
    new_index: int
    orig_indices: List[int]
    length: float
    vertices: List[List[float]]


@dataclass
class Face:
    new_index: int
    orig_indices: List[int]
    area: float
    face_type: int
    normal: Vector
    edges: List[Edge]
    vertices: List[List[float]]


@dataclass
class Mesh:
    name: str
    size: List[float]
    convex_points: List[int]
    concave_points: List[int]
    flat_points: List[int]
    matrix_world: Matrix
    faces: List[Face]

    @property
    def edges(self) -> List[Edge]:
        result = []
        for f in self.faces:
            result.extend(f.edges)
        return result

    @property
    def volume(self) -> float:
        x, y, z = self.size
        return x * y * z


@dataclass
class GraphMatch:
    mesh1: str
    mesh2: str
    match_type: MatchType
    indices: Tuple[int, int]
    coeff: float
    edges: List[Tuple[Edge, Edge]] = field(default_factory=list)

    @property
    def inverted(self) -> "GraphMatch":
        inverted_edges = [(deepcopy(e2), deepcopy(e1)) for e1, e2 in self.edges]

        return GraphMatch(
            mesh1=self.mesh2,
            mesh2=self.mesh1,
            match_type=self.match_type,
            indices=(self.indices[1], self.indices[0]),
            coeff=self.coeff,
            edges=inverted_edges,
        )


# Граф: MeshName -> Connected MeshNames -> info about connection
class MeshGraph:
    def __init__(self):
        self.connections: Dict[str, Dict[str, List[GraphMatch]]] = {}

    def add_match(self, match: GraphMatch):
        self.connections.setdefault(match.mesh1, {}).setdefault(match.mesh2, []).append(match)
        self.connections.setdefault(match.mesh2, {}).setdefault(match.mesh1, []).append(match.inverted)
        print(f"В граф добавлено совпадение: {match.mesh1} ↔ {match.mesh2}")
        print(f"  - {match.match_type}: indices {match.indices[0]} ↔ {match.indices[1]}, coeff = {match.coeff:.3f}")


@dataclass
class Network:
    matches: List[GraphMatch]
    weight: float = field(init = False)

    def __post_init__(self):
        # Считаем вес как сумму coeff всех совпадений
        self.weight = sum(m.coeff for m in self.matches)


@dataclass
class TransformMatch:
    src_mesh_name: str
    dst_mesh_name: str
    matrix_world: Matrix
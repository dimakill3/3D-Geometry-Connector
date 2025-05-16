from dataclasses import dataclass, field
from typing import List, Tuple, Dict
from geometry_connector.enums import MatchType
from mathutils import Vector, Quaternion


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
    faces: List[Face]


@dataclass
class GraphMatch:
    mesh1: str
    mesh2: str
    match_type: MatchType
    indices: Tuple[int, int]
    coeff: float


# Граф: MeshName -> Connected MeshNames -> info about connection
class MeshGraph:
    def __init__(self):
        self.adj: Dict[str, Dict[str, List[GraphMatch]]] = {}

    def add_match(self, match: GraphMatch):
        self.adj.setdefault(match.mesh1, {}).setdefault(match.mesh2, []).append(match)
        self.adj.setdefault(match.mesh2, {}).setdefault(match.mesh1, []).append(
            GraphMatch(match.mesh2, match.mesh1, match.match_type, match.indices, match.coeff)
        )
        print(f"Добавлено совпадение: {match}")


@dataclass
class Network:
    matches: List[GraphMatch]
    weight: float = field(init = False)

    def __post_init__(self):
        # Считаем вес как сумму coeff всех совпадений
        self.weight = sum(m.coeff for m in self.matches)


@dataclass
class TransformMatch:
    match: GraphMatch
    rotation: Quaternion
    translation: Vector
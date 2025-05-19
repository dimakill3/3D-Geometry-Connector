import math
from typing import List, Tuple
from geometry_connector import math_utils
from geometry_connector.enums import MatchType
from geometry_connector.models import GraphMatch, Face, Edge, Mesh, MeshGraph
from geometry_connector.reader import JsonMeshReader
from geometry_connector.constants import AREA_PENALTY, EDGE_PENALTY, NORMAL_PENALTY, MIN_MATCH_FACE_COEFF
from geometry_connector.writer import Writer
from mathutils import Vector, Matrix
import bpy


# Сравнение нормалей граней с учётом выравнивания совпавших рёбер
def compare_normals(f1: Face, f2: Face, matching_edges: List[Tuple[Edge, Edge]]) -> bool:
    # Порог и его косинус
    threshold = bpy.context.scene.connected_edge_angle_threshold
    cos_th = math.cos(threshold)

    # Собираем направляющие векторы по рёбрам
    v1_list: List[Vector] = []
    v2_list: List[Vector] = []
    for e1, e2 in matching_edges:
        p1a, p1b = map(Vector, e1.vertices)
        p2a, p2b = map(Vector, e2.vertices)
        v1_list.append((p1b - p1a).normalized())
        v2_list.append((p2b - p2a).normalized())

    if not v1_list:
        return False

    # Ориентируем первую пару
    v1_ref = v1_list[0]
    raw_v2_ref = v2_list[0]
    sign_ref = 1.0 if v1_ref.dot(raw_v2_ref) >= 0.0 else -1.0
    v2_ref = (raw_v2_ref * sign_ref).normalized()

    # Нормали граней
    n1 = f1.normal.normalized()
    n2 = f2.normal.normalized()

    # Сбор базисов и матриц
    x1, z1 = v1_ref, -n1
    y1 = z1.cross(x1).normalized()
    M1 = Matrix((x1, y1, z1)).transposed()

    x2, z2 = v2_ref, n2
    y2 = z2.cross(x2).normalized()
    M2 = Matrix((x2, y2, z2)).transposed()

    # Инверсия M2
    try:
        M2_inv = M2.inverted()
    except Exception:
        return False

    # Матрица вращения
    R = M1 @ M2_inv

    # Проверяем все остальные рёбра через скалярное произведение
    for v1_i, raw_v2_i in zip(v1_list, v2_list):
        sign_i = 1.0 if v1_i.dot(raw_v2_i) >= 0.0 else -1.0
        v2o = (raw_v2_i * sign_i).normalized()
        v2_rot = R @ v2o
        if v1_i.dot(v2_rot) < cos_th:
            return False

    # Финальная проверка нормалей граней
    n2_rot = R @ n2
    if n2_rot.dot(-n1) > cos_th:
        return True

    return False


# Построение графа совпадений обломков
def build_mesh_graph(pieces_meshes: List[Mesh]) -> MeshGraph:
    scene = bpy.context.scene
    area_th = scene.area_threshold
    edge_th = scene.edge_threshold

    pieces_graph = MeshGraph()

    # Поиск совпадений по граням
    for i, m1 in enumerate(pieces_meshes):
        for m2 in pieces_meshes[i + 1:]:
            for f1 in m1.faces:
                a1 = f1.area
                edges1 = f1.edges
                n1 = len(edges1)

                for f2 in m2.faces:
                    coeff = 1.0

                    # Сравнение площадей
                    if not math_utils.compare_values(a1, f2.area, area_th):
                        coeff -= AREA_PENALTY

                    # Подготовка рёбер
                    edges2 = f2.edges
                    n2 = len(edges2)
                    n_max = max(n1, n2)
                    if n1 != n2:
                        coeff -= (n_max - min(n1, n2)) / n_max * EDGE_PENALTY

                    # Сопоставление рёбер
                    matched_edges = []
                    used = set()
                    for e1 in edges1:
                        found = False
                        for e2 in edges2:
                            if e2.new_index in used:
                                continue
                            if math_utils.compare_values(e1.length, e2.length, edge_th):
                                used.add(e2.new_index)
                                if n1 <= n2:
                                    matched_edges.append((e1, e2))
                                else:
                                    matched_edges.append((e2, e1))
                                found = True
                                break
                        if not found:
                            coeff -= EDGE_PENALTY / n_max

                    # Сравнение нормалей, если есть достаточно рёбер
                    if len(matched_edges) > 2:
                        if not compare_normals(f1, f2, matched_edges):
                            coeff -= NORMAL_PENALTY
                        else:

                            if coeff < MIN_MATCH_FACE_COEFF:
                                coeff = MIN_MATCH_FACE_COEFF

                    # Добавляем совпадение, если коэффициент удовлетворён
                    if coeff >= MIN_MATCH_FACE_COEFF:
                        pieces_graph.add_match(GraphMatch(
                            mesh1=m1.name,
                            mesh2=m2.name,
                            match_type=MatchType.FACE,
                            indices=(f1.new_index, f2.new_index),
                            coeff=coeff,
                            edges=matched_edges
                        ))

    # Поиск совпадений по рёбрам
    for i, m1 in enumerate(pieces_meshes):
        for m2 in pieces_meshes[i + 1:]:
            min_coeff = MIN_MATCH_FACE_COEFF
            # Исключаем рёбра, у которых грани уже совпали по FACE
            existing = pieces_graph.adj.get(m1.name, {}).get(m2.name, [])
            used_face_idxs = {
                match.indices[0]
                for match in existing
                if match.match_type == MatchType.FACE
            }

            edges1 = [e for f in m1.faces if f.new_index not in used_face_idxs for e in f.edges]
            edges2 = [e for f in m2.faces if f.new_index not in used_face_idxs for e in f.edges]

            for e1 in edges1:
                for e2 in edges2:
                    max_len = max(e1.length, e2.length)
                    coeff = 1 - abs(e1.length / max_len - e2.length / max_len)
                    if coeff >= min_coeff:
                        pieces_graph.add_match(GraphMatch(
                            mesh1=m1.name,
                            mesh2=m2.name,
                            match_type=MatchType.EDGE,
                            indices=(e1.new_index, e2.new_index),
                            coeff=coeff
                        ))
                        min_coeff = coeff

    return pieces_graph


if __name__ == '__main__':
    meshes = JsonMeshReader.read()
    graph = build_mesh_graph(meshes)
    Writer.print_graph(graph)

from typing import List, Tuple
from geometry_connector import math_utils
from geometry_connector.enums import MatchType
from geometry_connector.models import GraphMatch, Face, Edge, Mesh, MeshGraph
from geometry_connector.reader import JsonMeshReader
from geometry_connector.constants import AREA_PENALTY, EDGE_PENALTY, NORMAL_PENALTY, MIN_MATCH_FACE_COEFF, MIN_MATCH_EDGE_COEFF
from geometry_connector.writer import Writer
from mathutils import Vector, Matrix
import bpy


# Сравнение нормалей граней с учётом выравнивания совпавших рёбер
def compare_normals(f1: Face, f2: Face, matching_edges: List[Tuple[Edge, Edge]]) -> bool:
    scene = bpy.context.scene
    threshold = scene.connected_edge_angle_threshold
    print(f"--- compare_normals start ---\nThreshold = {threshold}")

    # Сами грани
    print(f"f1.normal raw = {f1.normal}, f2.normal raw = {f2.normal}")

    # Собираем пары направляющих векторов для каждого совпавшего ребра
    v1_list: List[Vector] = []
    v2_list: List[Vector] = []
    for idx, (e1, e2) in enumerate(matching_edges):
        p1a, p1b = map(Vector, e1.vertices)
        p2a, p2b = map(Vector, e2.vertices)
        v1 = (p1b - p1a).normalized()
        v2 = (p2b - p2a).normalized()
        v1_list.append(v1)
        v2_list.append(v2)
        print(f"Edge {idx}: v1 = {v1}, v2 = {v2}")

    if not v1_list:
        print("No edges → False")
        return False

    # Ориентируем первую пару
    v1_ref = v1_list[0]
    raw_v2_ref = v2_list[0]
    sign_ref = 1.0 if v1_ref.dot(raw_v2_ref) >= 0.0 else -1.0
    v2_ref = (raw_v2_ref * sign_ref).normalized()
    print(f"Reference: v1_ref = {v1_ref}")
    print(f"Raw v2_ref = {raw_v2_ref}, sign_ref = {sign_ref}, oriented v2_ref = {v2_ref}")

    # Нормали
    n1 = f1.normal.normalized()
    n2 = f2.normal.normalized()
    print(f"Normalized normals: n1 = {n1}, n2 = {n2}")

    # Строим базис для f1
    x1 = v1_ref
    z1 = -n1
    y1 = z1.cross(x1).normalized()
    M1 = Matrix((x1, y1, z1)).transposed()
    print("Basis M1:")
    for row in M1:
        print(f"  {row}")
    print(f"det(M1) = {M1.determinant()}")

    # Строим базис для f2
    x2 = v2_ref
    z2 = n2
    y2 = z2.cross(x2).normalized()
    M2 = Matrix((x2, y2, z2)).transposed()
    print("Basis M2:")
    for row in M2:
        print(f"  {row}")
    print(f"det(M2) = {M2.determinant()}")

    # Инверсия M2
    try:
        M2_inv = M2.inverted()
        print("M2.inverted() succeeded")
    except Exception as e:
        print(f"M2.inverted() failed: {e}")
        return False

    # Вычисляем матрицу вращения
    R = M1 @ M2_inv
    print("Rotation matrix R = M1 @ M2^{-1}:")
    for row in R:
        print(f"  {row}")
    print(f"det(R) = {R.determinant()}")

    # Проверяем все остальные рёбра
    for idx, (v1_i, v2_i) in enumerate(zip(v1_list, v2_list)):
        sign_i = 1.0 if v1_i.dot(v2_i) >= 0.0 else -1.0
        v2o = (v2_i * sign_i).normalized()
        v2_rot = R @ v2o
        angle = v1_i.angle(v2_rot)
        print(f"Check edge {idx}:")
        print(f"  v1_i = {v1_i}, raw v2_i = {v2_i}, sign_i = {sign_i}, v2o = {v2o}")
        print(f"  v2_rot = {v2_rot}, angle = {angle}")
        if angle > threshold:
            print(f"  Angle {angle} > threshold {threshold} → False")
            return False

    # Финальная проверка нормалей
    n2_rot = R @ n2
    angle_n = n2_rot.angle(-n1)
    print(f"Rotated f2.normal = {n2_rot}")
    print(f"Angle between rotated f2.normal and -f1.normal = {angle_n}")
    if angle_n < threshold:
        print("Normals match → True")
        return True
    else:
        print("Normals do not match → False")
        return False


# Построение графа совпадений обломков
def build_mesh_graph(meshes: List[Mesh]) -> MeshGraph:
    added_logs = []
    scene = bpy.context.scene
    graph = MeshGraph()

    added_logs.append("...Поиск совпадений по граням...")
    for i, m1 in enumerate(meshes):
        for m2 in meshes[i+1:]:
            added_logs.append(f"Обработка мэшей {m1.name} и {m2.name}. Начало...")
            for f1 in m1.faces:
                for f2 in m2.faces:
                    local_logs = []
                    local_logs.append(f"Обработка мэшей {m1.name} и {m2.name}. Грань1 {f1.new_index}. Грань2 {f2.new_index}")
                    coeff = 1.0

                    local_logs.append(f"Площадь... {f1.area} ?? {f2.area}")
                    # Сравниваем площадь
                    if not math_utils.compare_values(f1.area, f2.area, scene.area_threshold):
                        coeff -= AREA_PENALTY
                        local_logs.append( f"Несоответствие площади!!!")

                    local_logs.append(f"Рёбра...")
                    # Сравниваем длины рёбер
                    edges1 = f1.edges
                    edges2 = f2.edges
                    n1, n2 = len(edges1), len(edges2)
                    n_max = max(n1, n2)

                    local_logs.append(f"n1 = {n1}, n2 = {n2}, edges1 = {[e.length for e in edges1]}, edges2 = {[e.length for e in edges2]}")

                    # Штрафуем за «лишние» рёбра
                    coeff -= (n_max - min(n1, n2)) / n_max * EDGE_PENALTY
                    if n1 != n2:
                        local_logs.append(f"Несоответствие по количеству!!!")

                    min_edges, max_edges = (edges1, edges2) if n1 <= n2 else (edges2, edges1)
                    used = set()
                    matched_edges: List[Tuple[Edge, Edge]] = []

                    for e1 in min_edges:
                        found = False
                        for e2 in max_edges:
                            if e2.new_index in used:
                                continue
                            local_logs.append(f"{abs(e1.length - e2.length)} {scene.edge_threshold} {math_utils.compare_values(e1.length, e2.length, scene.edge_threshold)}")
                            if math_utils.compare_values(e1.length, e2.length, scene.edge_threshold):
                                used.add(e2.new_index)
                                if n1 <= n2:
                                    matched_edges.append((e1, e2))
                                else:
                                    matched_edges.append((e2, e1))
                                found = True
                                break
                        if not found:
                            coeff -= EDGE_PENALTY / n_max
                            local_logs.append(f"Несоответствие по длине!!! e1 = {e1.length}")

                    local_logs.append(f"Нормаль...")
                    # Сравниваем нормали
                    normals_ok = False
                    if len(matched_edges) > 2:
                        if compare_normals(f1, f2, matched_edges):
                            normals_ok = True
                        else:
                            coeff -= NORMAL_PENALTY
                            local_logs.append(f"Несоответствие нормали!!!")

                    if normals_ok and coeff < MIN_MATCH_FACE_COEFF:
                        coeff = MIN_MATCH_FACE_COEFF

                    # Добавляем совпадение
                    if coeff >= MIN_MATCH_FACE_COEFF:
                        graph.add_match(GraphMatch(
                            m1.name, m2.name,
                            MatchType.FACE,
                            (f1.new_index, f2.new_index),
                            coeff,
                            edges=matched_edges
                        ))
                        added_logs.append(local_logs)

    print("Поиск совпадений по рёбрам...")
    for i, m1 in enumerate(meshes):
        for m2 in meshes[i+1:]:
            min_coeff = MIN_MATCH_FACE_COEFF
            # Исключаем ребра, принадлежащие совпавшим граням
            matched_faces = {idx for match in graph.adj.get(m1.name, {}).get(m2.name, []) if match.match_type==MatchType.FACE for idx in [match.indices[0]]}
            edges1 = [e for f in m1.faces if f.new_index not in matched_faces for e in f.edges]
            edges2 = [e for f in m2.faces if f.new_index not in matched_faces for e in f.edges]
            for e1 in edges1:
                for e2 in edges2:
                    max_length = max(e1.length, e2.length)
                    coeff = 1 - abs(e1.length / max_length - e2.length / max_length)

                    if coeff >= min_coeff:
                        graph.add_match(GraphMatch(m1.name, m2.name, MatchType.EDGE, (e1.new_index, e2.new_index), coeff))
                        min_coeff = coeff

    for line in added_logs:
        print(line)
        print('\n')
    return graph


if __name__ == '__main__':
    meshes = JsonMeshReader.read()
    graph = build_mesh_graph(meshes)
    Writer.print_graph(graph)

from typing import List, Tuple
from geometry_connector import math_utils
from geometry_connector.enums import MatchType
from geometry_connector.models import GraphMatch, Face, Edge, Mesh, MeshGraph
from geometry_connector.reader import JsonMeshReader
from geometry_connector.constants import MIN_MATCH_COEFF, AREA_PENALTY, EDGE_PENALTY, NORMAL_PENALTY
from geometry_connector.writer import Writer
from mathutils import Vector, Matrix
import bpy


# Сравнение нормалей граней с учётом выравнивания совпавших рёбер
def compare_normals(f1: Face, f2: Face, matching_edges: List[Tuple[Edge, Edge]]) -> bool:
    scene = bpy.context.scene

    # Собираем пары направляющих векторов для каждого совпавшего ребра
    v1_list = []
    v2_list = []
    for e1, e2 in matching_edges:
        p1a, p1b = map(Vector, e1.vertices)
        p2a, p2b = map(Vector, e2.vertices)
        v1_list.append((p1b - p1a).normalized())
        v2_list.append((p2b - p2a).normalized())

    if len(v1_list) < 1:
        return False

    # Ориентируем первую пару
    v1_ref = v1_list[0]
    raw_v2_ref = v2_list[0]
    sign = 1.0 if v1_ref.dot(raw_v2_ref) >= 0 else -1.0
    v2_ref = (raw_v2_ref * sign).normalized()
    print(f"Reference v1_ref = {v1_ref}")
    print(f"Raw v2_ref = {raw_v2_ref}, sign = {sign}, oriented v2_ref = {v2_ref}")


    # Строим базисы
    x1 = v1_ref
    z1 = (-f1.normal).normalized()  # цель — противоположная нормаль
    y1 = z1.cross(x1).normalized()
    M1 = Matrix((x1, y1, z1)).transposed()

    x2 = v2_ref
    z2 = f2.normal.normalized()
    y2 = z2.cross(x2).normalized()
    M2 = Matrix((x2, y2, z2)).transposed()

    # Матрица вращения f2 -> f1
    R = M1 @ M2.inverted()

    # Проверяем, что все остальные рёбра тоже «станут» параллельны
    threshold = scene.connected_edge_angle_threshold
    for idx, (v1_i, v2_i) in enumerate(zip(v1_list, v2_list)):
        sign_i = 1.0 if v1_i.dot(v2_i) >= 0 else -1.0
        v2o = (v2_i * sign_i).normalized()
        v2_rot = R @ v2o
        angle = v1_i.angle(v2_rot)
        print(f"Check edge {idx}: v1_i={v1_i}, raw v2_i={v2_i}, sign_i={sign_i}, v2o={v2o}")
        print(f"Rotated v2o = {v2_rot}, angle with v1_i = {angle}")
        if angle > threshold:
            print(f"Angle {angle} exceeds threshold {threshold}, returning False.")
            return False

    # Проверяем нормали: f2.normal после поворота должна совпасть с -f1.normal
    n2_rot = R @ f2.normal
    dot = f1.normal.dot(n2_rot)
    print(f"Rotated normal f2: {n2_rot}, dot with f1.normal = {dot}")
    if abs(dot + 1.0) < threshold:
        print("Normals are opposite, returning True.")
        return True
    else:
        print("Normals are not opposite, returning False.")
        return False


# Построение графа совпадений обломков
def build_mesh_graph(meshes: List[Mesh]) -> MeshGraph:
    scene = bpy.context.scene
    graph = MeshGraph()

    print("...Поиск совпадений по граням...")
    for i, m1 in enumerate(meshes):
        print(f"Обработка мэша {m1.name}. Начало...")
        for m2 in meshes[i+1:]:
            for f1 in m1.faces:
                print(f"Обработка мэша {m1.name}. Грань {f1.new_index}. Начало...")
                for f2 in m2.faces:
                    print(f"Обработка мэша {m1.name}. Грань {f1.new_index}. Грань {f2.new_index}")
                    coeff = 1.0

                    print(f"Обработка мэша {m1.name}. Грань {f1.new_index}. Грань {f2.new_index}. Площадь... {f1.area} ?? {f2.area}")
                    # Сравниваем площадь
                    if not math_utils.compare_values(f1.area, f2.area, scene.area_threshold):
                        coeff -= AREA_PENALTY
                        print( f"Несоответствие площади!!!")

                    print(f"Обработка мэша {m1.name}. Грань {f1.new_index}. Грань {f2.new_index}. Рёбра...")
                    # Сравниваем длины рёбер
                    edges1 = f1.edges
                    edges2 = f2.edges
                    n1, n2 = len(edges1), len(edges2)
                    n_max = max(n1, n2)

                    print(f"n1 = {n1}, n2 = {n2}, edges1 = {[e.length for e in edges1]}, edges2 = {[e.length for e in edges2]}")

                    # Штрафуем за «лишние» рёбра
                    coeff -= (n_max - min(n1, n2)) / n_max * EDGE_PENALTY
                    if n1 != n2:
                        print(f"Несоответствие по количеству!!!")

                    min_edges, max_edges = (edges1, edges2) if n1 <= n2 else (edges2, edges1)
                    used = set()
                    matched_edges: List[Tuple[Edge, Edge]] = []

                    for e1 in min_edges:
                        found = False
                        for e2 in max_edges:
                            if e2.new_index in used:
                                continue
                            print(f"{abs(e1.length - e2.length)} {scene.edge_threshold} {math_utils.compare_values(e1.length, e2.length, scene.edge_threshold)}")
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
                            print(f"Несоответствие по длине!!! e1 = {e1.length}")

                    print(f"Обработка мэша {m1.name}. Грань {f1.new_index}. Нормаль...")
                    # Сравниваем нормали
                    normals_ok = False
                    if len(matched_edges) > 2:
                        if compare_normals(f1, f2, matched_edges):
                            normals_ok = True
                        else:
                            coeff -= NORMAL_PENALTY
                            print(f"Несоответствие нормали!!!")

                    if normals_ok and coeff < MIN_MATCH_COEFF:
                        coeff = MIN_MATCH_COEFF

                    # Добавляем совпадение
                    if coeff >= MIN_MATCH_COEFF:
                        graph.add_match(GraphMatch(
                            m1.name, m2.name,
                            MatchType.FACE,
                            (f1.new_index, f2.new_index),
                            coeff
                        ))

    print("Поиск совпадений по рёбрам...")
    for i, m1 in enumerate(meshes):
        for m2 in meshes[i+1:]:
            # Исключаем ребра, принадлежащие совпавшим граням
            matched_faces = {idx for match in graph.adj.get(m1.name, {}).get(m2.name, []) if match.match_type==MatchType.FACE for idx in [match.indices[0]]}
            edges1 = [e for f in m1.faces if f.new_index not in matched_faces for e in f.edges]
            edges2 = [e for f in m2.faces if f.new_index not in matched_faces for e in f.edges]
            for e1 in edges1:
                for e2 in edges2:
                    max_length = max(e1.length, e2.length)
                    coeff = 1 - abs(e1.length / max_length - e2.length / max_length)

                    if coeff >= MIN_MATCH_COEFF:
                        graph.add_match(GraphMatch(m1.name, m2.name, MatchType.EDGE, (e1.new_index, e2.new_index), coeff))

    return graph


if __name__ == '__main__':
    meshes = JsonMeshReader.read()
    graph = build_mesh_graph(meshes)
    Writer.print_graph(graph)

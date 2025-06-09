import math
from typing import List, Tuple
from geometry_connector import math_utils
from geometry_connector.enums import MatchType
from geometry_connector.models import GraphMatch, Face, Edge, Mesh, MeshGraph
from geometry_connector.constants import AREA_PENALTY, EDGE_PENALTY, NORMAL_PENALTY, MIN_MATCH_FACE_COEFF, MIN_MATCH_EDGE_COEFF
from mathutils import Vector, Matrix
import bpy


class GeometryConnector:
    def __init__(self):
        scene = bpy.context.scene

        self.connected_edge_angle_threshold = scene.connected_edge_angle_threshold
        self.area_threshold = scene.face_area_threshold
        self.edge_length_threshold = scene.edge_length_threshold

    # Построение графа совпадений обломков
    def build_mesh_graph(self, pieces_meshes: List[Mesh]) -> MeshGraph:
        pieces_graph = MeshGraph()

        # region Поиск совпадений по граням

        for i, mesh1 in enumerate(pieces_meshes):
            for mesh2 in pieces_meshes[i + 1:]:
                for face1 in mesh1.faces:
                    edges1 = face1.edges
                    edge_count1 = len(edges1)

                    for face2 in mesh2.faces:
                        coeff = 1.0

                        # Сравнение площадей
                        if not math_utils.compare_values(face1.area, face2.area, self.area_threshold):
                            coeff -= AREA_PENALTY

                        # Подготовка рёбер
                        edges2 = face2.edges
                        edge_count2 = len(edges2)
                        max_count = max(edge_count1, edge_count2)

                        if edge_count1 != edge_count2:
                            coeff -= (max_count - min(edge_count1, edge_count2)) / max_count * EDGE_PENALTY

                        min_edges = edges1 if edge_count1 <= edge_count2 else edges2
                        max_edges = edges2 if edge_count1 <= edge_count2 else edges1

                        # Сопоставление рёбер
                        matched_edges = []
                        used = set()

                        for edge1 in min_edges:
                            found = False
                            for edge2 in max_edges:
                                if edge2.new_index in used:
                                    continue
                                if math_utils.compare_values(edge1.length, edge2.length, self.edge_length_threshold):
                                    used.add(edge2.new_index)
                                    if edge_count1 <= edge_count2:
                                        matched_edges.append((edge1, edge2))
                                    else:
                                        matched_edges.append((edge2, edge1))
                                    found = True
                                    break
                            if not found:
                                coeff -= EDGE_PENALTY / max_count

                        # Сравнение нормалей, если есть достаточно рёбер
                        if len(matched_edges) > 2:
                            ok = self._compare_normals(face1, face2, matched_edges)

                            if not ok:
                                coeff -= NORMAL_PENALTY
                            elif coeff < MIN_MATCH_FACE_COEFF:
                                coeff = MIN_MATCH_FACE_COEFF

                        # Добавляем совпадение, если коэффициент удовлетворён
                        if coeff >= MIN_MATCH_FACE_COEFF:
                            pieces_graph.add_match(GraphMatch(
                                mesh1=mesh1.name,
                                mesh2=mesh2.name,
                                match_type=MatchType.FACE,
                                indices=(face1.new_index, face2.new_index),
                                coeff=coeff,
                                edges=matched_edges
                            ))

        # endregion

        # region Поиск совпадений по рёбрам

        # for i, mesh1 in enumerate(pieces_meshes):
        #     for mesh2 in pieces_meshes[i + 1:]:
        #         min_coeff = MIN_MATCH_EDGE_COEFF
        #         # Не рассматриваем соединения, у которых уже совпали грани
        #         existing = pieces_graph.connections.get(mesh1.name, {}).get(mesh2.name, [])
        #         if len(existing) > 0:
        #             continue
        #
        #         m1_used_edges = list({edge.new_index for matches in pieces_graph.connections.get(mesh1.name, {}).values()
        #                                for match in matches if match.match_type == MatchType.FACE
        #                                for edge, _ in match.edges})
        #
        #         m2_used_edges = list({edge.new_index for matches in pieces_graph.connections.get(mesh2.name, {}).values()
        #                            for match in matches if match.match_type == MatchType.FACE
        #                            for edge, _ in match.edges})
        #
        #         edges1 = [edge for edge in mesh1.edges if edge.new_index not in m1_used_edges]
        #         edges2 = [edge for edge in mesh2.edges if edge.new_index not in m2_used_edges]
        #
        #         for edge1 in edges1:
        #             for edge2 in edges2:
        #                 max_len = max(edge1.length, edge2.length)
        #                 coeff = 1 - abs(edge1.length / max_len - edge2.length / max_len)
        #                 if coeff >= min_coeff:
        #                     pieces_graph.add_match(GraphMatch(
        #                         mesh1=mesh1.name,
        #                         mesh2=mesh2.name,
        #                         match_type=MatchType.EDGE,
        #                         indices=(edge1.new_index, edge2.new_index),
        #                         coeff=coeff
        #                     ))
        #                     min_coeff = coeff

        # endregion

        return pieces_graph


    # Сравнение нормалей граней с учётом выравнивания совпавших рёбер
    def _compare_normals(self, f1: Face, f2: Face, matching_edges: List[Tuple[Edge, Edge]]) -> bool:
        # Косинус порогового угла
        cos_th = math.cos(self.connected_edge_angle_threshold)

        # Собираем направляющие векторы по рёбрам
        v1_list: List[Vector] = []
        v2_list: List[Vector] = []
        for edge1, edge2 in matching_edges:
            p1a, p1b = map(Vector, edge1.vertices)
            p2a, p2b = map(Vector, edge2.vertices)
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
        r = M1 @ M2_inv

        # Проверяем все остальные рёбра через скалярное произведение
        for v1_i, raw_v2_i in zip(v1_list, v2_list):
            sign_i = 1.0 if v1_i.dot(raw_v2_i) >= 0.0 else -1.0
            v2o = (raw_v2_i * sign_i).normalized()
            v2_rot = r @ v2o
            if v1_i.dot(v2_rot) < cos_th:
                return False

        # Финальная проверка нормалей граней
        n2_rot = r @ n2
        if n2_rot.dot(-n1) > cos_th:
            return True

        return False
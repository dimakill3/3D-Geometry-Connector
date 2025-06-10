import math
import bpy
from typing import Dict, Counter, Set
from geometry_connector.constants import MAX_DISTANCE_BETWEEN_MESHES, NORMAL_ANGLE_THRESHOLD
from geometry_connector.enums import MatchType
from geometry_connector.models import Network, Mesh, MeshGraph, GraphMatch
from mathutils import Quaternion, Vector
from mathutils import Matrix


class GeometryBuilder:
    def __init__(self):
        scene = bpy.context.scene

        self.connected_edge_angle_threshold = scene.connected_edge_angle_threshold
        self.area_threshold = scene.face_area_threshold
        self.edge_length_threshold = scene.edge_length_threshold

    def assemble_network(self, network: Network, meshes: Dict[str, Mesh], graph: MeshGraph) -> Dict[str, Matrix]:
        # Кэшируем все исходные мировые матрицы
        mat_worlds: Dict[str, Matrix] = {name: mesh.matrix_world.copy() for name, mesh in meshes.items()}

        base = network.matches[0].mesh1

        for match in network.matches:
            src, dst = match.mesh2, match.mesh1
            self._find_connection_matrix(match, meshes[src], meshes[dst], mat_worlds[src], mat_worlds[dst])

            new_world = self._find_connection_matrix(match, meshes[src], meshes[dst], mat_worlds[src], mat_worlds[dst])

            # Сохраняем результат
            mat_worlds[src] = new_world

        # Проверка ориентации: флипаем меши с некорректными нормалями
        self._flip_incorrect_orientations(network, graph, meshes, mat_worlds, base)
        # Пост-обработка: корректировка трансформаций
        self._correct_transformations(network, meshes, mat_worlds, MAX_DISTANCE_BETWEEN_MESHES)

        return mat_worlds


    def apply_transforms_to_scene(self, transforms: Dict[str, Matrix]):
        for mesh_name in transforms:
            obj = bpy.data.objects.get(mesh_name)
            if obj:
                obj.matrix_world = transforms[mesh_name]


    def _flip_incorrect_orientations(self, network : Network, graph: MeshGraph, meshes: Dict[str, Mesh], mat_worlds: Dict[str, Matrix], base_mesh: str):
        print("[flip_orientations] Начало проверки ориентаций")

        cos_th = math.cos(NORMAL_ANGLE_THRESHOLD)

        flipped_meshes: Set[str] = set()
        flipped_meshes.add(base_mesh)

        while True:
            meshes_to_flip = []
            added_matches = []

            for net in network.matches[1:]:
                name = net.mesh2
                print(f"[flip_orientations] Проверяем меш '{name}'")
                for neighbor_name, gm_list in graph.connections.get(name, {}).items():
                    print(f"[flip_orientations]  Найден сосед '{neighbor_name}' с {len(gm_list)} связями")
                    for gm in gm_list:
                        if gm in added_matches or gm.inverted in added_matches:
                            continue

                        print(
                            f"[flip_orientations]   Используемый GraphMatch: {gm.mesh1} -> {gm.mesh2}, indices: {gm.indices[0]} {gm.indices[1]}")
                        is_src = (name == gm.mesh2)
                        idx_local, idx_other = (gm.indices[1], gm.indices[0]) if is_src else (gm.indices[0],
                                                                                              gm.indices[1])
                        fe_local = meshes[name].faces[idx_local] if gm.match_type == MatchType.FACE else \
                        meshes[name].edges[idx_local]
                        fe_other = meshes[neighbor_name].faces[idx_other] if gm.match_type == MatchType.FACE else \
                        meshes[neighbor_name].edges[idx_other]
                        n_local = (mat_worlds[name].to_3x3() @ fe_local.normal).normalized()
                        n_other = (mat_worlds[neighbor_name].to_3x3() @ fe_other.normal).normalized()
                        print(
                            f"[flip_orientations]    Нормаль локальная: {n_local}, нормаль соседа: {-n_other}, dot = {n_local.dot(-n_other)}, thr = {cos_th}")
                        if n_local.dot(-n_other) < cos_th:
                            print(f"[flip_orientations]    Нормали не противоположны, заносим {name} и {neighbor_name}")
                            meshes_to_flip.append(name)
                            meshes_to_flip.append(neighbor_name)
                            added_matches.append(gm)
                            break
                        else:
                            print(
                                f"[flip_orientations]  Для меша '{name}' нет используемых соединений, требующих флипа")
                            continue

            print(f"[flip_orientations]!!!!!!!!!Проход закончен, список для флипа {meshes_to_flip}")

            counter = Counter(meshes_to_flip)
            if counter:
                found = False
                for most_common_element, count in counter.most_common():
                    if most_common_element in flipped_meshes or count < 2:
                        continue
                    else:
                        found = True
                        break
                if not found:
                    break
            else:
                break

            print(f"[flip_orientations]!!!!!!!!!Самый частый элемент {most_common_element}, поворачиваем его")

            match = [m for m in network.matches if m.mesh2 == most_common_element][0]

            fe_local = meshes[most_common_element].faces[
                match.indices[1]] if match.match_type == MatchType.FACE else meshes[most_common_element].edges[
                match.indices[1]]
            n_local = (mat_worlds[most_common_element].to_3x3() @ fe_local.normal).normalized()
            center = sum((mat_worlds[most_common_element] @ Vector(v) for v in fe_local.vertices), Vector()) / len(
                fe_local.vertices)
            q_flip = Quaternion(n_local, math.pi)
            mat_flip = (Matrix.Translation(center) @
                        q_flip.to_matrix().to_4x4() @
                        Matrix.Translation(-center))
            mat_worlds[most_common_element] = mat_flip @ mat_worlds[most_common_element]


            flipped_meshes.add(most_common_element)
            print(f"[flip_orientations]!!!!!!!!!Меш '{most_common_element}' флипанут на 180° вокруг нормали {n_local}")

            for match in [m for m in network.matches if m.mesh1 == most_common_element]:
                mat_worlds[match.mesh2] = self._find_connection_matrix(match, meshes[match.mesh2], meshes[match.mesh1], mat_worlds[match.mesh2], mat_worlds[match.mesh1])


        print("[flip_orientations] Завершение проверки ориентаций")


    def _find_connection_matrix(self, match: GraphMatch, src_mesh: Mesh, dst_mesh: Mesh, src_mesh_world: Matrix, dst_mesh_world: Matrix) -> Matrix:
        idx_src, idx_dst = match.indices[1], match.indices[0]
        edges = [(e2, e1) for e1, e2 in match.edges]

        # Вспомогательная функция для центроидов и направлений
        def get_cd(fe, M: Matrix):
            pts = [M @ Vector(v) for v in fe.vertices]
            ctr = sum(pts, Vector()) / len(pts)
            if hasattr(fe, 'normal'):
                nr = (M.to_3x3() @ fe.normal).normalized()
                return ctr, nr
            return ctr, (pts[1] - pts[0]).normalized()

        # Выбираем Face или Edge
        if match.match_type == MatchType.FACE:
            fe_s = src_mesh.faces[idx_src]
            fe_d = dst_mesh.faces[idx_dst]
        else:
            fe_s = src_mesh.edges[idx_src]
            fe_d = dst_mesh.edges[idx_dst]

        c_src, dir_src = get_cd(fe_s, src_mesh_world)
        c_dst, dir_dst = get_cd(fe_d, dst_mesh_world)

        # Вычисляем кватернион
        if match.match_type == MatchType.FACE:
            q1 = dir_src.rotation_difference(-dir_dst)
            if edges:
                e1, e2 = edges[0]
                p1 = [src_mesh_world @ Vector(v) for v in e1.vertices]
                v1 = (q1 @ (p1[1] - p1[0]).normalized()).normalized()
                p2 = [dst_mesh_world @ Vector(v) for v in e2.vertices]
                v2 = (p2[1] - p2[0]).normalized()
                axis = -dir_dst
                angle = v1.angle(v2)
                sign = 1 if axis.dot(v1.cross(v2)) > 0 else -1
                q = Quaternion(axis, sign * angle) @ q1
            else:
                q = q1
        else:
            q = dir_src.rotation_difference(dir_dst)

        # Строим матрицы трансформации
        mat_rot = q.to_matrix().to_4x4()
        mat_trans = Matrix.Translation(c_dst - (q @ c_src))

        return mat_trans @ mat_rot @ src_mesh_world


    def _correct_transformations(self, network: Network, meshes: Dict[str, Mesh], mat_worlds: Dict[str, Matrix], max_sep: float):
        for match in network.matches:
            src, dst = match.mesh2, match.mesh1
            idx_src, idx_dst = match.indices[1], match.indices[0]
            M_src = mat_worlds[src]
            M_dst = mat_worlds[dst]

            # Сбор соответствующих точек
            if match.match_type == MatchType.FACE:
                fe_s = meshes[src].faces[idx_src]
                fe_d = meshes[dst].faces[idx_dst]
            else:
                fe_s = meshes[src].edges[idx_src]
                fe_d = meshes[dst].edges[idx_dst]

            pts_s = [M_src @ Vector(v) for v in fe_s.vertices]
            pts_d = [M_dst @ Vector(v) for v in fe_d.vertices]

            # Вычисляем среднее расстояние
            seps = [(ps - pd).length for ps, pd in zip(pts_s, pts_d)]
            avg_sep = sum(seps) / len(seps)
            if avg_sep > max_sep:
                ctr_s = sum(pts_s, Vector()) / len(pts_s)
                ctr_d = sum(pts_d, Vector()) / len(pts_d)
                shift = ctr_d - ctr_s
                corr = Matrix.Translation(shift)
                mat_worlds[src] = corr @ mat_worlds[src]
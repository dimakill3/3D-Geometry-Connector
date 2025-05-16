from typing import Dict, List, Tuple
from geometry_connector.enums import MatchType
from geometry_connector.models import Network, Mesh, TransformMatch, Face, Edge
from mathutils import Quaternion, Vector
import bpy
from mathutils import Matrix


def assemble_network(network: Network, meshes: Dict[str, Mesh]) -> List[TransformMatch]:
    transforms: List[TransformMatch] = []
    placed: Dict[str, Tuple[Quaternion, Vector]] = {}

    # первая точка — без трансформации
    first = network.matches[0]
    placed[first.mesh1] = (Quaternion(), Vector((0, 0, 0)))

    for match in network.matches:
        # ищем «непомещённый» меш
        if match.mesh1 in placed and match.mesh2 not in placed:
            src, dst = match.mesh2, match.mesh1
            idx_src, idx_dst = match.indices[1], match.indices[0]
        elif match.mesh2 in placed and match.mesh1 not in placed:
            src, dst = match.mesh1, match.mesh2
            idx_src, idx_dst = match.indices[0], match.indices[1]
        else:
            continue

        # получаем объекты Face или Edge
        if match.match_type == MatchType.FACE:
            fe_src = meshes[src].faces[idx_src]
            fe_dst = meshes[dst].faces[idx_dst]
        else:
            fe_src = meshes[src].edges[idx_src]
            fe_dst = meshes[dst].edges[idx_dst]

        # рассчитываем центр и «направление» (нормаль или вектор ребра) в мировых координатах
        def centroid_and_dir(fe, world_m: Matrix):
            pts = [world_m @ Vector(v) for v in fe.vertices]
            center = sum(pts, Vector()) / len(pts)
            if match.match_type == MatchType.FACE:
                # мировая нормаль
                normal = (world_m.to_3x3() @ fe.normal).normalized()
                return center, normal
            else:
                # направление ребра
                return center, (pts[1] - pts[0]).normalized()

        c_src, dir_src = centroid_and_dir(fe_src, meshes[src].matrix_world)
        c_dst, dir_dst = centroid_and_dir(fe_dst, meshes[dst].matrix_world)

        # построим кватернион поворота
        if match.match_type == MatchType.FACE:
            # хотим n_src → –n_dst
            q1 = dir_src.rotation_difference(-dir_dst)

            # берем заранее найденные в GraphMatch пары рёбер
            matched_edges = match.edges

            if matched_edges:
                # уточняем ориентацию вокруг нормали
                e1, e2 = matched_edges[0]
                # мировой вектор ребра после q1
                p1 = [meshes[src].matrix_world @ Vector(v) for v in e1.vertices]
                v1 = (p1[1] - p1[0]).normalized()
                v1 = (q1 @ v1).normalized()
                # мировой вектор цели
                p2 = [meshes[dst].matrix_world @ Vector(v) for v in e2.vertices]
                v2 = (p2[1] - p2[0]).normalized()
                # вращаем вокруг –dir_dst
                axis = -dir_dst
                angle = v1.angle(v2)
                sign = 1 if axis.dot(v1.cross(v2)) > 0 else -1
                q2 = Quaternion(axis, sign * angle)
                q = q2 @ q1
            else:
                q = q1
        else:
            # для ребра — обычное выравнивание
            q = dir_src.rotation_difference(dir_dst)

        # смещение так, чтобы центр src лег в центр dst
        t = c_dst - (q @ c_src)

        # комбинируем с уже поставленным dst
        q_base, t_base = placed[dst]
        q_net = q_base @ q
        t_net = q_base @ t + t_base

        # сохраняем и сразу применяем в локальной копии
        placed[src] = (q_net, t_net)
        meshes[src].matrix_world = Matrix.Translation(t_net) @ q_net.to_matrix().to_4x4()
        transforms.append(TransformMatch(match=match, rotation=q_net, translation=t_net))

    return transforms


def apply_transforms_to_scene(transforms, base_mesh_name: str):
    for tm in transforms:
        # Определяем, к какому мешу относится текущая трансформация
        if tm.match.mesh1 == base_mesh_name:
            obj_name = tm.match.mesh2
        else:
            obj_name = tm.match.mesh1

        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            print(f"Object '{obj_name}' not found in the scene.")
            continue

        # Строим матрицу трансформации: сначала поворот, затем перенос
        mat_rot = tm.rotation.to_matrix().to_4x4()
        mat_trans = Matrix.Translation(tm.translation)
        transform_mat = mat_trans @ mat_rot

        # Применяем в мировых координатах
        obj.matrix_world = transform_mat

    print("Transforms applied.")

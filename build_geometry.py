from typing import Dict, List, Tuple
from geometry_connector.models import Network, Mesh, TransformMatch, Face, Edge
from mathutils import Quaternion, Vector
import bpy
from mathutils import Matrix


def assemble_network(network: Network, meshes: Dict[str, Mesh]) -> List[TransformMatch]:
    transforms: List[TransformMatch] = []
    # Сохраняем текущие трансформы для мешей
    placed: Dict[str, Tuple[Quaternion, Vector]] = {}

    # Берём первый меш как базовый: без трансформации
    first_match = network.matches[0]
    base_mesh = first_match.mesh1
    placed[base_mesh] = (Quaternion(), Vector((0, 0, 0)))

    # Для каждого совпадения в сети
    for match in network.matches:
        # Определяем, какая из пар уже расположена
        if match.mesh1 in placed and match.mesh2 not in placed:
            src, dst = match.mesh2, match.mesh1
            idx_src, idx_dst = match.indices[1], match.indices[0]
        elif match.mesh2 in placed and match.mesh1 not in placed:
            src, dst = match.mesh1, match.mesh2
            idx_src, idx_dst = match.indices[0], match.indices[1]
        else:
            # либо оба уже размещены, либо ни один — пропускаем
            continue

        # Получаем геометрию граней/рёбер
        face_or_edge_src = meshes[src].faces[idx_src]
        face_or_edge_dst = meshes[dst].faces[idx_dst]

        # Вычисляем центры и нормали граней (или направл. вектора ребра)
        def centroid_and_dir(fe: Face or Edge):
            verts = fe.vertices
            pts = [Vector(v) for v in verts]
            center = sum(pts, Vector()) / len(pts)
            if isinstance(fe, Face):
                direction = fe.normal.normalized()
            else:
                direction = (pts[1] - pts[0]).normalized()
            return center, direction

        c_src, dir_src = centroid_and_dir(face_or_edge_src)
        c_dst, dir_dst = centroid_and_dir(face_or_edge_dst)

        # Находим кватернион поворота, выравнивающий src → dst
        q = dir_src.rotation_difference(dir_dst)

        # Вычисляем перемещение: после поворота центр src должен лечь в центр dst
        t = c_dst - (q @ c_src)

        # Учитываем уже применённые трансформы к dst (или src)
        q_base, t_base = placed[dst]
        q_net = q_base @ q
        t_net = q_base @ t + t_base

        # Сохраняем трансформ для src
        placed[src] = (q_net, t_net)
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

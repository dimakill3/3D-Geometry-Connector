import bpy
from typing import Dict, List
from geometry_connector.enums import MatchType
from geometry_connector.models import Network, Mesh, TransformMatch
from mathutils import Quaternion, Vector
from mathutils import Matrix


def assemble_network(network: Network, meshes: Dict[str, Mesh]) -> List[TransformMatch]:
    # Кэшируем все исходные матрицы
    mat_worlds: Dict[str, Matrix] = {
        name: mesh.matrix_world.copy() for name, mesh in meshes.items()
    }

    placed = set()
    transforms: List[TransformMatch] = []

    # Базовый меш — первый в первой паре
    base = network.matches[0].mesh1
    placed.add(base)
    # Добавляем трансформ для базового меша
    transforms.append(TransformMatch(mesh_name=base, matrix_world=mat_worlds[base]))

    changed = True
    while changed:
        changed = False
        for m in network.matches:
            m1, m2 = m.mesh1, m.mesh2
            # Пропускаем, если оба уже в placed
            if m1 in placed and m2 in placed:
                continue

            # Определяем, что src, а что dst
            if m1 in placed and m2 not in placed:
                src, dst = m2, m1
                idx_src, idx_dst = m.indices[1], m.indices[0]
                edges = [(e2, e1) for e1, e2 in m.edges]
            elif m2 in placed and m1 not in placed:
                src, dst = m1, m2
                idx_src, idx_dst = m.indices[0], m.indices[1]
                edges = m.edges
            else:
                continue

            # Готовимся расчитать новую матрицу для src
            M_src = mat_worlds[src]
            M_dst = mat_worlds[dst]

            # Получаем центроиды и направления
            def get_cd(fe, M):
                pts = [M @ Vector(v) for v in fe.vertices]
                ctr = sum(pts, Vector()) / len(pts)
                # Если грань — нормаль, иначе вектор по ребру
                if hasattr(fe, 'normal'):
                    nr = (M.to_3x3() @ fe.normal).normalized()
                    return ctr, nr
                return ctr, (pts[1] - pts[0]).normalized()

            # Выбираем Face или Edge из матча
            if m.match_type == MatchType.FACE:
                fe_s = meshes[src].faces[idx_src]
                fe_d = meshes[dst].faces[idx_dst]
            else:
                fe_s = meshes[src].edges[idx_src]
                fe_d = meshes[dst].edges[idx_dst]

            c_src, dir_src = get_cd(fe_s, M_src)
            c_dst, dir_dst = get_cd(fe_d, M_dst)

            # Вычисляем поворот q так же, как раньше
            if m.match_type == MatchType.FACE:
                q1 = dir_src.rotation_difference(-dir_dst)
                if edges:
                    e1, e2 = edges[0]
                    p1 = [M_src @ Vector(v) for v in e1.vertices]
                    v1 = (q1 @ (p1[1] - p1[0]).normalized()).normalized()
                    p2 = [M_dst @ Vector(v) for v in e2.vertices]
                    v2 = (p2[1] - p2[0]).normalized()
                    axis = -dir_dst
                    angle = v1.angle(v2)
                    sign = 1 if axis.dot(v1.cross(v2)) > 0 else -1
                    q = Quaternion(axis, sign * angle) @ q1
                else:
                    q = q1
            else:
                q = dir_src.rotation_difference(dir_dst)

            # Считаем абсолютную новую матрицу
            mat_rot   = q.to_matrix().to_4x4()
            mat_trans = Matrix.Translation(c_dst - (q @ c_src))
            new_world = mat_trans @ mat_rot @ M_src

            # Сохраняем и помечаем, что добавили
            mat_worlds[src] = new_world
            transforms.append(TransformMatch(mesh_name=src, matrix_world=new_world))
            placed.add(src)
            changed = True

    return transforms


def apply_transforms_to_scene(transforms: List[TransformMatch]):
    for tm in transforms:
        obj = bpy.data.objects.get(tm.mesh_name)
        if obj:
            obj.matrix_world = tm.matrix_world

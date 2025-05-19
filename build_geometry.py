from typing import Dict, List

from geometry_connector.enums import MatchType
from geometry_connector.models import Network, Mesh, TransformMatch, GraphMatch
from mathutils import Quaternion, Vector
import bpy
from mathutils import Matrix


def assemble_network(network: Network, meshes: Dict[str, Mesh]) -> List[TransformMatch]:
    matches = network.matches
    # Кэшируем все исходные матрицы
    mat_worlds = {name: mesh.matrix_world.copy() for name, mesh in meshes.items()}
    placed = set()
    transforms: List[TransformMatch] = []

    # Базовый меш — первый в первой паре
    base = matches[0].mesh1
    placed.add(base)

    # Повторяем, пока есть что разместить
    changed = True
    while changed:
        changed = False
        for m in matches:
            m1, m2 = m.mesh1, m.mesh2
            # Пропускаем, если оба уже размещены
            if m1 in placed and m2 in placed:
                continue

            # Ппределяем src/dst и индексы
            if m1 in placed:
                src, dst = m2, m1
                i_src, i_dst = m.indices[1], m.indices[0]
                edges = [(e2, e1) for (e1, e2) in m.edges]
            elif m2 in placed:
                src, dst = m1, m2
                i_src, i_dst = m.indices
                edges = m.edges
            else:
                continue

            changed = True

            # Вытаскиваем необходимые объекты и матрицы
            M_src, M_dst = mat_worlds[src], mat_worlds[dst]
            mesh_src, mesh_dst = meshes[src], meshes[dst]

            # Выбор Face или Edge
            if m.match_type == MatchType.FACE:
                fe_s = mesh_src.faces[i_src]
                fe_d = mesh_dst.faces[i_dst]
            else:
                fe_s = mesh_src.edges[i_src]
                fe_d = mesh_dst.edges[i_dst]

            # Вспомогательная функция для получения центроида и направления
            def get_cd(fe, M):
                pts = [M @ Vector(v) for v in fe.vertices]
                ctr = sum(pts, Vector()) / len(pts)
                if hasattr(fe, 'normal'):
                    nr = (M.to_3x3() @ fe.normal).normalized()
                    return ctr, nr
                return ctr, (pts[1] - pts[0]).normalized()

            c_src, dir_src = get_cd(fe_s, M_src)
            c_dst, dir_dst = get_cd(fe_d, M_dst)

            # Расчёт вращения
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

            # Перемещение
            t = c_dst - (q @ c_src)

            # Новая world-матрица
            mat_worlds[src] = Matrix.Translation(t) @ q.to_matrix().to_4x4() @ M_src

            # Инвертируем GraphMatch, чтобы трансформ всегда применялся для второго мэша в паре
            inv = GraphMatch(
                mesh1=dst,
                mesh2=src,
                match_type=m.match_type,
                indices=(i_dst, i_src),
                coeff=m.coeff,
                edges=edges
            )
            transforms.append(TransformMatch(match=inv, rotation=q, translation=t))
            placed.add(src)

    return transforms


def apply_transforms_to_scene(transforms):
    for tm in transforms:
        # Трансформируем всегда mesh2
        obj = bpy.data.objects.get(tm.match.mesh2)
        if obj is None:
            continue

        # Применяем в мировых координатах
        mat_rot = tm.rotation.to_matrix().to_4x4()
        mat_trans = Matrix.Translation(tm.translation)
        obj.matrix_world = mat_trans @ mat_rot @ obj.matrix_world

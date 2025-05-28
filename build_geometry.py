import math
import bpy
from typing import Dict, List, Set
from geometry_connector.enums import MatchType
from geometry_connector.models import Network, Mesh, TransformMatch, MeshGraph, GraphMatch
from mathutils import Quaternion, Vector
from mathutils import Matrix


def assemble_network(network: Network, meshes: Dict[str, Mesh], graph: MeshGraph) -> List[TransformMatch]:
    print("[assemble_network] Старт сети")
    print(f"[assemble_network] Mesh Cube_cell.023 присутствует в meshes? {'Cube_cell.023' in meshes}")

    # Кэшируем все исходные мировые матрицы
    mat_worlds: Dict[str, Matrix] = {name: mesh.matrix_world.copy() for name, mesh in meshes.items()}

    placed: Set[str] = set()
    transforms: List[TransformMatch] = []

    # Базовый меш — самый большой
    base = max(meshes.values(), key=lambda mesh: mesh.volume).name
    placed.add(base)
    transforms.append(
        TransformMatch(src_mesh_name=base, dst_mesh_name=base, matrix_world=mat_worlds[base])
    )
    print(f"[assemble_network] Базовый меш: {base}")

    changed = True
    while changed:
        changed = False
        for m in network.matches:
            m1, m2 = m.mesh1, m.mesh2
            # Пропускаем, если оба уже размещены
            if m1 in placed and m2 in placed:
                continue

            # Определяем src и dst
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

            # Лог, если задействован интересующий меш
            if 'Cube_cell.023' in (src, dst):
                print(f"[assemble_network] Обработка Cube_cell.023 в соединении {src} -> {dst}")

            # Получаем текущие мировые матрицы
            M_src = mat_worlds[src]
            M_dst = mat_worlds[dst]

            # Вспомогательная функция для центроидов и направлений
            def get_cd(fe, M: Matrix):
                pts = [M @ Vector(v) for v in fe.vertices]
                ctr = sum(pts, Vector()) / len(pts)
                if hasattr(fe, 'normal'):
                    nr = (M.to_3x3() @ fe.normal).normalized()
                    return ctr, nr
                return ctr, (pts[1] - pts[0]).normalized()

            # Выбираем Face или Edge
            if m.match_type == MatchType.FACE:
                fe_s = meshes[src].faces[idx_src]
                fe_d = meshes[dst].faces[idx_dst]
            else:
                fe_s = meshes[src].edges[idx_src]
                fe_d = meshes[dst].edges[idx_dst]

            c_src, dir_src = get_cd(fe_s, M_src)
            c_dst, dir_dst = get_cd(fe_d, M_dst)
            print(f"[assemble_network] c_src={c_src}, dir_src={dir_src}, c_dst={c_dst}, dir_dst={dir_dst}")

            # Вычисляем кватернион
            if m.match_type == MatchType.FACE:
                print(f"[assemble_network] Расчёт FACE-вращения для {src}")
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
                print(f"[assemble_network] Расчёт EDGE-вращения для {src}")
                q = dir_src.rotation_difference(dir_dst)
            print(f"[assemble_network] Кватернион поворота: {q}")

            # Строим матрицы трансформации
            mat_rot = q.to_matrix().to_4x4()
            mat_trans = Matrix.Translation(c_dst - (q @ c_src))
            new_world = mat_trans @ mat_rot @ M_src

            # Сохраняем результат
            mat_worlds[src] = new_world
            transforms.append(
                TransformMatch(src_mesh_name=src, dst_mesh_name=dst, matrix_world=new_world)
            )
            print(f"[assemble_network] Transform для {src}:\n{new_world}")

            placed.add(src)
            changed = True

    # Постобработка ориентации листьев
    # postprocess_leaf_orientation(network, meshes, graph, transforms)
    print("[assemble_network] Завершение сети")
    return transforms


def apply_transforms_to_scene(transforms: List[TransformMatch]):
    for tm in transforms:
        obj = bpy.data.objects.get(tm.src_mesh_name)
        if obj:
            obj.matrix_world = tm.matrix_world


def postprocess_leaf_orientation(network, meshes: dict[str, Mesh], graph, transforms: list[TransformMatch]) -> List[TransformMatch]:
    used = {}
    for m in network.matches:
        used.setdefault(m.mesh1, []).append(m)
        used.setdefault(m.mesh2, []).append(m)

    leaves = [name for name, conns in used.items() if len(conns) == 1 and name != network.matches[0].mesh1]

    print(leaves)

    # Подготовить словарь мировых матриц
    mat_world = {tm.src_mesh_name: tm.matrix_world.copy() for tm in transforms}

    for leaf in leaves:
        # единственное соединение из сети
        conn = used[leaf][0]
        neighbor = conn.mesh1 if conn.mesh2 == leaf else conn.mesh2
        # все FACE-соединения в графе между leaf и neighbor
        candidates: list[GraphMatch] = [gm for gm in graph.connections.get(leaf, {}).get(neighbor, [])
                                        if gm.match_type == MatchType.FACE]
        # отфильтровать те, что уже в network
        used_idxs = {conn.indices if conn.mesh1 == leaf else (conn.indices[1], conn.indices[0])}
        not_used = [gm for gm in candidates if gm.indices not in used_idxs]

        # Проверка каждого неиспользованного FACE
        for gm in not_used:
            # получить мировые матрицы
            M1 = mat_world[gm.mesh1]
            M2 = mat_world[gm.mesh2]
            # взять вершины граней
            mesh1 = meshes[gm.mesh1]
            mesh2 = meshes[gm.mesh2]
            f1 = mesh1.faces[gm.indices[0]]
            f2 = mesh2.faces[gm.indices[1]]

            # нормали в world
            n1 = (M1.to_3x3() @ f1.normal).normalized()
            n2 = (M2.to_3x3() @ f2.normal).normalized()
            # проверяем противоположность
            if abs(n1.dot(n2) + 1) > 1e-3:
                needs_flip = True
            else:
                # проверяем рёбра: сравнить world-координаты вершин каждого ребра попарно
                needs_flip = False
                # по каждому ребру печатать, если не совпадает
                for e1, e2 in gm.edges:
                    vs1 = [(M1 @ Vector(v)).to_tuple(5) for v in e1.vertices]
                    vs2 = [(M2 @ Vector(v)).to_tuple(5) for v in e2.vertices]
                    # сравнить пары либо прямой, либо в обратном порядке
                    if not (vs1 == vs2 or vs1 == vs2[::-1]):
                        needs_flip = True
                        break
            # если надо перевернуть leaf на 180° вокруг normal из conn
            if needs_flip:
                # нормаль прикрепления из сети
                fc = conn.mesh1, conn.mesh2
                f_src = meshes[conn.mesh1].faces[conn.indices[0]] if conn.mesh1 == leaf else meshes[conn.mesh2].faces[
                    conn.indices[1]]
                M_leaf = mat_world[leaf]
                n_leaf = (M_leaf.to_3x3() @ f_src.normal).normalized()
                q = Quaternion(n_leaf, math.pi)
                # применяем поворот вокруг центра грани
                # центр грани
                verts = [Vector(v) for v in f_src.vertices]
                c = sum((M_leaf @ v for v in verts), Vector()) / len(verts)
                # перенос в центр, поворот, обратно
                T1 = Matrix.Translation(-c)
                T2 = Matrix.Translation(c)
                mat_flip = T2 @ q.to_matrix().to_4x4() @ T1
                new_world = mat_flip @ M_leaf
                # сохраняем
                mat_world[leaf] = new_world
                # обновить в transforms
                for tm in transforms:
                    if tm.src_mesh_name == leaf:
                        tm.matrix_world = new_world
                        break
                print(f"Leaf {leaf} flipped 180° around face normal {n_leaf}")
                # после первого флипа можно прерываться
                break

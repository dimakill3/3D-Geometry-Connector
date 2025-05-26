from typing import List
import bpy
import bmesh
from mathutils import Vector
from geometry_connector.models import Mesh, Face, Edge

ORIG_INDICES = "orig_indices"
ORIG_INDEX = "orig_index"


class GeometryCalculator:
    def __init__(self):
        scene = bpy.context.scene
        self.angle_threshold = scene.coplanar_angle_threshold
        self.distance_threshold = scene.coplanar_dist_threshold
        self.curvature_threshold = scene.curvature_threshold


    def calculate(self) -> List[Mesh]:
        result_meshes: List[Mesh] = []

        for obj in bpy.data.objects:
            if obj.type != 'MESH' or not obj.visible_get():
                continue

            # region Чтение мэша

            mesh = obj.data
            bm = bmesh.new()
            bm.from_mesh(mesh)

            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()

            # endregion

            # Кэшируем переиспользуемые данные
            face_normals = [f.normal.copy() for f in bm.faces]
            face_centroids = [f.calc_center_median().copy() for f in bm.faces]

            # region Создаем словарь смежности граней, чтобы потом была возможность вернуться от аппроксимации к дефолтной модели

            neighbors = {i: [] for i in range(len(bm.faces))}
            for f_idx, f in enumerate(bm.faces):
                n1 = face_normals[f_idx]
                d1 = n1.dot(face_centroids[f_idx])
                for e in f.edges:
                    for g in e.link_faces:
                        g_idx = g.index
                        if g_idx <= f_idx:
                            continue
                        n2 = face_normals[g_idx]
                        if n1.angle(n2) < self.angle_threshold:
                            d2 = n2.dot(face_centroids[g_idx])
                            if abs(d1 - d2) < self.distance_threshold:
                                neighbors[f_idx].append(g_idx)
                                neighbors[g_idx].append(f_idx)

            # Группировка компланарных граней
            visited = set()
            coplanar_groups = []
            for start in neighbors:
                if start in visited:
                    continue
                stack = [start]
                comp = []
                while stack:
                    curr = stack.pop()
                    if curr in visited:
                        continue
                    visited.add(curr)
                    comp.append(curr)
                    for nbr in neighbors[curr]:
                        if nbr not in visited:
                            stack.append(nbr)
                coplanar_groups.append(comp)

            # endregion

            # region Аппроксимация контуров

            # Собираем только внутренние рёбра, у которых ровно две прилегающие грани и угол между ними < threshold
            internal_edges = [e for e in bm.edges
                              if len(e.link_faces) == 2
                              and e.link_faces[0].normal.angle(e.link_faces[1].normal) < self.angle_threshold]

            # Производим dissolve по этим рёбрам
            bmesh.ops.dissolve_edges(
                bm,
                edges=internal_edges,
                use_verts=True,
                use_face_split=False,
            )

            bmesh.ops.remove_doubles(
                bm,
                verts=bm.verts,
                dist=self.distance_threshold)

            # Пересчитываем нормали
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.normal_update()

            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()

            # endregion

            # region Сбор данных

            # Получаем размеры меша
            coords = [v.co for v in bm.verts]
            if coords:
                xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
                size = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
            else:
                size = [0.0, 0.0, 0.0]

            # Классификация вершин по кривизне
            convex_inds, concave_inds, flat_inds = [], [], []
            for v in bm.verts:
                normals = [f.normal for f in v.link_faces]
                if not normals:
                    continue
                avg = sum(normals, Vector()) / len(normals)
                avg.normalize()
                deviation = 1.0 - v.normal.dot(avg)
                if deviation > self.curvature_threshold:
                    convex_inds.append(v.index)
                elif deviation < -self.curvature_threshold:
                    concave_inds.append(v.index)
                else:
                    flat_inds.append(v.index)

            # Собираем данные граней и ребер
            faces_out: List[Face] = []
            group_map = {idx: grp for grp in coplanar_groups for idx in grp}
            for f in bm.faces:
                idx = f.index
                orig_group = group_map.get(idx, [idx])
                vert_coords = [[v.co.x, v.co.y, v.co.z] for v in f.verts]

                edges_list: List[Edge] = []
                linked_edges = f.edges[:]
                for e in linked_edges:
                    edge_verts = [[v.co.x, v.co.y, v.co.z] for v in e.verts]
                    edges_list.append(Edge(
                        new_index=e.index,
                        orig_indices=[e.index],
                        length=e.calc_length(),
                        vertices=edge_verts
                    ))

                # Определяем тип грани по среднему диэдральному
                dihedral_angles = [e.link_faces[0].normal.angle(e.link_faces[1].normal)
                                   for e in linked_edges if len(e.link_faces) == 2]
                avg_dihedral = sum(dihedral_angles) / len(dihedral_angles) if dihedral_angles else 0.0
                face_type = 1 if avg_dihedral > self.angle_threshold else (
                    -1 if avg_dihedral < -self.angle_threshold else 0)

                normal = (f.verts[1].co - f.verts[0].co).cross(f.verts[2].co - f.verts[0].co).normalized()

                faces_out.append(Face(
                    new_index=idx,
                    orig_indices=orig_group,
                    area=f.calc_area(),
                    face_type=face_type,
                    normal=normal,
                    edges=edges_list,
                    vertices=vert_coords
                ))

            result_meshes.append(Mesh(
                name=obj.name,
                size=size,
                convex_points=convex_inds,
                concave_points=concave_inds,
                flat_points=flat_inds,
                matrix_world=obj.matrix_world.copy(),
                faces=faces_out
            ))

            # endregion

            bm.free()
        return result_meshes

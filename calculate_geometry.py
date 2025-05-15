from typing import List
import bpy
import bmesh
from collections import deque
from mathutils import Vector
from geometry_connector.models import Mesh, Face, Edge
from geometry_connector.constants import COPLANAR_ANGLE_THRESHOLD, COPLANAR_DIST_THRESHOLD, CURVATURE_THRESHOLD

class CalculateGeometry:
    def __init__(self):
        self.angle_threshold = COPLANAR_ANGLE_THRESHOLD
        self.distance_threshold = COPLANAR_DIST_THRESHOLD
        self.curvature_threshold = CURVATURE_THRESHOLD

    def calculate(self) -> List[Mesh]:
        meshes = []

        for obj in bpy.data.objects:
            if obj.type != 'MESH' or obj.hide_get():
                continue

            # Чтение мэша
            mesh = obj.data
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            # Слои для меток
            face_int_layer = bm.faces.layers.int.new("orig_index")
            face_str_layer = bm.faces.layers.string.new("orig_indices")
            edge_int_layer = bm.edges.layers.int.new("orig_index")

            # Заполняем int-слой
            for f in bm.faces:
                f[face_int_layer] = f.index
            for e in bm.edges:
                e[edge_int_layer] = e.index

            # Группируем копланарные грани
            neighbors = {f.index: [] for f in bm.faces}
            for f in bm.faces:
                for e in f.edges:
                    for g in e.link_faces:
                        if g == f: continue
                        if f.normal.angle(g.normal) < self.angle_threshold:
                            d1 = f.normal.dot(f.calc_center_median())
                            d2 = g.normal.dot(g.calc_center_median())
                            if abs(d1 - d2) < self.distance_threshold:
                                neighbors[f.index].append(g.index)

            visited = set()
            groups = []
            for start in neighbors:
                if start in visited: continue
                queue = deque([start])
                comp = []
                while queue:
                    idx = queue.popleft()
                    if idx in visited: continue
                    visited.add(idx)
                    comp.append(idx)
                    for nbr in neighbors[idx]:
                        if nbr not in visited:
                            queue.append(nbr)
                groups.append(comp)

            # Запоминаем индексы
            for grp in groups:
                s = ",".join(str(idx) for idx in grp)
                for idx in grp:
                    bm.faces[idx][face_str_layer] = s.encode('utf-8')

            # Аппроксимация контуров
            bmesh.ops.dissolve_limit(
                bm,
                angle_limit = self.angle_threshold,
                use_dissolve_boundaries = True,
                verts = bm.verts,
                edges = bm.edges
            )
            bmesh.ops.remove_doubles(bm, verts = bm.verts, dist = self.distance_threshold)
            bm.normal_update()

            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()

            # Классификация вершин по кривизне
            convex_verts, concave_verts, flat_verts = [], [], []
            for v in bm.verts:
                norms = [f.normal for f in v.link_faces]
                if not norms: continue
                avg = sum(norms, Vector()) / len(norms)
                avg.normalize()
                d = 1.0 - v.normal.dot(avg)
                if d > self.curvature_threshold:
                    convex_verts.append(v.index)
                elif d < -self.curvature_threshold:
                    concave_verts.append(v.index)
                else:
                    flat_verts.append(v.index)

            # Размер меша
            coords = [v.co for v in bm.verts]
            if coords:
                xs, ys, zs = zip(*coords)
                size = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
            else:
                size = [0, 0, 0]

            # Собираем информацию о гранях
            faces_output = []
            for f in bm.faces:
                vert_coords = [[v.co.x, v.co.y, v.co.z] for v in f.verts]
                orig = bm.faces.layers.string["orig_indices"]
                orig_str = f[face_str_layer].decode('utf-8') if f[face_str_layer] else str(f[face_int_layer])
                orig_list = [int(i) for i in orig_str.split(',')]
                edges_info = []
                for e in f.edges:
                    orig_e = e[edge_int_layer]
                    edge_coords = [[v.co.x, v.co.y, v.co.z] for v in e.verts]
                    edges_info.append(Edge(
                        new_index = e.index,
                        orig_indices = [orig_e],
                        length = e.calc_length(),
                        vertices = edge_coords
                    ))
                dihed = [e.link_faces[0].normal.angle(e.link_faces[1].normal)
                         for e in f.edges if len(e.link_faces) == 2]
                avg = sum(dihed) / len(dihed) if dihed else 0
                face_type = 1 if avg > self.angle_threshold else (-1 if avg < -self.angle_threshold else 0)
                faces_output.append(Face(
                    new_index = f.index,
                    orig_indices = orig_list,
                    area = f.calc_area(),
                    face_type = face_type,
                    normal = f.normal,
                    edges = edges_info,
                    vertices = vert_coords
                ))

            meshes.append(Mesh(
                name = obj.name,
                size = size,
                convex_points = convex_verts,
                concave_points = concave_verts,
                flat_points = flat_verts,
                faces = faces_output
            ))

            bm.free()
        return meshes

if __name__ == '__main__':
    CalculateGeometry()
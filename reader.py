import json
from typing import List
from geometry_connector.models import Mesh, Face, Edge
from geometry_connector.constants import JSON_PATH
from mathutils import Vector


class Reader:
    @staticmethod
    def read_meshes(filepath: str = JSON_PATH) -> List[Mesh]:
        with open(filepath, 'r') as f:
            data = json.load(f)

        meshes = []
        for md in data:
            faces = []
            for fd in md['faces']:
                edges = [
                    Edge(
                        new_index = ed['new_index'],
                        orig_indices = ed['orig_indices'],
                        length = ed['length'],
                        vertices = ed['vertices']
                    )
                    for ed in fd['edges']
                ]
                face = Face(
                    new_index = fd['new_index'],
                    orig_indices = fd['orig_indices'],
                    area = fd['area'],
                    face_type = fd['face_type'],
                    normal = Vector(fd['normal']),
                    vertices = fd['vertices'],
                    edges = edges
                )
                faces.append(face)

            mesh = Mesh(
                name = md['name'],
                size = md['size'],
                convex_points = md['convex_points'],
                concave_points = md['concave_points'],
                flat_points = md['flat_points'],
                faces = faces
            )
            meshes.append(mesh)

        print(f"Mesh-объекты считаны из файла: {filepath}")
        return meshes
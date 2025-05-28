import json
from typing import List
from geometry_connector.models import Mesh, MeshGraph, Network
from geometry_connector.constants import JSON_PATH


class Writer:
    @staticmethod
    def write_meshes_to_json(meshes: List[Mesh], filepath: str = JSON_PATH):
        data = []
        for m in meshes:
            md = {
                'name': m.name,
                'size': m.size,
                'convex_points': m.convex_points,
                'concave_points': m.concave_points,
                'flat_points': m.flat_points,
                'matrix_world': [list(row) for row in m.matrix_world],
                'faces': [
                    {
                        'new_index': f.new_index,
                        'orig_indices': f.orig_indices,
                        'area': f.area,
                        'face_type': f.face_type,
                        'normal': list(f.normal),
                        'vertices': f.vertices,
                        'edges': [
                            {
                                'new_index': e.new_index,
                                'orig_indices': e.orig_indices,
                                'vertices': e.vertices,
                                'length': e.length
                            }
                            for e in f.edges
                        ]
                    }
                    for f in m.faces
                ]
            }
            data.append(md)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent = 4)
        print(f"Параметры Mesh записаны в файл: {filepath}")


    @staticmethod
    def print_graph(graph: MeshGraph):
        print("Graph matches:")
        # Чтобы не дублировать двусторонние связи, будем выводить только m1 < m2
        seen = set()
        for m1, nbrs in graph.connections.items():
            for m2, matches in nbrs.items():
                if (m2, m1) in seen:
                    continue
                seen.add((m1, m2))

                print(f"\n{m1} ↔ {m2}:")
                for match in matches:
                    mt = match.match_type.name
                    idx1, idx2 = match.indices
                    coeff = match.coeff
                    print(f"  - {mt}: indices {idx1} ↔ {idx2}, coeff = {coeff:.3f}")
        print("\nВсего узлов:", len(graph.connections))
        total_edges = sum(len(v) for d in graph.connections.values() for v in d.values()) // 2
        print("Всего связей:", total_edges)


    @staticmethod
    def print_networks(networks: List[Network]):
        if not networks:
            print("No networks to display.")
            return

        for i, net in enumerate(networks, start=1):
            print(f"\nNetwork {i}: weight = {net.weight:.3f}")
            for match in net.matches:
                mt = match.match_type.name
                m1, m2 = match.mesh1, match.mesh2
                idx1, idx2 = match.indices
                coeff = match.coeff
                print(f"  - {mt}: {m1}[{idx1}] ↔ {m2}[{idx2}], coeff = {coeff:.3f}")
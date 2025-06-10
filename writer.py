import json
from typing import List
from geometry_connector.enums import MatchType
from geometry_connector.models import Mesh, MeshGraph, Network
from geometry_connector.constants import JSON_PATH, GRAPH_PATH
import networkx as nx
import matplotlib.pyplot as plt


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
        for mesh1, nbrs in graph.connections.items():
            for mesh2, matches in nbrs.items():
                if (mesh2, mesh1) in seen:
                    continue
                seen.add((mesh1, mesh2))

                print(f"\n{mesh1} ↔ {mesh2}:")
                for match in matches:
                    match_type = match.match_type.name
                    idx1, idx2 = match.indices
                    coeff = match.coeff
                    print(f"  - {match_type}: indices {idx1} ↔ {idx2}, coeff = {coeff:.3f}")
        print("\nВсего узлов:", len(graph.connections))
        total_edges = sum(len(v) for d in graph.connections.values() for v in d.values()) // 2
        print("Всего связей:", total_edges)

    @staticmethod
    def draw_graph(graph: "MeshGraph", filepath: str = GRAPH_PATH):
        # Собираем неориентированный граф NetworkX
        G = nx.Graph()
        # Словарь для хранения многострочных подписей рёбер
        edge_labels = {}

        for mesh1, nbrs in graph.connections.items():
            # Добавляем вершину (если ещё не была добавлена)
            G.add_node(mesh1)
            for mesh2, matches in nbrs.items():
                if mesh1 >= mesh2:
                    continue

                # Добавляем ребро
                G.add_edge(mesh1, mesh2)

                # Собираем подпись для этого ребра
                lines = []
                for match in matches:
                    i1, i2 = match.indices
                    coeff = match.coeff
                    lines.append(f"{'F' if match.match_type is MatchType.FACE else 'E'}: {i1}↔{i2}, {coeff:.3f}")

                # Многострочная подпись: каждый match — новая строка
                label_text = "\n".join(lines)
                edge_labels[(mesh1, mesh2)] = label_text

        # Вычисляем расположение узлов
        pos = nx.spring_layout(G, k=1.2, iterations=1000, seed=31)

        # Отображаем узлы и подписи
        plt.figure(figsize=(15, 12))
        nx.draw_networkx_nodes(G, pos, node_color='lightgreen', node_size=1000)
        nx.draw_networkx_labels(G, pos, font_size=10, font_weight='bold')

        # Отображаем рёбра
        nx.draw_networkx_edges(G, pos, width=2)

        # Отображаем подписи рёбер
        text_items = nx.draw_networkx_edge_labels(
            G,
            pos,
            edge_labels=edge_labels,
            font_color='gray',
            font_size=7,
            label_pos=0.5,
            rotate=False
        )

        for text in text_items.values():
            text.set_zorder(4)

        # Cохранение в файл
        plt.title("Визуализация MeshGraph: узлы и детальные совпадения")
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(filepath, dpi=300)
        plt.close()


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
from typing import List, Dict, Set
from geometry_connector.enums import MatchType
from geometry_connector.models import MeshGraph, GraphMatch, Network
import copy
from collections import deque


def sort_graph(graph: MeshGraph) -> MeshGraph:
    # Глубокое копирование, чтобы не изменять оригинальный граф
    new_graph = copy.deepcopy(graph)

    # Будем хранить лучший coeff для каждого меша, чтобы потом отсортировать весь словарь
    best_coeff_per_mesh = {}

    # Проходим по каждому мешу и его соседям, сортируем matches и сразу вычисляем лучший coeff
    for mesh, nbrs in new_graph.connections.items():
        best_coeff_for_this_mesh = 0.0
        # Лучший coeff у каждого соседа
        neighbor_best = {}

        for nbr, matches in nbrs.items():
            # Сортируем: сначала FACE (False=0), потом EDGE (True=1); внутри — по убыванию coeff
            matches.sort(key=lambda m: (m.match_type != MatchType.FACE, -m.coeff))

            if matches:
                bc = matches[0].coeff
            else:
                bc = 0.0

            neighbor_best[nbr] = bc
            if bc > best_coeff_for_this_mesh:
                best_coeff_for_this_mesh = bc

        # Сортируем словарь nbrs по neighbor_best[nbr] и перезаписываем
        new_graph.connections[mesh] = dict(
            sorted(nbrs.items(), key=lambda item: -neighbor_best[item[0]])
        )

        best_coeff_per_mesh[mesh] = best_coeff_for_this_mesh

    # Сортируем весь словарь new_graph.connections по best_coeff_per_mesh[mesh]
    new_graph.connections = dict(
        sorted(
            new_graph.connections.items(),
            key=lambda item: -best_coeff_per_mesh[item[0]]
        )
    )

    return new_graph


# Выдаёт сети группами для оптимизации
def generate_networks(graph: MeshGraph):
    connections = graph.connections

    nodes: Set[str] = set(connections.keys())
    for nbrs in connections.values():
        nodes |= set(nbrs.keys())

    all_matches: List[GraphMatch] = []
    for m1, nbrs in connections.items():
        for m2, matches in nbrs.items():
            for match in matches:
                if match not in all_matches:
                    all_matches.append(match)

    def dfs(current: List[GraphMatch], used_idx: Dict[str, Set[int]], used_meshes: Set[str],
            skipped_matches: Set[GraphMatch]):
        if used_meshes == nodes:
            if any(m.match_type == MatchType.FACE for m in current):
                yield Network(matches=list(current))
            return

        ordered_matches = order_matches(all_matches, current, connections)

        for match in ordered_matches:
            a, b = match.mesh1, match.mesh2
            index_a, index_b = match.indices

            if match in skipped_matches:
                continue

            if index_a in used_idx.get(a, ()) or index_b in used_idx.get(b, ()):
                continue

            if len(used_meshes) is 0:
                used_idx.setdefault(a, set()).add(index_a)
                used_idx.setdefault(b, set()).add(index_b)
                used_meshes.add(a)
                used_meshes.add(b)

                current.append(match.inverted)
                yield from dfs(current, used_idx, used_meshes, skipped_matches)
                current.pop()

                current.append(match)
                yield from dfs(current, used_idx, used_meshes, skipped_matches)
                current.pop()

                used_idx[a].remove(index_a)
                used_idx[b].remove(index_b)
                used_meshes.remove(a)
                used_meshes.remove(b)

                skipped_matches.add(match)
                continue

            connected_meshes = [connect.mesh2 for connect in current]
            can_add_a = a not in connected_meshes
            can_add_b = b not in connected_meshes

            if not can_add_a and not can_add_b:
                continue

            not_used_a = a not in used_meshes
            not_used_b = b not in used_meshes

            if can_add_a and not_used_a:
                if not_used_b:
                    continue
                else:
                    used_idx.setdefault(a, set()).add(index_a)
                    used_idx.setdefault(b, set()).add(index_b)
                    if not_used_a:
                        used_meshes.add(a)
                    if not_used_b:
                        used_meshes.add(b)

                    current.append(match.inverted)
                    yield from dfs(current, used_idx, used_meshes, skipped_matches)
                    current.pop()

                    used_idx[a].remove(index_a)
                    used_idx[b].remove(index_b)
                    if not_used_a:
                        used_meshes.remove(a)
                    if not_used_b:
                        used_meshes.remove(b)

            if can_add_b and not_used_b:
                if not_used_a:
                    continue
                else:
                    used_idx.setdefault(a, set()).add(index_a)
                    used_idx.setdefault(b, set()).add(index_b)
                    if not_used_a:
                        used_meshes.add(a)
                    if not_used_b:
                        used_meshes.add(b)

                    current.append(match)
                    yield from dfs(current, used_idx, used_meshes, skipped_matches)
                    current.pop()

                    used_idx[a].remove(index_a)
                    used_idx[b].remove(index_b)
                    if not_used_a:
                        used_meshes.remove(a)
                    if not_used_b:
                        used_meshes.remove(b)

            skipped_matches.add(match)
            continue

    yield from dfs([], {}, set(), set())


# Сортируем по возрастанию расстояния
def order_matches(all_matches, current, connections):
    if not current:
        return all_matches

    start_mesh = current[0].mesh2

    dist = {start_mesh: 0}
    queue = deque([start_mesh])
    while queue:
        u = queue.popleft()
        for v in connections.get(u, {}).keys():
            if v not in dist:
                dist[v] = dist[u] + 1
                queue.append(v)

    def match_dist(m):
        return dist.get(m.mesh2, float('inf'))

    return sorted(all_matches, key=match_dist)
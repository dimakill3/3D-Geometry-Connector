from typing import List, Dict, Set
from geometry_connector.enums import MatchType
from geometry_connector.models import MeshGraph, GraphMatch, Network
import copy


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

    # Собираем все меши
    nodes: Set[str] = set(connections.keys())
    for nbrs in connections.values():
        nodes |= set(nbrs.keys())

    # Предварительно группируем мэтчи по парам
    pair_to_matches: Dict[frozenset, List[GraphMatch]] = {}
    for m1, nbrs in connections.items():
        for m2, matches in nbrs.items():
            if m1 < m2:
                key = frozenset((m1, m2))
                pair_to_matches.setdefault(key, []).extend(matches)

    pairs = list(pair_to_matches.keys())

    # Рекурсивный dfs
    def dfs(idx: int, current: List[GraphMatch], used_idx: Dict[str, Set[int]], used_meshes: Set[str],
            skipped_connections: Set[GraphMatch], outdated_connections: List[GraphMatch]):
        # Если досчитали все пары — выдаём сеть
        if used_meshes == nodes:
            if any(m.match_type == MatchType.FACE for m in current):
                yield Network(matches=list(current))
            return

        if idx >= len(pairs):
            return

        key = pairs[idx]
        matches = pair_to_matches[key]

        def try_connect(try_match : GraphMatch, outdated : bool):
            # Пропускаем, если совпадение пропущено
            if try_match in skipped_connections:
                return

            a, b = try_match.mesh1, try_match.mesh2
            index_a, index_b = try_match.indices

            # Пропускаем, если индексы уже заняты
            if index_a in used_idx.get(a, ()) or index_b in used_idx.get(b, ()):
                return

            # Случай, когда сеть пустая, нужно начать с любого соединения
            if len(used_meshes) == 0 and not outdated:
                used_idx.setdefault(a, set()).add(index_a)
                used_idx.setdefault(b, set()).add(index_b)
                used_meshes.add(a)
                used_meshes.add(b)

                # a -> b
                current.append(try_match.inverted)
                yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)
                current.pop()

                # b -> a
                current.append(try_match)
                yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)
                current.pop()

                used_idx[a].remove(index_a)
                used_idx[b].remove(index_b)
                used_meshes.remove(a)
                used_meshes.remove(b)

                # Не используем данное соединение
                skipped_connections.add(try_match)
                yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)
                return

            # Смотрим, какие мэши уже присоединены
            connected_meshes = [connect.mesh2 for connect in current]
            can_add_a = a not in connected_meshes
            can_add_b = b not in connected_meshes

            # Пропускаем, если оба присоединены
            if not can_add_a and not can_add_b:
                return

            not_used_a = a not in used_meshes
            not_used_b = b not in used_meshes

            # a -> b
            if can_add_a and not_used_a:
                # a -> b не может быть присоединено и не было отложено
                if not_used_b and not outdated:
                    outdated_connections.append(try_match.inverted)
                    yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)
                    outdated_connections.pop()
                # a -> b может быть присоединено
                elif not not_used_b:
                    used_idx.setdefault(a, set()).add(index_a)
                    used_idx.setdefault(b, set()).add(index_b)
                    if not_used_a:
                        used_meshes.add(a)
                    if not_used_b:
                        used_meshes.add(b)

                    current.append(try_match.inverted)
                    if outdated:
                        outdated_connections.remove(try_match)
                    yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)
                    current.pop()

                    used_idx[a].remove(index_a)
                    used_idx[b].remove(index_b)
                    if not_used_a:
                        used_meshes.remove(a)
                    if not_used_b:
                        used_meshes.remove(b)

            # b -> a
            if can_add_b and not_used_b:
                # b -> a не может быть присоединено и не было отложено
                if not_used_a and not outdated:
                    outdated_connections.append(try_match)
                    yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)
                    outdated_connections.pop()
                # b -> a может быть присоединено
                elif not not_used_a:
                    used_idx.setdefault(a, set()).add(index_a)
                    used_idx.setdefault(b, set()).add(index_b)
                    if not_used_a:
                        used_meshes.add(a)
                    if not_used_b:
                        used_meshes.add(b)

                    current.append(try_match)
                    if outdated:
                        outdated_connections.remove(try_match)
                    yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)
                    current.pop()

                    used_idx[a].remove(index_a)
                    used_idx[b].remove(index_b)
                    if not_used_a:
                        used_meshes.remove(a)
                    if not_used_b:
                        used_meshes.remove(b)

            skipped_connections.add(try_match)
            yield from dfs(idx + 1, current, used_idx, used_meshes, skipped_connections, outdated_connections)

        for match in outdated_connections:
            try_connect(match, True)

        # Пробуем добавить каждый мэтч из пары
        for match in matches:
            try_connect(match, False)

        return


    # Начинаем обход графа
    yield from dfs(0, [], {}, set(), set(), [])

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
        print(f"Текущая сеть: {[f'{m.mesh1}->{m.mesh2}' for m in current]}")
        print(f"Задействованные меши: {used_meshes}")
        print(f"Занятые индексы: {used_idx}")
        print(f"Пропущенные соединения: {[f'{m.mesh1}->{m.mesh2}' for m in skipped_matches]}")

        if used_meshes == nodes:
            if any(m.match_type == MatchType.FACE for m in current):
                print(">>> Сформирована полная сеть:")
                for match in current:
                    print(
                        f"    {match.mesh1} → {match.mesh2} | type: {match.match_type.name} | indices: {match.indices} | coeff: {match.coeff:.3f}")
                yield Network(matches=list(current))
            else:
                print("Пропущена сеть — не содержит FACE соединений.")
            return

        # Вычисляем «расстояние» для каждого match от первого в current
        if current:
            start_mesh = current[0].mesh1

            # BFS по меш-графу, чтобы найти минимальное число переходов между мешами:
            dist_from_start: Dict[str, int] = {start_mesh: 0}
            queue = deque([start_mesh])

            while queue:
                u = queue.popleft()
                # neighbors — это все меши, которые смежны с u (ключи connections[u])
                for v in connections.get(u, {}).keys():
                    if v not in dist_from_start:
                        dist_from_start[v] = dist_from_start[u] + 1
                        queue.append(v)

            def match_distance(m: GraphMatch) -> int:
                return dist_from_start.get(m.mesh2, float('inf'))

            # Сортируем все совпадения по возрастанию расстояния
            ordered_matches = sorted(all_matches, key=lambda m: match_distance(m))
        else:
            # Если current пуст, берём исходный порядок
            ordered_matches = all_matches

        for match in ordered_matches:
            a, b = match.mesh1, match.mesh2
            index_a, index_b = match.indices
            print(f"Рассматриваем совпадение: {a} ↔ {b}")

            if match in skipped_matches:
                print(f"❌ Пропущено ранее: {a} ↔ {b}")
                continue

            if index_a in used_idx.get(a, ()) or index_b in used_idx.get(b, ()):
                print(f"⚠️ Индексы заняты: {a}[{index_a}] или {b}[{index_b}]")
                continue

            if len(used_meshes) is 0:
                print(f"🚀 Стартуем с соединения: {a} ↔ {b}")
                used_idx.setdefault(a, set()).add(index_a)
                used_idx.setdefault(b, set()).add(index_b)
                used_meshes.add(a)
                used_meshes.add(b)

                current.append(match.inverted)
                print(f"➕ Добавлено: {a} → {b}")
                yield from dfs(current, used_idx, used_meshes, skipped_matches)
                current.pop()

                current.append(match)
                print(f"➕ Добавлено: {b} → {a}")
                yield from dfs(current, used_idx, used_meshes, skipped_matches)
                current.pop()

                used_idx[a].remove(index_a)
                used_idx[b].remove(index_b)
                used_meshes.remove(a)
                used_meshes.remove(b)

                skipped_matches.add(match)
                print(f"🔁 Пробуем без соединения: {a} ↔ {b}")
                continue

            connected_meshes = [connect.mesh2 for connect in current]
            can_add_a = a not in connected_meshes
            can_add_b = b not in connected_meshes

            if not can_add_a and not can_add_b:
                print(f"⛔ Оба меша уже подключены: {a}, {b}")
                continue

            not_used_a = a not in used_meshes
            not_used_b = b not in used_meshes

            if can_add_a and not_used_a:
                if not_used_b:
                    print(f"🕒 Откладываем {a} → {b}")
                    continue
                else:
                    used_idx.setdefault(a, set()).add(index_a)
                    used_idx.setdefault(b, set()).add(index_b)
                    if not_used_a:
                        used_meshes.add(a)
                    if not_used_b:
                        used_meshes.add(b)

                    current.append(match.inverted)
                    print(f"🔗 Пробуем: {a} → {b}")
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
                    print(f"🕒 Откладываем {b} → {a}")
                    continue
                else:
                    used_idx.setdefault(a, set()).add(index_a)
                    used_idx.setdefault(b, set()).add(index_b)
                    if not_used_a:
                        used_meshes.add(a)
                    if not_used_b:
                        used_meshes.add(b)

                    current.append(match)
                    print(f"🔗 Пробуем: {b} → {a}")
                    yield from dfs(current, used_idx, used_meshes, skipped_matches)
                    current.pop()

                    used_idx[a].remove(index_a)
                    used_idx[b].remove(index_b)
                    if not_used_a:
                        used_meshes.remove(a)
                    if not_used_b:
                        used_meshes.remove(b)

            skipped_matches.add(match)
            print(f"Пробуем без: {a} ↔ {b}")
            continue

    print("🔍 Начинаем построение всех возможных сетей...\n")
    yield from dfs([], {}, set(), set())
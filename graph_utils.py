from typing import List, Dict, Set
from geometry_connector.enums import MatchType
from geometry_connector.models import MeshGraph, GraphMatch, Network
import copy


def sort_graph(graph: MeshGraph) -> MeshGraph:
    # Глубокое копирование, чтобы не изменять оригинальный граф
    new_graph = copy.deepcopy(graph)

    for mesh, nbrs in new_graph.connections.items():
        for nbr, matches in nbrs.items():
            # Сортировка: FACE первыми, затем EDGE; внутри каждого типа по убыванию coeff
            matches.sort(key=lambda m: (0 if m.match_type == MatchType.FACE else 1, -m.coeff))
            # Убираем EDGE, если есть идеальный FACE
            if any(m.match_type == MatchType.FACE and abs(m.coeff - 1.0) < 1e-6 for m in matches):
                new_graph.connections[mesh][nbr] = [m for m in matches if m.match_type == MatchType.FACE]
    return new_graph


# Выдаёт сети группами для оптимизации
def generate_networks(graph: MeshGraph):
    print(f"Начало генерации сетей")
    connections = graph.connections

    # Собираем все меши
    nodes: Set[str] = set(connections.keys())
    for nbrs in connections.values():
        nodes |= set(nbrs.keys())

    # Предварительно группируем матчи по парам
    pair_to_matches: Dict[frozenset, List[GraphMatch]] = {}
    for m1, nbrs in connections.items():
        for m2, matches in nbrs.items():
            if m1 < m2:
                key = frozenset((m1, m2))
                pair_to_matches.setdefault(key, []).extend(matches)

    pairs = list(pair_to_matches.keys())

    # Рекурсивный dfs
    def dfs(idx: int, current: List[GraphMatch], used_idx: Dict[str, Set[int]], used_meshes: Set[str]):
        print(f"DFS вызов idx={idx}, current_len={len(current)}, used_meshes={used_meshes}")

        # Если досчитали все пары — выдаём сеть
        if used_meshes == nodes:
            print("Все меши объединены в сеть.")
            if any(m.match_type == MatchType.FACE for m in current):
                print(f"Найден FACE-матч, генерируем Network с {len(current)} матчами")
                yield Network(matches=list(current))
            else:
                print("FACE-матч не найден, сеть не возвращается")
            return

        if idx >= len(pairs):
            print(f"Индекс idx={idx} вне диапазона пар, возврат без генерации")
            return

        key = pairs[idx]
        matches = pair_to_matches[key]

        # Пробуем добавить каждый мэтч из пары
        for match in matches:
            a, b = match.mesh1, match.mesh2
            index_a, index_b = match.indices
            print(f"Проверка матча {a} <-> {b}: индексы ({index_a}, {index_b})")

            # Пропускаем, если индексы уже заняты
            if index_a in used_idx.get(a, ()) or index_b in used_idx.get(b, ()):
                print(f"Индексы уже используется, пропуск матча")
                continue

            # Смотрим, какие мэши уже присоединены
            connected_meshes = [connect.mesh2 for connect in current]
            need_add_a = a not in connected_meshes
            need_add_b = b not in connected_meshes
            print(f"connected_meshes={connected_meshes}, need_add_a={need_add_a}, need_add_b={need_add_b}")

            if not need_add_a and not need_add_b:
                print(f"Невозможно добавить ни одного матча, пропуск")
                continue

            # Маркируем занятые индексы
            used_idx.setdefault(a, set()).add(index_a)
            used_idx.setdefault(b, set()).add(index_b)
            added_a = a not in used_meshes
            added_b = b not in used_meshes
            if added_a:
                used_meshes.add(a)
            if added_b:
                used_meshes.add(b)

            # Если b ещё не присоединён
            if need_add_b:
                print(f"Добавление прямого соединения {b} -> {a}")
                current.append(match)
                yield from dfs(idx + 1, current, used_idx, used_meshes)
                current.pop()
                print(f"Откат прямого соединения {b} -> {a}")

            # Если a ещё не присоединён
            if need_add_a:
                print(f"Добавление инверсного соединения {a} -> {b}")
                current.append(match.inverted)
                yield from dfs(idx + 1, current, used_idx, used_meshes)
                current.pop()
                print(f"Откат инверсного соединения {a} -> {b}")

            # Снимаем маркировку занятых индексов
            used_idx[a].remove(index_a)
            used_idx[b].remove(index_b)
            if added_a:
                used_meshes.remove(a)
            if added_b:
                used_meshes.remove(b)

        # Продолжаем поиск без мэтчей из этой пары
        print(f"Переход к следующей паре без текущих матчей, idx={idx}")
        yield from dfs(idx + 1, current, used_idx, used_meshes)

    # Начинаем обход графа
    yield from dfs(0, [], {}, set())

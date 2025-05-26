from typing import List, Dict, Set
from geometry_connector.enums import MatchType
from geometry_connector.models import MeshGraph, GraphMatch, Network
import copy


def sort_graph(graph: MeshGraph) -> MeshGraph:
    # Глубокое копирование, чтобы не изменять оригинальный граф
    new_graph = copy.deepcopy(graph)

    for mesh, nbrs in new_graph.adj.items():
        for nbr, matches in nbrs.items():
            # Сортировка: FACE первыми, затем EDGE; внутри каждого типа по убыванию coeff
            matches.sort(key=lambda m: (0 if m.match_type == MatchType.FACE else 1, -m.coeff))
            # Убираем EDGE, если есть идеальный FACE
            if any(m.match_type == MatchType.FACE and abs(m.coeff - 1.0) < 1e-6 for m in matches):
                new_graph.adj[mesh][nbr] = [m for m in matches if m.match_type == MatchType.FACE]
    return new_graph


def build_networks(graph: MeshGraph) -> List[Network]:
    adj = graph.adj
    # Собираем все имена мешей
    nodes: Set[str] = set(adj.keys())
    for nbrs in adj.values():
        nodes.update(nbrs.keys())

    # Группируем совпадения по парам мешей
    pair_to_matches: Dict[frozenset, List[GraphMatch]] = {}
    for m1, nbrs in adj.items():
        for m2, matches in nbrs.items():
            if m1 < m2:
                key = frozenset((m1, m2))
                pair_to_matches.setdefault(key, []).extend(matches)

    # Оставляем все FACE и лучший EDGE, затем сортируем
    for key, matches in pair_to_matches.items():
        face_ms = [m for m in matches if m.match_type == MatchType.FACE]
        edge_ms = [m for m in matches if m.match_type == MatchType.EDGE]
        best_edge = max(edge_ms, key=lambda m: m.coeff) if edge_ms else None
        filtered = face_ms + ([best_edge] if best_edge else [])
        filtered.sort(key=lambda m: (-m.coeff, 0 if m.match_type == MatchType.FACE else 1))
        pair_to_matches[key] = filtered

    pairs = list(pair_to_matches.keys())
    networks: List[Network] = []

    # Рекурсивный DFS
    def dfs(idx, current, used_idx, used_meshes):
        # Если все меши — сохраняем сеть (только если есть FACE)
        if used_meshes == nodes:
            if any(m.match_type == MatchType.FACE for m in current):
                networks.append(Network(matches=list(current)))
            return
        if idx >= len(pairs):
            return

        key = pairs[idx]
        for m in pair_to_matches[key]:
            a, b = m.mesh1, m.mesh2
            i_a, i_b = m.indices

            if a in used_meshes and b in used_meshes:
                continue
            if i_a in used_idx.get(a, ()) or i_b in used_idx.get(b, ()):
                continue

            # «выбираем» матч
            used_idx.setdefault(a, set()).add(i_a)
            used_idx.setdefault(b, set()).add(i_b)
            added_a = a not in used_meshes
            added_b = b not in used_meshes
            if added_a: used_meshes.add(a)
            if added_b: used_meshes.add(b)
            current.append(m)

            dfs(idx + 1, current, used_idx, used_meshes)

            # «откатываем»
            current.pop()
            used_idx[a].remove(i_a)
            used_idx[b].remove(i_b)
            if added_a: used_meshes.remove(a)
            if added_b: used_meshes.remove(b)

        # Ветка без матчей из этой пары
        dfs(idx + 1, current, used_idx, used_meshes)

    dfs(0, [], {}, set())

    # Финальная сортировка по количеству FACE и весу
    networks.sort(
        key=lambda net: (
            sum(1 for m in net.matches if m.match_type == MatchType.FACE),
            net.weight
        ),
        reverse=True
    )
    return networks


def generate_networks(graph: MeshGraph):
    """
    Генератор, который по частям выдаёт объекты Network
    """
    adj = graph.adj

    # собираем все меши
    nodes = set(adj.keys())
    for nbrs in adj.values():
        nodes |= set(nbrs.keys())

    # предварительно группируем матчи по парам (как раньше)
    pair_to_matches: Dict[frozenset, List[GraphMatch]] = {}
    for m1, nbrs in adj.items():
        for m2, matches in nbrs.items():
            if m1 < m2:
                key = frozenset((m1, m2))
                # здесь по желанию можно оставить только best_face/best_edge
                pair_to_matches.setdefault(key, []).extend(matches)

    pairs = list(pair_to_matches.keys())

    # рекурсивный dfs, но как генератор
    def dfs(idx: int,
            current: List[GraphMatch],
            used_idx: Dict[str, Set[int]],
            used_meshes: Set[str]):
        # если досчитали все пары — выдаём сеть
        if used_meshes == nodes:
            if any(m.match_type == MatchType.FACE for m in current):
                yield Network(matches=list(current))
            return
        if idx >= len(pairs):
            return

        key = pairs[idx]
        matches = pair_to_matches[key]

        # ветка: пробуем каждый матч
        for m in matches:
            a, b = m.mesh1, m.mesh2
            ia, ib = m.indices
            # пропускаем, если индексы уже заняты
            if ia in used_idx.get(a, ()) or ib in used_idx.get(b, ()):
                continue

            # отмечаем
            used_idx.setdefault(a, set()).add(ia)
            used_idx.setdefault(b, set()).add(ib)
            added_a = a not in used_meshes
            added_b = b not in used_meshes
            if added_a: used_meshes.add(a)
            if added_b: used_meshes.add(b)
            current.append(m)

            # рекурсивно углубляемся
            yield from dfs(idx + 1, current, used_idx, used_meshes)

            # откатываем
            current.pop()
            used_idx[a].remove(ia)
            used_idx[b].remove(ib)
            if added_a: used_meshes.remove(a)
            if added_b: used_meshes.remove(b)

        # и ветка без матчей из этой пары
        yield from dfs(idx + 1, current, used_idx, used_meshes)

    # стартуем
    yield from dfs(0, [], {}, set())

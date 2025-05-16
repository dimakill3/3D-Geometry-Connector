import itertools
from typing import List, Dict, Set, FrozenSet
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
    # 1) Собираем все имена мешей
    nodes: Set[str] = set(graph.adj.keys())
    for nbrs in graph.adj.values():
        nodes.update(nbrs.keys())

    # 2) Группируем совпадения по парам мешей
    pair_to_matches: Dict[FrozenSet[str], List[GraphMatch]] = {}
    for m1, nbrs in graph.adj.items():
        for m2, matches in nbrs.items():
            if m1 < m2:
                key = frozenset((m1, m2))
                pair_to_matches.setdefault(key, []).extend(matches)

    # 3) Для каждой пары оставляем все FACE и одно лучшее EDGE, сортируем
    for key, matches in pair_to_matches.items():
        face = [m for m in matches if m.match_type == MatchType.FACE]
        edge = [m for m in matches if m.match_type == MatchType.EDGE]
        best_edge = max(edge, key=lambda m: m.coeff) if edge else None
        filtered = face + ([best_edge] if best_edge else [])
        filtered.sort(key=lambda m: (-(m.coeff), 0 if m.match_type == MatchType.FACE else 1))
        pair_to_matches[key] = filtered

    # 4) Порядок пар для рекурсии
    pairs = list(pair_to_matches.keys())
    networks: List[Network] = []

    # Рекурсивный поиск без повторов и без циклов (просто пропускаем matches, если оба меша уже в сети)
    def dfs(
            idx: int,
            current: List[GraphMatch],
            used_indices: Dict[str, Set[int]],
            used_meshes: Set[str]
    ):
        # если уже собрали все меши — сохраняем сеть и не идём дальше
        if used_meshes == nodes:
            networks.append(Network(matches=list(current)))
            return
        # если пар больше нет — сохраняем то, что есть
        if idx >= len(pairs):
            networks.append(Network(matches=list(current)))
            return

        key = pairs[idx]
        for match in pair_to_matches[key]:
            m1, m2 = match.mesh1, match.mesh2
            i1, i2 = match.indices

            # 1) пропускаем, если оба меша уже в сети
            if m1 in used_meshes and m2 in used_meshes:
                continue

            # 2) пропускаем конфликт по индексам
            if i1 in used_indices.get(m1, set()) or i2 in used_indices.get(m2, set()):
                continue

            # выбираем этот матч
            used_indices.setdefault(m1, set()).add(i1)
            used_indices.setdefault(m2, set()).add(i2)
            added1 = m1 not in used_meshes
            added2 = m2 not in used_meshes
            if added1: used_meshes.add(m1)
            if added2: used_meshes.add(m2)
            current.append(match)

            # рекурсивно идём к следующей паре
            dfs(idx + 1, current, used_indices, used_meshes)

            # откатываем выбор
            current.pop()
            used_indices[m1].remove(i1)
            used_indices[m2].remove(i2)
            if added1: used_meshes.remove(m1)
            if added2: used_meshes.remove(m2)

        # 3) Также пробуем *не* брать ни одного совпадения из этой пары
        dfs(idx + 1, current, used_indices, used_meshes)

    # старт рекурсии
    dfs(0, [], {}, set())

    # 5) Сортировка по числу FACE и весу
    networks.sort(
        key=lambda net: (
            sum(1 for m in net.matches if m.match_type == MatchType.FACE),
            net.weight
        ),
        reverse=True
    )
    return networks
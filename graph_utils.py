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
    # Группируем совпадения по парам мешей
    pair_to_matches: Dict[FrozenSet[str], List[GraphMatch]] = {}
    for m1, nbrs in graph.adj.items():
        for m2, matches in nbrs.items():
            if m1 < m2:
                key = frozenset((m1, m2))
                pair_to_matches.setdefault(key, []).extend(matches)

    # Оставляем для каждой пары все FACE и одно лучшее EDGE, сортируем их
    for key, matches in pair_to_matches.items():
        face = [m for m in matches if m.match_type == MatchType.FACE]
        edge = [m for m in matches if m.match_type == MatchType.EDGE]
        best_edge = max(edge, key=lambda m: m.coeff) if edge else None
        filtered = face + ([best_edge] if best_edge else [])
        filtered.sort(key=lambda m: (-(m.coeff), 0 if m.match_type == MatchType.FACE else 1))
        pair_to_matches[key] = filtered

    # Формируем все комбинации: по одному совпадению на каждую пару
    keys = list(pair_to_matches.keys())
    choices = [pair_to_matches[k] for k in keys]
    networks: List[Network] = []

    for combo in itertools.product(*choices):
        used_indices: Dict[str, Set[int]] = {}
        conflict = False
        for match in combo:
            for mesh, idx in [(match.mesh1, match.indices[0]), (match.mesh2, match.indices[1])]:
                if idx in used_indices.get(mesh, set()):
                    conflict = True
                    break
                used_indices.setdefault(mesh, set()).add(idx)
            if conflict:
                break
        if not conflict:
            networks.append(Network(matches=list(combo)))

    # Сортируем сети по сумме coeff (весу)
    networks.sort(key=lambda net: net.weight, reverse=True)
    return networks
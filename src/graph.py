"""Граф зависимостей: построение обходом в ширину и поиск циклов.

Обход не зависит от источника данных: ему передаётся функция,
возвращающая прямые зависимости пакета. Рекурсия не используется —
BFS работает на очереди collections.deque, поиск циклов — на явном
стеке. Повторно встреченный пакет в очередь не ставится, поэтому
циклические зависимости не приводят к зацикливанию.
"""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

IN_PROGRESS = 1
DONE = 2


class SourceError(Exception):
    """Не удалось получить зависимости одного пакета."""


@dataclass
class Graph:
    """Граф: root — исходный пакет, edges — списки смежности."""

    root: str
    edges: dict[str, list[str]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def edge_count(self) -> int:
        """Число связей в графе."""
        return sum(len(children) for children in self.edges.values())


def bfs(root: str, neighbours: Callable[[str], list[str]]) -> Graph:
    """Строит граф всех пакетов, достижимых из root, обходом в ширину.

    Если для пакета не удалось получить зависимости, ошибка
    запоминается в Graph.errors, а обход продолжается.
    """
    graph = Graph(root)
    queue = deque([root])
    seen = {root}
    while queue:
        node = queue.popleft()
        try:
            children = neighbours(node)
        except SourceError as error:
            graph.errors[node] = str(error)
            children = []
        graph.edges[node] = children
        for child in children:
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return graph


def cycle_edges(graph: Graph) -> list[tuple[str, str]]:
    """Находит обратные рёбра, замыкающие циклы (DFS на явном стеке)."""
    state: dict[str, int] = {}
    found: list[tuple[str, str]] = []
    for start in graph.edges:
        if start in state:
            continue
        state[start] = IN_PROGRESS
        stack = [(start, iter(graph.edges[start]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                state[node] = DONE
                stack.pop()
            elif state.get(child) == IN_PROGRESS:
                found.append((node, child))
            elif child not in state:
                state[child] = IN_PROGRESS
                stack.append((child, iter(graph.edges.get(child, []))))
    return found


def format_graph(graph: Graph) -> list[str]:
    """Текстовое описание графа: списки смежности, циклы и ошибки."""
    lines = [
        f"Граф зависимостей {graph.root} (пакетов: {len(graph.edges)}, "
        f"связей: {graph.edge_count})"
    ]
    for node, children in graph.edges.items():
        lines.append(f"  {node} -> {', '.join(children) or '(нет)'}")
    cycles = cycle_edges(graph)
    if cycles:
        lines.append("Циклические зависимости (ребро, замыкающее цикл):")
        lines.extend(f"  {source} -> {target}" for source, target in cycles)
    for node, message in graph.errors.items():
        lines.append(f"Ошибка получения зависимостей {node}: {message}")
    return lines

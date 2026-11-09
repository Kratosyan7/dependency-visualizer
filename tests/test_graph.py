"""Тесты построения графа обходом в ширину и поиска циклов."""

import unittest

from graph import SourceError, bfs, cycle_edges, format_graph

LONG_CHAIN = 5000


def source(edges: dict[str, list[str]]):
    """Функция соседей для bfs по словарю смежности."""
    return lambda name: edges.get(name, [])


class TestBfs(unittest.TestCase):
    """Обход в ширину."""

    def test_order_is_breadth_first(self) -> None:
        """Пакеты посещаются по уровням."""
        graph = bfs("A", source({"A": ["B", "C"], "B": ["D"], "C": ["E"]}))
        self.assertEqual(list(graph.edges), ["A", "B", "C", "D", "E"])

    def test_diamond_visited_once(self) -> None:
        """Общая зависимость посещается один раз."""
        calls: list[str] = []
        edges = {"A": ["B", "C"], "B": ["D"], "C": ["D"]}

        def neighbours(name: str) -> list[str]:
            """Запоминает вызовы."""
            calls.append(name)
            return edges.get(name, [])

        graph = bfs("A", neighbours)
        self.assertEqual(calls.count("D"), 1)
        self.assertEqual(graph.edge_count, 4)

    def test_cycle_terminates(self) -> None:
        """Цикл не приводит к зацикливанию."""
        graph = bfs("A", source({"A": ["B"], "B": ["C"], "C": ["A"]}))
        self.assertEqual(set(graph.edges), {"A", "B", "C"})
        self.assertEqual(cycle_edges(graph), [("C", "A")])

    def test_self_loop(self) -> None:
        """Пакет, зависящий от самого себя."""
        graph = bfs("A", source({"A": ["A"]}))
        self.assertEqual(cycle_edges(graph), [("A", "A")])

    def test_unreachable_ignored(self) -> None:
        """Недостижимые пакеты в граф не попадают."""
        graph = bfs("B", source({"A": ["B"], "B": []}))
        self.assertEqual(list(graph.edges), ["B"])

    def test_no_recursion_limit(self) -> None:
        """Длинная цепочка не упирается в предел рекурсии."""
        edges = {str(i): [str(i + 1)] for i in range(LONG_CHAIN)}
        edges[str(LONG_CHAIN)] = ["0"]
        graph = bfs("0", source(edges))
        self.assertEqual(len(graph.edges), LONG_CHAIN + 1)
        self.assertEqual(len(cycle_edges(graph)), 1)

    def test_errors_recorded(self) -> None:
        """Ошибка одного пакета не прерывает обход."""

        def neighbours(name: str) -> list[str]:
            """B недоступен."""
            if name == "B":
                raise SourceError("нет связи")
            return {"A": ["B", "C"]}.get(name, [])

        graph = bfs("A", neighbours)
        self.assertEqual(graph.errors, {"B": "нет связи"})
        self.assertIn("C", graph.edges)


class TestFormat(unittest.TestCase):
    """Текстовый вывод графа."""

    def test_lists_cycles_and_errors(self) -> None:
        """Вывод содержит заголовок, рёбра, циклы и ошибки."""
        graph = bfs("A", source({"A": ["B"], "B": ["A"]}))
        graph.errors["B"] = "сбой"
        lines = format_graph(graph)
        self.assertIn("пакетов: 2, связей: 2", lines[0])
        self.assertIn("  A -> B", lines)
        self.assertIn("  B -> A", lines)
        self.assertTrue(any("сбой" in line for line in lines))


if __name__ == "__main__":
    unittest.main()

"""Тесты визуализации: PlantUML, PNG и ASCII-дерево."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import render
from graph import bfs
from render import (
    RenderError,
    ascii_tree,
    encode_plantuml,
    save_png,
    to_plantuml,
)

PNG = render.PNG_SIGNATURE + b"data"


def graph_of(edges: dict[str, list[str]], root: str = "A"):
    """Граф по словарю смежности."""
    return bfs(root, lambda name: edges.get(name, []))


class TestPlantUml(unittest.TestCase):
    """Текст на языке PlantUML."""

    def test_known_encoding(self) -> None:
        """Совпадает с примером из документации PlantUML."""
        self.assertEqual(encode_plantuml("Bob -> Alice : hello"),
                         "SyfFKj2rKt3CoKnELR1Io4ZDoSa70000")

    def test_structure(self) -> None:
        """Узлы, рёбра, выделение корня и заголовок."""
        text = to_plantuml(graph_of({"A": ["B"]}), "Заголовок")
        self.assertTrue(text.startswith("@startuml"))
        self.assertIn("@enduml", text)
        self.assertIn("title Заголовок", text)
        self.assertIn('rectangle "A" as n0 #LightSkyBlue', text)
        self.assertIn("n0 --> n1", text)

    def test_cycle_edge_highlighted(self) -> None:
        """Ребро, замыкающее цикл, рисуется красным пунктиром."""
        text = to_plantuml(graph_of({"A": ["B"], "B": ["A"]}))
        self.assertIn("n1 -[#Red,dashed]-> n0", text)

    def test_maven_label(self) -> None:
        """Части координат Maven — на отдельных строках подписи."""
        graph = graph_of({}, "g:a:1")
        self.assertIn('"g\\na\\n1"', to_plantuml(graph))

    def test_error_node_color(self) -> None:
        """Пакет с ошибкой выделяется цветом."""
        graph = graph_of({"A": ["B"]})
        graph.errors["B"] = "нет POM"
        self.assertIn("#Pink", to_plantuml(graph))


class TestPng(unittest.TestCase):
    """Сохранение изображения."""

    def setUp(self) -> None:
        """Временный каталог и очищенные переменные окружения."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "g.png"
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("PLANTUML_JAR", None)

    def test_saves_png(self) -> None:
        """Ответ сервера записывается в файл."""
        with mock.patch.object(render, "render_with_server",
                               return_value=PNG):
            save_png("@startuml\n@enduml\n", self.path)
        self.assertEqual(self.path.read_bytes(), PNG)

    def test_not_png(self) -> None:
        """Ответ, не являющийся PNG, — RenderError."""
        with mock.patch.object(render, "render_with_server",
                               return_value=b"<html>"), \
                self.assertRaises(RenderError):
            save_png("x", self.path)

    def test_server_unreachable(self) -> None:
        """Недоступный сервер — RenderError."""
        os.environ["PLANTUML_SERVER"] = "http://127.0.0.1:9"
        with self.assertRaises(RenderError):
            save_png("x", self.path)

    def test_missing_jar(self) -> None:
        """Неверный путь к plantuml.jar — RenderError."""
        os.environ["PLANTUML_JAR"] = "/nonexistent/plantuml.jar"
        with self.assertRaises(RenderError):
            save_png("x", self.path)


class TestAsciiTree(unittest.TestCase):
    """ASCII-дерево зависимостей."""

    def test_branches(self) -> None:
        """Ветви и отступы."""
        lines = ascii_tree(graph_of({"A": ["B", "C"], "B": ["D"]}))
        self.assertEqual(lines, ["A", "├── B", "│   └── D", "└── C"])

    def test_nearest_parent_expands(self) -> None:
        """Поддерево раскрывается под ближайшим родителем, как в Maven."""
        lines = ascii_tree(graph_of({"A": ["B", "C"], "B": ["C"],
                                     "C": ["D"]}))
        self.assertEqual(lines, ["A", "├── B", "│   └── C (*)",
                                 "└── C", "    └── D"])

    def test_cycle_mark(self) -> None:
        """Ребро к предку помечается и не раскрывается."""
        lines = ascii_tree(graph_of({"A": ["B"], "B": ["A"]}))
        self.assertEqual(lines, ["A", "└── B", "    └── A (цикл)"])

    def test_leaf_root(self) -> None:
        """Пакет без зависимостей — одна строка."""
        self.assertEqual(ascii_tree(graph_of({})), ["A"])


if __name__ == "__main__":
    unittest.main()

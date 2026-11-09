"""Тесты точки входа на тестовых репозиториях."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from main import EXIT_CONFIG, EXIT_DATA, EXIT_OK, main


class MainTestCase(unittest.TestCase):
    """Запуск main с временной конфигурацией."""

    def setUp(self) -> None:
        """Создаёт временный каталог."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def run_main(self, repo: str, package: str, extra: str = "") -> tuple:
        """Запускает main; возвращает код, stdout и stderr."""
        repo_path = self.root / "repo.txt"
        repo_path.write_text(repo, encoding="utf-8")
        config = self.root / "c.ini"
        config.write_text(
            f"[package]\nname = {package}\n[repository]\n"
            f"url = {repo_path}\ntest_mode = true\n[output]\n"
            f"image = {self.root / 'g.png'}\n{extra}",
            encoding="utf-8",
        )
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(config)])
        return code, out.getvalue(), err.getvalue()


class TestMain(MainTestCase):
    """Сценарии запуска."""

    def test_graph_printed(self) -> None:
        """Выводится граф с циклом."""
        code, out, _ = self.run_main("A: B\nB: A C\n", "A")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("B -> A, C", out)
        self.assertIn("Циклические", out)

    def test_dependency_only_package(self) -> None:
        """Пакет, упомянутый только как зависимость, допустим."""
        code, out, _ = self.run_main("A: B\n", "B")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("B -> (нет)", out)

    def test_reverse_mode(self) -> None:
        """Режим обратных зависимостей."""
        code, out, _ = self.run_main("A: C\nB: C\nC:\n", "C",
                                     "reverse = true\n")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("зависящих пакетов: 2): A, B", out)

    def test_unknown_package(self) -> None:
        """Пакет, которого нет в репозитории, — ошибка данных."""
        code, _, err = self.run_main("A: B\n", "Q")
        self.assertEqual(code, EXIT_DATA)
        self.assertIn("Q", err)

    def test_bad_repository(self) -> None:
        """Ошибка формата репозитория — ошибка данных."""
        code, _, _ = self.run_main("A B\n", "A")
        self.assertEqual(code, EXIT_DATA)

    def test_bad_config(self) -> None:
        """Ошибка конфигурации — код EXIT_CONFIG."""
        code, _, err = self.run_main("A: B\n", "a")
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("package.name", err)


if __name__ == "__main__":
    unittest.main()

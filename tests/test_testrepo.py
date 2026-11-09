"""Тесты разбора файла тестового репозитория."""

import tempfile
import unittest
from pathlib import Path

from testrepo import TestRepositoryError, load_repository, parse_repository


class TestParse(unittest.TestCase):
    """Формат «ПАКЕТ: ЗАВИСИМОСТИ»."""

    def test_basic(self) -> None:
        """Комментарии и пустые строки пропускаются."""
        text = "# граф\n\nA: B C  # хвост\nB:\n"
        self.assertEqual(parse_repository(text), {"A": ["B", "C"], "B": []})

    def test_repeated_dependency(self) -> None:
        """Повтор зависимости в строке убирается."""
        self.assertEqual(parse_repository("A: B B\n"), {"A": ["B"]})

    def test_multi_letter_names(self) -> None:
        """Имя может состоять из нескольких больших букв."""
        self.assertEqual(parse_repository("APP: CORE"), {"APP": ["CORE"]})

    def test_errors(self) -> None:
        """Нарушения формата сообщают номер строки."""
        cases = ["A B", "a: B", "A: B1", "A: B\nA: C", ": B"]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(
                    TestRepositoryError) as context:
                parse_repository(text)
            self.assertIn("строка", str(context.exception))

    def test_missing_file(self) -> None:
        """Отсутствующий файл — ошибка."""
        with self.assertRaises(TestRepositoryError):
            load_repository(Path("/nonexistent/repo.txt"))

    def test_file_name_in_message(self) -> None:
        """Сообщение об ошибке формата содержит имя файла."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "repo.txt"
            path.write_text("A B\n", encoding="utf-8")
            with self.assertRaises(TestRepositoryError) as context:
                load_repository(path)
            self.assertIn("repo.txt", str(context.exception))


if __name__ == "__main__":
    unittest.main()

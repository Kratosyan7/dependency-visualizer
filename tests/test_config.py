"""Тесты чтения и проверки конфигурационного файла INI."""

import tempfile
import unittest
from pathlib import Path

from config import ConfigError, Settings, load_settings

MAVEN_INI = """
[package]
name = org.example:demo
version = 1.0.2

[repository]
url = https://repo1.maven.org/maven2
test_mode = no

[output]
image = graph.png
ascii_tree = yes
"""


class ConfigTestCase(unittest.TestCase):
    """Общая подготовка временного каталога."""

    def setUp(self) -> None:
        """Создаёт временный каталог на время теста."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def write(self, name: str, text: str) -> Path:
        """Записывает файл во временный каталог."""
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def problems(self, text: str) -> list[str]:
        """Возвращает ошибки проверки конфигурации с данным текстом."""
        path = self.write("config.ini", text)
        with self.assertRaises(ConfigError) as context:
            load_settings(path)
        return context.exception.problems

    def make_test_ini(self, name: str = "A", image: str = "g.png") -> str:
        """Формирует конфигурацию тестового режима."""
        repo = self.write("repo.txt", "A: B\n")
        return (
            f"[package]\nname = {name}\n"
            f"[repository]\nurl = {repo}\ntest_mode = true\n"
            f"[output]\nimage = {image}\n"
        )


class TestValidConfig(ConfigTestCase):
    """Корректные конфигурации."""

    def test_maven_settings(self) -> None:
        """Читает все параметры режима Maven."""
        settings = load_settings(self.write("c.ini", MAVEN_INI))
        self.assertEqual(settings.package, "org.example:demo")
        self.assertEqual(settings.version, "1.0.2")
        self.assertFalse(settings.test_mode)
        self.assertTrue(settings.ascii_tree)
        self.assertEqual(settings.image, Path("graph.png"))

    def test_items_are_key_value(self) -> None:
        """Выводит все шесть параметров в виде пар ключ-значение."""
        settings = load_settings(self.write("c.ini", MAVEN_INI))
        items = dict(settings.items())
        self.assertEqual(len(items), 7)
        self.assertEqual(items["repository.test_mode"], "false")
        self.assertEqual(items["output.ascii_tree"], "true")

    def test_test_mode_without_version(self) -> None:
        """В тестовом режиме версия не обязательна."""
        settings = load_settings(self.write("c.ini", self.make_test_ini()))
        self.assertIsInstance(settings, Settings)
        self.assertTrue(settings.test_mode)
        self.assertFalse(settings.ascii_tree)
        self.assertEqual(dict(settings.items())["package.version"],
                         "<не задано>")

    def test_file_url(self) -> None:
        """Схема file допускается для локального репозитория Maven."""
        text = MAVEN_INI.replace("https://repo1.maven.org/maven2",
                                 "file:///tmp/repo")
        settings = load_settings(self.write("c.ini", text))
        self.assertEqual(settings.repository, "file:///tmp/repo")


class TestFileErrors(ConfigTestCase):
    """Ошибки доступа к файлу и синтаксиса."""

    def test_missing_file(self) -> None:
        """Отсутствующий файл — ConfigError."""
        with self.assertRaises(ConfigError):
            load_settings(self.root / "missing.ini")

    def test_broken_syntax(self) -> None:
        """Строка без знака равенства — ошибка синтаксиса."""
        problems = self.problems("[package]\nname\n= x\n[[\n")
        self.assertIn("синтаксиса", problems[0])

    def test_not_utf8(self) -> None:
        """Файл не в UTF-8 отклоняется."""
        path = self.root / "c.ini"
        path.write_bytes("[package]\nname = Ж\n".encode("cp1251"))
        with self.assertRaises(ConfigError):
            load_settings(path)


class TestSchemaErrors(ConfigTestCase):
    """Неизвестные и пропущенные параметры."""

    def test_unknown_section_and_key(self) -> None:
        """Сообщает и о секции, и о ключе."""
        problems = self.problems(MAVEN_INI + "colour = red\n[x]\na = 1\n")
        self.assertIn("неизвестный ключ output.colour", problems)
        self.assertIn("неизвестная секция [x]", problems)

    def test_missing_required(self) -> None:
        """Перечисляет все пропущенные обязательные параметры."""
        problems = self.problems("[package]\nversion = 1\n")
        self.assertEqual(len(problems), 3)


class TestValueErrors(ConfigTestCase):
    """Ошибки значений каждого параметра."""

    def replace(self, old: str, new: str) -> list[str]:
        """Возвращает ошибки после замены фрагмента MAVEN_INI."""
        return self.problems(MAVEN_INI.replace(old, new))

    def test_bad_maven_name(self) -> None:
        """Имя без двоеточия отклоняется."""
        problems = self.replace("org.example:demo", "demo")
        self.assertIn("package.name", problems[0])

    def test_bad_version(self) -> None:
        """Версия с пробелом отклоняется."""
        problems = self.replace("1.0.2", "1.0 beta")
        self.assertIn("package.version", problems[0])

    def test_missing_version(self) -> None:
        """Без версии репозиторий Maven не анализируется."""
        problems = self.replace("version = 1.0.2", "version =")
        self.assertIn("обязательна", problems[0])

    def test_bad_scheme(self) -> None:
        """Неподдерживаемая схема URL отклоняется."""
        problems = self.replace("https://repo1", "ftp://repo1")
        self.assertIn("repository.url", problems[0])

    def test_missing_host(self) -> None:
        """URL без хоста отклоняется."""
        problems = self.replace("https://repo1.maven.org", "https://")
        self.assertIn("хост", problems[0])

    def test_bad_flags(self) -> None:
        """Нелогические значения флагов отклоняются оба."""
        text = MAVEN_INI.replace("= no", "= nope").replace("= yes", "= 2")
        self.assertEqual(len(self.problems(text)), 2)

    def test_bad_image_suffix(self) -> None:
        """Изображение должно быть PNG."""
        problems = self.replace("graph.png", "graph.svg")
        self.assertIn("output.image", problems[0])

    def test_image_is_directory(self) -> None:
        """Каталог вместо файла изображения отклоняется."""
        (self.root / "dir.png").mkdir()
        problems = self.problems(self.make_test_ini(
            image=str(self.root / "dir.png")))
        self.assertIn("каталогом", problems[0])

    def test_reverse_needs_test_mode(self) -> None:
        """Обратные зависимости только в тестовом режиме."""
        problems = self.problems(MAVEN_INI + "reverse = true\n")
        self.assertIn("output.reverse", problems[0])

    def test_reverse_in_test_mode(self) -> None:
        """В тестовом режиме reverse допускается."""
        text = self.make_test_ini() + "reverse = on\n"
        self.assertTrue(load_settings(self.write("c.ini", text)).reverse)

    def test_lowercase_test_name(self) -> None:
        """В тестовом режиме имя — большие латинские буквы."""
        problems = self.problems(self.make_test_ini(name="a"))
        self.assertIn("больших латинских", problems[0])

    def test_missing_test_repository(self) -> None:
        """Отсутствующий файл тестового репозитория отклоняется."""
        text = self.make_test_ini().replace(
            str(self.root / "repo.txt"), str(self.root / "none.txt"))
        problems = self.problems(text)
        self.assertIn("тестовый репозиторий", problems[0])


if __name__ == "__main__":
    unittest.main()

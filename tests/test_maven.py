"""Тесты разбора POM и получения прямых зависимостей Maven."""

import tempfile
import unittest
from pathlib import Path

from maven import (
    Coordinates,
    MavenError,
    Repository,
    fetch_bytes,
    interpolate,
    normalize_version,
    parse_pom,
    split_name,
)

BASE = "https://repo.test/maven2"
NAMESPACE = 'xmlns="http://maven.apache.org/POM/4.0.0"'


def pom(coordinates: str, body: str = "", parent: str = "") -> bytes:
    """Формирует текст POM; coordinates и parent — строки g:a:v."""
    group, artifact, version = coordinates.split(":")
    parent_xml = ""
    if parent:
        p_group, p_artifact, p_version = parent.split(":")
        parent_xml = (
            f"<parent><groupId>{p_group}</groupId>"
            f"<artifactId>{p_artifact}</artifactId>"
            f"<version>{p_version}</version></parent>"
        )
    return (
        f"<project {NAMESPACE}>{parent_xml}<groupId>{group}</groupId>"
        f"<artifactId>{artifact}</artifactId><version>{version}</version>"
        f"{body}</project>"
    ).encode()


def dep(coordinates: str, extra: str = "") -> str:
    """Формирует элемент dependency; версия может быть пустой."""
    group, artifact, version = coordinates.split(":")
    version_xml = f"<version>{version}</version>" if version else ""
    return (
        f"<dependency><groupId>{group}</groupId>"
        f"<artifactId>{artifact}</artifactId>{version_xml}{extra}"
        "</dependency>"
    )


class FakeRepository(Repository):
    """Репозиторий, в котором файлы POM лежат в словаре."""

    def __init__(self, files: dict[str, bytes]) -> None:
        """Сопоставляет координаты g:a:v с содержимым POM."""
        super().__init__(BASE, self.lookup)
        self.files = {
            self.pom_url(split_name(name.rsplit(":", 1)[0],
                                    name.rsplit(":", 1)[1])): data
            for name, data in files.items()
        }
        self.requests: list[str] = []

    def lookup(self, url: str) -> bytes:
        """Возвращает файл или имитирует ответ 404."""
        self.requests.append(url)
        if url not in self.files:
            raise MavenError(f"{url}: HTTP 404 Not Found")
        return self.files[url]


def names(repository: Repository, coordinates: str) -> list[str]:
    """Прямые зависимости пакета в виде строк g:a:v."""
    group, artifact, version = coordinates.split(":")
    found = repository.direct_dependencies(
        Coordinates(group, artifact, version))
    return [str(item.coordinates) for item in found]


class TestParsing(unittest.TestCase):
    """Разбор одного файла POM."""

    def test_url_layout(self) -> None:
        """Поле groupId превращается в путь из каталогов."""
        repository = Repository(BASE + "/")
        url = repository.pom_url(Coordinates("org.x.y", "lib", "1.0"))
        self.assertEqual(url, BASE + "/org/x/y/lib/1.0/lib-1.0.pom")

    def test_namespace_and_fields(self) -> None:
        """Читает зависимости из POM с пространством имён."""
        data = pom("g:a:1", "<dependencies>"
                   + dep("g:b:2", "<scope>test</scope>")
                   + dep("g:c:3", "<optional>true</optional>")
                   + "</dependencies>")
        parsed = parse_pom(data, "a.pom")
        self.assertEqual(parsed.coordinates, Coordinates("g", "a", "1"))
        self.assertEqual(parsed.dependencies[0].scope, "test")
        self.assertTrue(parsed.dependencies[1].optional)

    def test_inherited_group_and_version(self) -> None:
        """Поля groupId и версия наследуются от родителя."""
        data = (f"<project {NAMESPACE}><parent><groupId>p</groupId>"
                "<artifactId>parent</artifactId><version>9</version>"
                "</parent><artifactId>child</artifactId></project>")
        parsed = parse_pom(data.encode(), "child.pom")
        self.assertEqual(str(parsed.coordinates), "p:child:9")

    def test_bad_xml(self) -> None:
        """Некорректный XML — MavenError."""
        with self.assertRaises(MavenError):
            parse_pom(b"<project><broken></project>", "bad.pom")

    def test_not_project(self) -> None:
        """Корневой элемент должен быть project."""
        with self.assertRaises(MavenError):
            parse_pom(b"<html></html>", "page.html")

    def test_interpolate_nested(self) -> None:
        """Свойства подставляются рекурсивно, неизвестные сохраняются."""
        props = {"a": "${b}.0", "b": "1"}
        self.assertEqual(interpolate("v${a}-${x}", props), "v1.0-${x}")

    def test_version_ranges(self) -> None:
        """Из диапазона берётся включённая нижняя граница."""
        self.assertEqual(normalize_version("[1.2]"), "1.2")
        self.assertEqual(normalize_version("[1.0,2.0)"), "1.0")
        self.assertEqual(normalize_version("1.5"), "1.5")
        with self.assertRaises(MavenError):
            normalize_version("(,2.0]")


class TestDirectDependencies(unittest.TestCase):
    """Прямые зависимости с учётом наследования."""

    def test_simple(self) -> None:
        """Возвращает зависимости в порядке объявления."""
        repository = FakeRepository({"g:a:1": pom(
            "g:a:1",
            "<dependencies>" + dep("g:b:2") + dep("g:c:3") + "</dependencies>",
        )})
        self.assertEqual(names(repository, "g:a:1"), ["g:b:2", "g:c:3"])

    def test_properties_and_parent(self) -> None:
        """Версия из свойства родителя и ${project.version}."""
        repository = FakeRepository({
            "g:parent:5": pom("g:parent:5",
                              "<properties><lib.v>7.1</lib.v></properties>"
                              "<dependencies>" + dep("g:log:1")
                              + "</dependencies>"),
            "g:a:1": pom("g:a:1", "<dependencies>"
                         + dep("x:lib:${lib.v}")
                         + dep("g:sib:${project.version}")
                         + "</dependencies>", parent="g:parent:5"),
        })
        self.assertEqual(names(repository, "g:a:1"),
                         ["x:lib:7.1", "g:sib:1", "g:log:1"])

    def test_dependency_management(self) -> None:
        """Версия и scope берутся из dependencyManagement родителя."""
        managed = ("<dependencyManagement><dependencies>"
                   + dep("x:lib:3.3", "<scope>runtime</scope>")
                   + "</dependencies></dependencyManagement>")
        repository = FakeRepository({
            "g:parent:5": pom("g:parent:5", managed),
            "g:a:1": pom("g:a:1", "<dependencies>" + dep("x:lib:")
                         + "</dependencies>", parent="g:parent:5"),
        })
        found = repository.direct_dependencies(Coordinates("g", "a", "1"))
        self.assertEqual(found[0].version, "3.3")
        self.assertEqual(found[0].scope, "runtime")

    def test_bom_import(self) -> None:
        """Версии из импортированного BOM."""
        bom = ("<dependencyManagement><dependencies>"
               + dep("b:bom:2", "<type>pom</type><scope>import</scope>")
               + "</dependencies></dependencyManagement>")
        repository = FakeRepository({
            "b:bom:2": pom("b:bom:2", "<dependencyManagement><dependencies>"
                           + dep("x:lib:4") + "</dependencies>"
                           "</dependencyManagement>"),
            "g:a:1": pom("g:a:1", bom + "<dependencies>" + dep("x:lib:")
                         + "</dependencies>"),
        })
        self.assertEqual(names(repository, "g:a:1"), ["x:lib:4"])

    def test_unknown_version(self) -> None:
        """Зависимость без версии и без управления — ошибка."""
        repository = FakeRepository({"g:a:1": pom(
            "g:a:1", "<dependencies>" + dep("x:lib:") + "</dependencies>")})
        with self.assertRaises(MavenError):
            names(repository, "g:a:1")

    def test_missing_package(self) -> None:
        """Отсутствующий POM — MavenError."""
        with self.assertRaises(MavenError):
            names(FakeRepository({}), "g:none:1")

    def test_pom_is_cached(self) -> None:
        """Повторный запрос не загружает POM заново."""
        repository = FakeRepository({"g:a:1": pom("g:a:1")})
        names(repository, "g:a:1")
        names(repository, "g:a:1")
        self.assertEqual(len(repository.requests), 1)


class TestFetch(unittest.TestCase):
    """Загрузка файлов по URL."""

    def test_file_url(self) -> None:
        """Репозиторий может быть локальным каталогом (схема file)."""
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "g" / "a" / "1"
            folder.mkdir(parents=True)
            (folder / "a-1.pom").write_bytes(pom("g:a:1", "<dependencies>"
                                                 + dep("g:b:2")
                                                 + "</dependencies>"))
            repository = Repository(Path(temp).as_uri())
            self.assertEqual(names(repository, "g:a:1"), ["g:b:2"])

    def test_file_missing(self) -> None:
        """Отсутствующий локальный файл — MavenError."""
        with self.assertRaises(MavenError):
            fetch_bytes("file:///nonexistent/dir/file.pom")


if __name__ == "__main__":
    unittest.main()

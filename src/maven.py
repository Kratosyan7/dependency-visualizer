"""Получение сведений о зависимостях пакетов из репозитория Maven.

Менеджеры пакетов и сторонние библиотеки не используются: файлы POM
скачиваются по стандартной раскладке репозитория Maven
(groupId/artifactId/version/artifactId-version.pom) и разбираются
модулем xml.etree. Поддерживаются наследование от родительских POM,
свойства ${...}, раздел dependencyManagement и импорт BOM.
"""

import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from xml.etree import ElementTree

from graph import SourceError

TIMEOUT = 30
USER_AGENT = "dependency-visualizer/1.0 (study project)"
MAX_INTERPOLATION_PASSES = 10
MAX_PARENT_DEPTH = 32
PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")
DEFAULT_SCOPE = "compile"
IMPORT_SCOPE = "import"
RANGE_START = "[("
RANGE_END = "])"
CLASSPATH_SCOPES = ("compile", "runtime")


class MavenError(SourceError):
    """Ошибка получения или разбора POM."""


@dataclass(frozen=True)
class Coordinates:
    """Координаты пакета: groupId, artifactId и версия."""

    group: str
    artifact: str
    version: str

    @property
    def key(self) -> str:
        """Имя пакета без версии."""
        return f"{self.group}:{self.artifact}"

    def __str__(self) -> str:
        """Полное имя пакета groupId:artifactId:version."""
        return f"{self.key}:{self.version}"


@dataclass(frozen=True)
class Dependency:
    """Объявление зависимости в POM."""

    group: str
    artifact: str
    version: str = ""
    scope: str = ""
    optional: bool = False

    @property
    def key(self) -> str:
        """Имя зависимости без версии."""
        return f"{self.group}:{self.artifact}"

    @property
    def coordinates(self) -> Coordinates:
        """Координаты зависимости."""
        return Coordinates(self.group, self.artifact, self.version)


@dataclass
class Pom:
    """Содержимое одного файла POM без учёта наследования."""

    coordinates: Coordinates
    parent: Coordinates | None
    properties: dict[str, str]
    managed: list[Dependency]
    dependencies: list[Dependency]


@dataclass
class EffectivePom:
    """POM с учётом родителей, свойств и dependencyManagement."""

    coordinates: Coordinates
    managed: dict[str, Dependency]
    dependencies: list[Dependency]


def split_name(name: str, version: str) -> Coordinates:
    """Превращает имя groupId:artifactId и версию в координаты."""
    group, artifact = name.split(":")
    return Coordinates(group, artifact, version)


def fetch_bytes(url: str) -> bytes:
    """Скачивает файл по URL (поддерживаются http, https и file)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise MavenError(f"{url}: HTTP {error.code} {error.reason}") from error
    except (urllib.error.URLError, OSError) as error:
        raise MavenError(f"{url}: {error}") from error


def strip_namespaces(root: ElementTree.Element) -> None:
    """Убирает пространство имён POM из тегов для простого поиска."""
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]


def text_of(element: ElementTree.Element | None, path: str) -> str:
    """Текст дочернего элемента или пустая строка."""
    if element is None:
        return ""
    return (element.findtext(path) or "").strip()


def read_dependencies(
    container: ElementTree.Element | None,
) -> list[Dependency]:
    """Читает элементы dependency из раздела dependencies."""
    if container is None:
        return []
    return [
        Dependency(
            group=text_of(item, "groupId"),
            artifact=text_of(item, "artifactId"),
            version=text_of(item, "version"),
            scope=text_of(item, "scope"),
            optional=text_of(item, "optional").lower() == "true",
        )
        for item in container.findall("dependency")
    ]


def read_parent(element: ElementTree.Element | None) -> Coordinates | None:
    """Читает ссылку на родительский POM."""
    if element is None:
        return None
    return Coordinates(
        text_of(element, "groupId"),
        text_of(element, "artifactId"),
        text_of(element, "version"),
    )


def parse_pom(data: bytes, source: str) -> Pom:
    """Разбирает содержимое файла POM."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise MavenError(f"{source}: некорректный XML: {error}") from error
    strip_namespaces(root)
    if root.tag != "project":
        raise MavenError(f"{source}: корневой элемент не project")
    parent = read_parent(root.find("parent"))
    inherited = parent or Coordinates("", "", "")
    properties = root.find("properties")
    return Pom(
        coordinates=Coordinates(
            text_of(root, "groupId") or inherited.group,
            text_of(root, "artifactId"),
            text_of(root, "version") or inherited.version,
        ),
        parent=parent,
        properties={
            item.tag: (item.text or "").strip()
            for item in (properties if properties is not None else [])
            if isinstance(item.tag, str)
        },
        managed=read_dependencies(root.find("dependencyManagement/"
                                            "dependencies")),
        dependencies=read_dependencies(root.find("dependencies")),
    )


def interpolate(value: str, properties: dict[str, str]) -> str:
    """Подставляет значения свойств ${...}; неизвестные остаются как есть."""
    for _ in range(MAX_INTERPOLATION_PASSES):
        result = PLACEHOLDER.sub(
            lambda match: properties.get(match.group(1), match.group(0)),
            value,
        )
        if result == value:
            break
        value = result
    return value


def project_properties(chain: list[Pom]) -> dict[str, str]:
    """Свойства с учётом наследования и встроенные свойства project.*."""
    properties: dict[str, str] = {}
    for pom in chain:
        properties.update(pom.properties)
    project = chain[-1].coordinates
    for prefix in ("project", "pom"):
        properties[f"{prefix}.groupId"] = project.group
        properties[f"{prefix}.artifactId"] = project.artifact
        properties[f"{prefix}.version"] = project.version
    parent = chain[-1].parent
    if parent is not None:
        properties["project.parent.groupId"] = parent.group
        properties["project.parent.artifactId"] = parent.artifact
        properties["project.parent.version"] = parent.version
    return properties


def normalize_version(version: str) -> str:
    """Выбирает конкретную версию из диапазона вида [1.0,2.0)."""
    if not version or version[0] not in RANGE_START:
        return version
    bounds = version.strip(RANGE_START + RANGE_END).split(",")
    lower = bounds[0].strip()
    if version[0] == "[" and lower:
        return lower
    raise MavenError(f"диапазон версий {version} не поддерживается")


def expand(dependency: Dependency, properties: dict[str, str]) -> Dependency:
    """Подставляет свойства во все поля зависимости."""
    return replace(
        dependency,
        group=interpolate(dependency.group, properties),
        artifact=interpolate(dependency.artifact, properties),
        version=interpolate(dependency.version, properties),
        scope=interpolate(dependency.scope, properties),
    )


def apply_management(
    dependency: Dependency,
    managed: dict[str, Dependency],
) -> Dependency:
    """Дополняет версию и scope из dependencyManagement."""
    rule = managed.get(dependency.key)
    version = dependency.version or (rule.version if rule else "")
    scope = dependency.scope or (rule.scope if rule else "")
    if not version:
        raise MavenError(f"не удалось определить версию {dependency.key}")
    return replace(
        dependency,
        version=normalize_version(version),
        scope=scope or DEFAULT_SCOPE,
    )


class Repository:
    """Репозиторий Maven с кэшем загруженных POM."""

    def __init__(
        self,
        base_url: str,
        fetch: Callable[[str], bytes] = fetch_bytes,
    ) -> None:
        """Запоминает адрес репозитория и функцию загрузки файлов."""
        self.base_url = base_url.rstrip("/")
        self.fetch = fetch
        self.raw_cache: dict[Coordinates, Pom] = {}
        self.effective_cache: dict[Coordinates, EffectivePom] = {}
        self.loading: set[Coordinates] = set()

    def pom_url(self, coordinates: Coordinates) -> str:
        """Адрес файла POM по стандартной раскладке Maven."""
        group_path = coordinates.group.replace(".", "/")
        name = f"{coordinates.artifact}-{coordinates.version}.pom"
        return "/".join((self.base_url, group_path, coordinates.artifact,
                         coordinates.version, name))

    def raw_pom(self, coordinates: Coordinates) -> Pom:
        """Загружает и разбирает один POM (с кэшем)."""
        if coordinates not in self.raw_cache:
            url = self.pom_url(coordinates)
            self.raw_cache[coordinates] = parse_pom(self.fetch(url), url)
        return self.raw_cache[coordinates]

    def lineage(self, coordinates: Coordinates) -> list[Pom]:
        """Цепочка POM от самого верхнего родителя до заданного пакета."""
        chain: list[Pom] = []
        current: Coordinates | None = coordinates
        while current is not None:
            if len(chain) >= MAX_PARENT_DEPTH:
                raise MavenError(f"{coordinates}: слишком длинная цепочка "
                                 "родительских POM")
            pom = self.raw_pom(current)
            chain.append(pom)
            current = pom.parent
        chain.reverse()
        return chain

    def merge_managed(
        self,
        chain: list[Pom],
        properties: dict[str, str],
    ) -> dict[str, Dependency]:
        """Собирает dependencyManagement с учётом родителей и BOM."""
        managed: dict[str, Dependency] = {}
        imports: list[Dependency] = []
        for pom in chain:
            for rule in pom.managed:
                rule = expand(rule, properties)
                if rule.scope == IMPORT_SCOPE:
                    imports.append(rule)
                else:
                    managed[rule.key] = rule
        for bom in imports:
            for key, rule in self.effective(bom.coordinates).managed.items():
                managed.setdefault(key, rule)
        return managed

    def effective(self, coordinates: Coordinates) -> EffectivePom:
        """Эффективный POM пакета (с кэшем и защитой от циклов BOM)."""
        if coordinates in self.effective_cache:
            return self.effective_cache[coordinates]
        if coordinates in self.loading:
            raise MavenError(f"{coordinates}: циклический импорт BOM")
        self.loading.add(coordinates)
        try:
            chain = self.lineage(coordinates)
            properties = project_properties(chain)
            managed = self.merge_managed(chain, properties)
            declared: dict[str, Dependency] = {}
            for pom in reversed(chain):
                for item in pom.dependencies:
                    item = expand(item, properties)
                    declared.setdefault(item.key, item)
        finally:
            self.loading.discard(coordinates)
        result = EffectivePom(coordinates, managed, list(declared.values()))
        self.effective_cache[coordinates] = result
        return result

    def direct_dependencies(
        self,
        coordinates: Coordinates,
    ) -> list[Dependency]:
        """Прямые зависимости пакета с определёнными версиями и scope."""
        pom = self.effective(coordinates)
        return [
            apply_management(item, pom.managed) for item in pom.dependencies
        ]


def parse_coordinates(name: str) -> Coordinates:
    """Разбирает полное имя узла графа groupId:artifactId:version."""
    group, artifact, version = name.split(":")
    return Coordinates(group, artifact, version)


def is_inherited(dependency: Dependency, transitive: bool) -> bool:
    """Попадает ли зависимость в граф времени выполнения.

    Учитываются scope compile и runtime; необязательные (optional)
    зависимости учитываются только у исходного пакета, как в Maven.
    """
    if dependency.scope not in CLASSPATH_SCOPES:
        return False
    return not (transitive and dependency.optional)


class Resolver:
    """Источник рёбер графа для обхода BFS по репозиторию Maven.

    Версия каждого пакета выбирается по правилу Maven «ближайший
    побеждает»: BFS встречает пакеты в порядке глубины, поэтому первая
    увиденная версия groupId:artifactId закрепляется за ним. Для
    транзитивных зависимостей действует dependencyManagement исходного
    пакета.
    """

    def __init__(self, repository: Repository, root: Coordinates) -> None:
        """Запоминает репозиторий и исходный пакет."""
        self.repository = repository
        self.root = root
        self.chosen: dict[str, str] = {root.key: root.version}

    def pick_version(self, dependency: Dependency, transitive: bool) -> str:
        """Выбирает версию зависимости с учётом уже выбранных."""
        if dependency.key not in self.chosen:
            version = dependency.version
            if transitive:
                managed = self.repository.effective(self.root).managed
                rule = managed.get(dependency.key)
                version = rule.version if rule else version
            self.chosen[dependency.key] = version
        return self.chosen[dependency.key]

    def neighbours(self, name: str) -> list[str]:
        """Прямые зависимости узла графа в виде полных имён."""
        coordinates = parse_coordinates(name)
        transitive = coordinates != self.root
        result = []
        for item in self.repository.direct_dependencies(coordinates):
            if is_inherited(item, transitive):
                version = self.pick_version(item, transitive)
                result.append(f"{item.key}:{version}")
        return list(dict.fromkeys(result))

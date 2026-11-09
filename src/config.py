"""Чтение и проверка конфигурационного файла INI.

Все настраиваемые пользователем параметры хранятся в одном файле INI
с тремя секциями. SCHEMA перечисляет допустимые секции и ключи,
REQUIRED — обязательные ключи. Проверка собирает сразу все ошибки,
чтобы пользователь мог исправить файл за один раз.
"""

import configparser
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = {
    "package": ("name", "version"),
    "repository": ("url", "test_mode"),
    "output": ("image", "ascii_tree"),
}
REQUIRED = (
    ("package", "name"),
    ("repository", "url"),
    ("output", "image"),
)

MAVEN_NAME = re.compile(r"[\w.\-]+:[\w.\-]+", re.ASCII)
TEST_NAME = re.compile(r"[A-Z]+")
VERSION = re.compile(r"[\w.\-+]+", re.ASCII)
URL_SCHEMES = ("http", "https", "file")
NETWORK_SCHEMES = ("http", "https")
IMAGE_SUFFIX = ".png"
NOT_SET = "<не задано>"


class ConfigError(Exception):
    """Ошибка конфигурации; problems содержит все найденные нарушения."""

    def __init__(self, problems: list[str]) -> None:
        """Сохраняет список нарушений."""
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Settings:
    """Проверенные параметры запуска."""

    package: str
    version: str
    repository: str
    test_mode: bool
    image: Path
    ascii_tree: bool

    def items(self) -> list[tuple[str, str]]:
        """Возвращает параметры в виде пар «ключ — значение»."""
        return [
            ("package.name", self.package),
            ("package.version", self.version or NOT_SET),
            ("repository.url", self.repository),
            ("repository.test_mode", show_flag(self.test_mode)),
            ("output.image", str(self.image)),
            ("output.ascii_tree", show_flag(self.ascii_tree)),
        ]


def show_flag(value: bool) -> str:
    """Представляет логическое значение так же, как в файле INI."""
    return "true" if value else "false"


def read_ini(path: Path) -> configparser.ConfigParser:
    """Читает файл INI; ошибки доступа и синтаксиса — ConfigError."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except OSError as error:
        raise ConfigError([f"не удалось прочитать {path}: {error}"]) from error
    except UnicodeDecodeError as error:
        raise ConfigError([f"{path}: файл не в кодировке UTF-8"]) from error
    except configparser.Error as error:
        message = " ".join(str(error).split())
        raise ConfigError([f"ошибка синтаксиса INI: {message}"]) from error
    return parser


def check_schema(parser: configparser.ConfigParser) -> list[str]:
    """Находит неизвестные секции и ключи и пропущенные обязательные."""
    problems = []
    for section in parser.sections():
        if section not in SCHEMA:
            problems.append(f"неизвестная секция [{section}]")
            continue
        for key in parser.options(section):
            if key not in SCHEMA[section]:
                problems.append(f"неизвестный ключ {section}.{key}")
    for section, key in REQUIRED:
        if not get_text(parser, section, key):
            problems.append(f"не задан обязательный параметр {section}.{key}")
    return problems


def get_text(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
) -> str:
    """Возвращает значение ключа без пробелов по краям или пустую строку."""
    return parser.get(section, key, fallback="").strip()


def get_flag(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    problems: list[str],
) -> bool:
    """Читает логический параметр; по умолчанию false."""
    raw = get_text(parser, section, key)
    if not raw:
        return False
    flag = parser.BOOLEAN_STATES.get(raw.lower())
    if flag is None:
        problems.append(
            f"{section}.{key}: ожидается true или false, получено {raw!r}"
        )
        return False
    return flag


def check_name(name: str, test_mode: bool) -> str | None:
    """Проверяет имя пакета для выбранного режима."""
    if test_mode and not TEST_NAME.fullmatch(name):
        return (
            f"package.name: в тестовом режиме имя пакета состоит из "
            f"больших латинских букв, получено {name!r}"
        )
    if not test_mode and not MAVEN_NAME.fullmatch(name):
        return (
            f"package.name: ожидается groupId:artifactId, "
            f"получено {name!r}"
        )
    return None


def check_version(version: str, test_mode: bool) -> str | None:
    """Проверяет версию: обязательна вне тестового режима."""
    if not version:
        if test_mode:
            return None
        return "package.version: версия обязательна для репозитория Maven"
    if not VERSION.fullmatch(version):
        return f"package.version: недопустимая версия {version!r}"
    return None


def check_repository(url: str, test_mode: bool) -> str | None:
    """Проверяет URL репозитория или путь к файлу тестового репозитория."""
    if test_mode:
        if not Path(url).is_file():
            return f"repository.url: не найден тестовый репозиторий {url!r}"
        return None
    parts = urlparse(url)
    if parts.scheme not in URL_SCHEMES:
        return (
            f"repository.url: ожидается URL со схемой "
            f"{', '.join(URL_SCHEMES)}, получено {url!r}"
        )
    if parts.scheme in NETWORK_SCHEMES and not parts.netloc:
        return f"repository.url: в URL {url!r} не указан хост"
    return None


def check_image(image: str) -> str | None:
    """Проверяет имя файла изображения графа."""
    path = Path(image)
    if path.suffix.lower() != IMAGE_SUFFIX:
        return (
            f"output.image: ожидается файл с расширением {IMAGE_SUFFIX}, "
            f"получено {image!r}"
        )
    if path.is_dir():
        return f"output.image: {image!r} является каталогом"
    return None


def load_settings(path: Path) -> Settings:
    """Читает и проверяет конфигурацию; ошибки — ConfigError."""
    parser = read_ini(path)
    problems = check_schema(parser)
    if problems:
        raise ConfigError(problems)
    test_mode = get_flag(parser, "repository", "test_mode", problems)
    settings = Settings(
        package=get_text(parser, "package", "name"),
        version=get_text(parser, "package", "version"),
        repository=get_text(parser, "repository", "url"),
        test_mode=test_mode,
        image=Path(get_text(parser, "output", "image")),
        ascii_tree=get_flag(parser, "output", "ascii_tree", problems),
    )
    checks = (
        check_name(settings.package, test_mode),
        check_version(settings.version, test_mode),
        check_repository(settings.repository, test_mode),
        check_image(str(settings.image)),
    )
    problems.extend(problem for problem in checks if problem)
    if problems:
        raise ConfigError(problems)
    return settings

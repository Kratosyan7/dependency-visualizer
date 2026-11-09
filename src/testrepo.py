"""Тестовый репозиторий: граф пакетов, описанный в текстовом файле.

Формат файла — по одному пакету в строке:

    ПАКЕТ: ЗАВИСИМОСТЬ ЗАВИСИМОСТЬ ...

Имена пакетов состоят из больших латинских букв. Пустые строки и
текст после # игнорируются. Пакет, упомянутый только как зависимость,
считается пакетом без зависимостей.
"""

import re
from pathlib import Path

NAME = re.compile(r"[A-Z]+")
COMMENT = "#"
SEPARATOR = ":"


class TestRepositoryError(Exception):
    """Ошибка чтения или формата файла тестового репозитория."""


def check_names(names: list[str], number: int) -> None:
    """Проверяет, что все имена состоят из больших латинских букв."""
    for name in names:
        if not NAME.fullmatch(name):
            raise TestRepositoryError(
                f"строка {number}: недопустимое имя пакета {name!r}"
            )


def parse_line(line: str, number: int) -> tuple[str, list[str]] | None:
    """Разбирает строку; для пустой строки или комментария — None."""
    line = line.split(COMMENT, 1)[0].strip()
    if not line:
        return None
    if SEPARATOR not in line:
        raise TestRepositoryError(
            f"строка {number}: ожидается «ПАКЕТ: ЗАВИСИМОСТИ», "
            f"получено {line!r}"
        )
    name, rest = line.split(SEPARATOR, 1)
    name = name.strip()
    children = rest.split()
    check_names([name, *children], number)
    return name, children


def parse_repository(text: str) -> dict[str, list[str]]:
    """Разбирает текст тестового репозитория в списки смежности."""
    packages: dict[str, list[str]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        parsed = parse_line(line, number)
        if parsed is None:
            continue
        name, children = parsed
        if name in packages:
            raise TestRepositoryError(
                f"строка {number}: пакет {name} описан повторно"
            )
        packages[name] = list(dict.fromkeys(children))
    return packages


def load_repository(path: Path) -> dict[str, list[str]]:
    """Читает файл тестового репозитория."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        message = f"не удалось прочитать {path}: {error}"
        raise TestRepositoryError(message) from error
    try:
        return parse_repository(text)
    except TestRepositoryError as error:
        raise TestRepositoryError(f"{path}: {error}") from error

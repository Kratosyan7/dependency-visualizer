"""Точка входа: визуализатор графа зависимостей пакетов Maven.

Единственный параметр командной строки — путь к конфигурационному
файлу INI (по умолчанию DEFAULT_CONFIG). Коды возврата заданы
константами EXIT_*.
"""

import argparse
import sys
from pathlib import Path

from config import ConfigError, Settings, load_settings
from maven import MavenError, Repository, split_name

DESCRIPTION = "Визуализатор графа зависимостей пакетов Maven"
DEFAULT_CONFIG = Path("config/default.ini")
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_DATA = 3


def build_parser() -> argparse.ArgumentParser:
    """Описывает параметры командной строки."""
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"конфигурационный файл INI (по умолчанию {DEFAULT_CONFIG})",
    )
    return parser


def report_problems(title: str, problems: list[str]) -> None:
    """Печатает список ошибок в stderr."""
    print(f"Ошибка: {title}", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)


def show_direct_dependencies(settings: Settings) -> None:
    """Печатает прямые зависимости пакета из репозитория Maven."""
    package = split_name(settings.package, settings.version)
    repository = Repository(settings.repository)
    dependencies = repository.direct_dependencies(package)
    print(f"Прямые зависимости {package}: {len(dependencies)}")
    for item in dependencies:
        flags = item.scope + (", optional" if item.optional else "")
        print(f"  {item.coordinates} ({flags})")


def main(argv: list[str] | None = None) -> int:
    """Читает конфигурацию и выводит прямые зависимости пакета."""
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
    except ConfigError as error:
        report_problems(f"конфигурация {args.config}", error.problems)
        return EXIT_CONFIG
    if settings.test_mode:
        report_problems("тестовый режим", ["будет поддержан на этапе 3"])
        return EXIT_CONFIG
    try:
        show_direct_dependencies(settings)
    except MavenError as error:
        report_problems("получение зависимостей", [str(error)])
        return EXIT_DATA
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

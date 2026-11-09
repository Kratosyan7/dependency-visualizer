"""Точка входа: визуализатор графа зависимостей пакетов Maven.

Единственный параметр командной строки — путь к конфигурационному
файлу INI (по умолчанию DEFAULT_CONFIG). Коды возврата заданы
константами EXIT_*.
"""

import argparse
import sys
from pathlib import Path

from config import ConfigError, Settings, load_settings
from graph import Graph, bfs, format_graph
from maven import MavenError, Repository, Resolver, split_name
from testrepo import TestRepositoryError, load_repository

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


def build_test_graph(settings: Settings) -> Graph:
    """Строит граф по файлу тестового репозитория."""
    packages = load_repository(Path(settings.repository))
    known = set(packages).union(*packages.values())
    if settings.package not in known:
        raise TestRepositoryError(
            f"пакет {settings.package} не описан в {settings.repository}"
        )
    return bfs(settings.package, lambda name: packages.get(name, []))


def build_maven_graph(settings: Settings) -> Graph:
    """Строит граф по репозиторию Maven.

    POM исходного пакета загружается заранее: если его нет, работа
    прерывается, а ошибки остальных пакетов попадают в Graph.errors.
    """
    root = split_name(settings.package, settings.version)
    resolver = Resolver(Repository(settings.repository), root)
    resolver.repository.effective(root)
    return bfs(str(root), resolver.neighbours)


def build_graph(settings: Settings) -> Graph:
    """Строит граф зависимостей из источника, заданного настройками."""
    if settings.test_mode:
        return build_test_graph(settings)
    return build_maven_graph(settings)


def main(argv: list[str] | None = None) -> int:
    """Читает конфигурацию, строит и выводит граф зависимостей."""
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
    except ConfigError as error:
        report_problems(f"конфигурация {args.config}", error.problems)
        return EXIT_CONFIG
    try:
        graph = build_graph(settings)
    except (MavenError, TestRepositoryError) as error:
        report_problems("получение зависимостей", [str(error)])
        return EXIT_DATA
    print("\n".join(format_graph(graph)))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

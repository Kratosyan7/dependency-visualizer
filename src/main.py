"""Точка входа: визуализатор графа зависимостей пакетов Maven.

Единственный параметр командной строки — путь к конфигурационному
файлу INI (по умолчанию DEFAULT_CONFIG). Коды возврата заданы
константами EXIT_*.
"""

import argparse
import sys
from pathlib import Path

from config import ConfigError, Settings, load_settings
from graph import Graph, bfs, format_graph, format_reverse, reverse_bfs
from maven import MavenError, Repository, Resolver, split_name
from render import RenderError, ascii_tree, save_png, to_plantuml
from testrepo import TestRepositoryError, load_repository

DESCRIPTION = "Визуализатор графа зависимостей пакетов Maven"
DEFAULT_CONFIG = Path("config/default.ini")
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_DATA = 3
EXIT_RENDER = 4


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
    """Строит граф тестового репозитория (прямой или обратный)."""
    packages = load_repository(Path(settings.repository))
    known = set(packages).union(*packages.values())
    if settings.package not in known:
        raise TestRepositoryError(
            f"пакет {settings.package} не описан в {settings.repository}"
        )
    if settings.reverse:
        return reverse_bfs(settings.package, packages)
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


def visualize(settings: Settings, graph: Graph) -> None:
    """Сохраняет PlantUML и PNG, при необходимости печатает ASCII-дерево.

    Текст PlantUML записывается рядом с изображением (расширение .puml).
    """
    kind = "Обратные зависимости" if settings.reverse else "Зависимости"
    text = to_plantuml(graph, f"{kind} {graph.root}")
    image = settings.image
    puml = image.with_suffix(".puml")
    try:
        image.parent.mkdir(parents=True, exist_ok=True)
        puml.write_text(text, encoding="utf-8")
    except OSError as error:
        raise RenderError(f"не удалось записать {puml}: {error}") from error
    print(f"Текст PlantUML: {puml}")
    if settings.ascii_tree:
        print(f"{kind} в виде ASCII-дерева:")
        print("\n".join(ascii_tree(graph)))
    save_png(text, image)
    print(f"Изображение PNG: {image}")


def main(argv: list[str] | None = None) -> int:
    """Читает конфигурацию, строит, выводит и визуализирует граф."""
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
    formatter = format_reverse if settings.reverse else format_graph
    print("\n".join(formatter(graph)))
    try:
        visualize(settings, graph)
    except RenderError as error:
        report_problems("визуализация", [str(error)])
        return EXIT_RENDER
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

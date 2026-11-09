"""Точка входа: визуализатор графа зависимостей пакетов Maven.

Единственный параметр командной строки — путь к конфигурационному
файлу INI (по умолчанию DEFAULT_CONFIG). Коды возврата заданы
константами EXIT_*.
"""

import argparse
import sys
from pathlib import Path

from config import ConfigError, load_settings

DESCRIPTION = "Визуализатор графа зависимостей пакетов Maven"
DEFAULT_CONFIG = Path("config/default.ini")
EXIT_OK = 0
EXIT_CONFIG = 2


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


def main(argv: list[str] | None = None) -> int:
    """Читает конфигурацию и выводит параметры в формате ключ-значение."""
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
    except ConfigError as error:
        report_problems(f"конфигурация {args.config}", error.problems)
        return EXIT_CONFIG
    for key, value in settings.items():
        print(f"{key} = {value}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

#!/bin/sh
# Запуск инструмента визуализации зависимостей и его тестов.
#
#   ./run.sh                  запуск с config/default.ini
#   ./run.sh run [параметры]  запуск с указанным файлом конфигурации
#   ./run.sh test             запуск тестов
#
# Интерпретатор переопределяется переменной PYTHON.
set -eu

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON=${PYTHON:-python3}
export PYTHONPATH="$ROOT_DIR/src"

COMMAND=${1:-run}
if [ $# -gt 0 ]; then
    shift
fi

case "$COMMAND" in
    run)
        exec "$PYTHON" "$ROOT_DIR/src/main.py" "$@"
        ;;
    test)
        exec "$PYTHON" -m unittest discover -s "$ROOT_DIR/tests" -v "$@"
        ;;
    *)
        echo "Использование: $0 [run|test] [параметры]" >&2
        exit 1
        ;;
esac

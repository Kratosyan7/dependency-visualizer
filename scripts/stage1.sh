#!/bin/sh
# Этап 1: вывод параметров и обработка ошибок конфигурации.
set -u
cd "$(dirname "$0")/.."

for config in config/default.ini config/test_basic.ini \
        config/нет_такого.ini config/errors/*.ini; do
    echo "=== $config ==="
    ./run.sh run "$config" || echo "код возврата: $?"
    echo
done

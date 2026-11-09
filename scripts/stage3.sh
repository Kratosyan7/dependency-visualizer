#!/bin/sh
# Этап 3: транзитивный граф (BFS), циклы и тестовые репозитории.
set -u
cd "$(dirname "$0")/.."

for config in config/test/*.ini config/maven/spring-context.ini; do
    echo "=== $config ==="
    ./run.sh run "$config" || echo "код возврата: $?"
    echo
done

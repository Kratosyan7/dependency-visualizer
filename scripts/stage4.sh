#!/bin/sh
# Этап 4: обратные зависимости в тестовых репозиториях.
set -u
cd "$(dirname "$0")/.."

for config in config/reverse/*.ini config/errors/reverse_maven.ini; do
    echo "=== $config ==="
    ./run.sh run "$config" || echo "код возврата: $?"
    echo
done

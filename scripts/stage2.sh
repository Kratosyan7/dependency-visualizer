#!/bin/sh
# Этап 2: прямые зависимости пакетов из центрального репозитория Maven.
set -u
cd "$(dirname "$0")/.."

for config in config/default.ini config/maven/*.ini \
        config/errors/maven_*.ini; do
    echo "=== $config ==="
    ./run.sh run "$config" || echo "код возврата: $?"
    echo
done

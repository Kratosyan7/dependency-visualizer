#!/bin/sh
# Этап 5: PlantUML, PNG и ASCII-дерево для трёх пакетов Maven
# и тестового репозитория. Результаты сохраняются в каталог out/.
set -u
cd "$(dirname "$0")/.."

for config in config/default.ini config/maven/okhttp.ini \
        config/maven/spring-context.ini config/test/large.ini \
        config/reverse/large_log.ini; do
    echo "=== $config ==="
    ./run.sh run "$config" || echo "код возврата: $?"
    echo
done

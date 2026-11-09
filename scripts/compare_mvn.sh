#!/bin/sh
# Этап 5: вывод штатного инструмента Maven для сравнения.
# Требуются Maven 3 и Java. Для каждого из трёх пакетов скачивается
# его POM и выполняется mvn dependency:tree по нему (как по проекту),
# результат сохраняется в docs/mvn/<artifactId>.txt.
set -eu
cd "$(dirname "$0")/.."
MVN=${MVN:-mvn}
REPO=https://repo1.maven.org/maven2
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p docs/mvn

for coords in \
        com.fasterxml.jackson.core:jackson-databind:2.16.0 \
        com.squareup.okhttp3:okhttp:4.12.0 \
        org.springframework:spring-context:6.1.0; do
    group=$(echo "$coords" | cut -d: -f1)
    artifact=$(echo "$coords" | cut -d: -f2)
    version=$(echo "$coords" | cut -d: -f3)
    path=$(echo "$group" | tr . /)/$artifact/$version
    mkdir -p "$WORK/$artifact"
    curl -sSf "$REPO/$path/$artifact-$version.pom" \
        -o "$WORK/$artifact/pom.xml"
    out=$(pwd)/docs/mvn/$artifact.txt
    (cd "$WORK/$artifact" && "$MVN" -B -q \
        org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree \
        -Dscope=runtime -DoutputFile="$out")
    echo "=== $coords ==="
    cat "$out"
done

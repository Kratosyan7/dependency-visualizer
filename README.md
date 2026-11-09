# Визуализатор графа зависимостей — вариант 14

Практическая работа № 2 по конфигурационному управлению, ИКБО-41-25.
Инструмент строит граф зависимостей пакетов Maven без использования
менеджеров пакетов и сторонних библиотек.

Требуется Python 3.11+. Используется только стандартная библиотека,
сборка не требуется.

## Запуск и тесты

Linux/macOS:

```sh
sh run.sh run config/default.ini
sh run.sh test
```

Windows:

```bat
run.bat config\default.ini
run.bat test
```

Прямой запуск: `PYTHONPATH=src python3 src/main.py config/default.ini`.
Без аргумента читается `config/default.ini`. Тесты напрямую:
`PYTHONPATH=src python3 -m unittest discover -s tests -v`.
Стиль кода проверяется `ruff check src tests` (правила в `ruff.toml`:
строки ≤ 79 символов, сложность ≤ 10, docstring, PEP8-имена,
не более 7 аргументов, нет магических чисел).

## Конфигурация (этап 1)

Все параметры задаются в файле INI:

```ini
[package]
name = com.fasterxml.jackson.core:jackson-databind  ; имя пакета
version = 2.16.0                                    ; версия пакета

[repository]
url = https://repo1.maven.org/maven2  ; URL репозитория или путь к файлу
test_mode = false                     ; режим тестового репозитория

[output]
image = out/jackson-databind.png  ; имя файла с изображением графа
ascii_tree = true                 ; вывод зависимостей ASCII-деревом
```

| Параметр | Правило проверки |
| --- | --- |
| `package.name` | Maven: `groupId:artifactId`; тестовый режим: большие латинские буквы |
| `package.version` | Обязательна для Maven, символы `A-Z a-z 0-9 _ . - +` |
| `repository.url` | Maven: схема `http`, `https` или `file`, у сети — хост; тестовый режим: существующий файл |
| `repository.test_mode` | `true/false`, `yes/no`, `on/off`, `1/0`; по умолчанию `false` |
| `output.image` | Расширение `.png`, не каталог |
| `output.ascii_tree` | Логическое значение, по умолчанию `false` |

Неизвестные секции и ключи, пропущенные обязательные параметры, ошибки
синтаксиса INI, отсутствие файла и кодировка не UTF-8 тоже считаются
ошибками. Проверка собирает все нарушения сразу, печатает их в stderr
и завершает программу с кодом 2.

Демонстрация: `sh scripts/stage1.sh` — корректные конфигурации и все
файлы из `config/errors/`.

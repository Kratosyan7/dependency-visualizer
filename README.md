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
| `output.reverse` | Логическое, по умолчанию `false`; `true` допустимо только при `test_mode = true` (этап 4) |

Неизвестные секции и ключи, пропущенные обязательные параметры, ошибки
синтаксиса INI, отсутствие файла и кодировка не UTF-8 тоже считаются
ошибками. Проверка собирает все нарушения сразу, печатает их в stderr
и завершает программу с кодом 2.

Демонстрация: `sh scripts/stage1.sh` — корректные конфигурации и все
файлы из `config/errors/`.

## Сбор данных из репозитория Maven (этап 2)

Менеджеры пакетов и сторонние библиотеки не используются. Модуль
`src/maven.py` скачивает файлы POM через `urllib` по стандартной
раскладке репозитория:

```
<url>/<groupId с / вместо .>/<artifactId>/<version>/<artifactId>-<version>.pom
```

и разбирает их `xml.etree.ElementTree`. Для заданной версии пакета
строится «эффективный» POM:

- цепочка родительских POM (`<parent>`) обходится циклом снизу вверх;
- свойства `<properties>` родителей переопределяются потомками,
  доступны встроенные `${project.version}`, `${project.groupId}`,
  `${project.parent.version}` и т. п.; подстановка многоуровневая;
- версии и `scope` без явного значения берутся из
  `<dependencyManagement>` (с учётом родителей и импорта BOM —
  `<scope>import</scope>`);
- зависимости, объявленные в родительском POM, наследуются;
- из диапазона версий `[1.0,2.0)` берётся включённая нижняя граница,
  `[1.2]` — точная версия.

URL может иметь схему `https`, `http` или `file` (локальный каталог в
раскладке Maven, например `file:///home/user/.m2/repository`).

Ошибки сети, HTTP 404 (нет пакета или версии), некорректный XML,
неопределимая версия зависимости выводятся в stderr, код возврата 3.

Пример (`sh run.sh run config/maven/httpclient.ini`):

```
Прямые зависимости org.apache.httpcomponents:httpclient:4.5.14: 5
  org.apache.httpcomponents:httpcore:4.4.16 (compile)
  commons-logging:commons-logging:1.2 (compile)
  commons-codec:commons-codec:1.11 (compile)
  junit:junit:4.11 (test)
  org.mockito:mockito-core:1.10.19 (test)
```

Демонстрация: `sh scripts/stage2.sh` — пакеты jackson-databind
(BOM и родительские POM), guava, spring-context, httpclient и ошибки
`config/errors/maven_*.ini` (нет пакета, нет версии, нет хоста).

## Граф зависимостей (этап 3)

Граф строится модулем `src/graph.py` функцией `bfs` — обходом в ширину
на очереди `collections.deque`, без рекурсии. Обходу передаётся функция,
возвращающая прямые зависимости пакета, поэтому один и тот же алгоритм
работает и с Maven, и с тестовым репозиторием. Каждый пакет ставится в
очередь один раз (множество `seen`), поэтому циклические зависимости не
приводят к зацикливанию. Рёбра, замыкающие циклы, находит `cycle_edges` —
обход в глубину на явном стеке — и они выводятся отдельным списком.
Если POM одного из транзитивных пакетов недоступен, ошибка выводится
после графа, а обход продолжается.

Правила Maven, которые учитывает `Resolver` (`src/maven.py`):

- в граф входят зависимости со `scope` `compile` и `runtime`
  (`test`, `provided`, `system`, `import` не транзитивны);
- `optional` учитываются только у исходного пакета;
- «ближайший побеждает»: первая встреченная при BFS версия
  `groupId:artifactId` используется для всех остальных упоминаний;
- `dependencyManagement` исходного пакета задаёт версии транзитивных
  зависимостей.

### Тестовый режим

При `test_mode = true` параметр `repository.url` — путь к файлу
описания графа. Пакеты называются большими латинскими буквами:

```text
# комментарий
A: B C      # A зависит от B и C
B: D
C: D E
D:          # пакет без зависимостей
```

Пакет, упомянутый только справа от двоеточия, считается пакетом без
зависимостей. Строка без двоеточия, недопустимое имя и повторное
описание пакета — ошибки с номером строки (код возврата 3).

| Файл | Случай |
| --- | --- |
| `data/basic.txt` | Простой ациклический граф |
| `data/diamond.txt` | Ромб: общая зависимость посещается один раз |
| `data/cycle.txt` | Цикл A → B → C → A (запуск от A и от C) |
| `data/self_loop.txt` | Пакет зависит сам от себя |
| `data/large.txt` | 15 пакетов, два цикла, недостижимые пакеты |
| `data/errors/*.txt` | Ошибки формата |

Пример (`sh run.sh run config/test/cycle.ini`):

```text
Граф зависимостей A (пакетов: 4, связей: 4)
  A -> B, D
  B -> C
  D -> (нет)
  C -> A
Циклические зависимости (ребро, замыкающее цикл):
  C -> A
```

Демонстрация: `sh scripts/stage3.sh` — все конфигурации `config/test/`
и транзитивный граф spring-context из Maven Central.

## Обратные зависимости (этап 4)

При `reverse = true` в секции `[output]` выводятся пакеты, которые
зависят от заданного (напрямую или транзитивно). Функция `reverse_bfs`
обращает все рёбра тестового репозитория (`invert`) и запускает тот же
обход `bfs`, что и на этапе 3, поэтому циклы обрабатываются так же.

Режим доступен только для тестового репозитория: в репозитории Maven
POM содержит лишь ссылки «вниз» и нет индекса пакетов, зависящих от
данного, поэтому сочетание `reverse = true` и `test_mode = false`
отклоняется при проверке конфигурации (код 2).

Пример (`sh run.sh run config/reverse/basic_d.ini`, `data/basic.txt`):

```text
Обратные зависимости D (зависящих пакетов: 3): B, C, A
  D <- B, C
  B <- A
  C <- A
  A <- (нет)
```

| Конфигурация | Случай |
| --- | --- |
| `config/reverse/basic_d.ini` | Общая зависимость двух пакетов |
| `config/reverse/basic_root.ini` | Корень: зависящих пакетов нет |
| `config/reverse/cycle_c.ini` | Пакет в цикле A → B → C → A |
| `config/reverse/self_loop.ini` | Пакет зависит сам от себя |
| `config/reverse/large_*.ini` | Большой граф: LOG, UTIL (в циклах), X (без описания) |
| `config/errors/reverse_maven.ini` | Ошибка: режим Maven |

Демонстрация: `sh scripts/stage4.sh`.

## Визуализация (этап 5)

После вывода графа программа:

1. формирует текст на языке диаграмм PlantUML (`to_plantuml`) и
   сохраняет его рядом с изображением: `out/okhttp.png` →
   `out/okhttp.puml`;
2. получает изображение PNG (`save_png`) и сохраняет его в файл
   `output.image` (каталог создаётся при необходимости);
3. при `ascii_tree = true` печатает зависимости ASCII-деревом
   (`ascii_tree`).

В PlantUML исходный пакет выделен голубым, пакет, POM которого не
удалось получить, — розовым, а ребро, замыкающее цикл, — красным
пунктиром. Изображение строит сам PlantUML: по умолчанию текст
кодируется алгоритмом PlantUML (deflate + base64 с алфавитом
`0-9A-Za-z-_`) и отправляется на сервер `https://www.plantuml.com/plantuml`.
Переменные окружения:

- `PLANTUML_SERVER` — другой сервер PlantUML (например, локальный
  `docker run -p 8080:8080 plantuml/plantuml-server` →
  `http://localhost:8080`);
- `PLANTUML_JAR` — путь к `plantuml.jar`; тогда PNG строит локальная
  Java (`java -jar plantuml.jar -tpng -pipe`) без обращения к сети.

Если PNG получить не удалось, граф, текст PlantUML и ASCII-дерево уже
выведены и сохранены, а программа сообщает причину с кодом возврата 4.

В ASCII-дереве, как и в `mvn dependency:tree`, поддерево пакета
раскрывается один раз — под ближайшим к корню родителем (по дереву
обхода BFS). Остальные вхождения помечены `(*)`, ребро к предку —
`(цикл)`. Дерево печатается обходом в глубину на явном стеке.

### Примеры для трёх пакетов

Демонстрация: `sh scripts/stage5.sh`. Тексты PlantUML лежат в
`docs/examples/`; изображения ниже строит сервер PlantUML по этим
текстам (в репозитории нет двоичных файлов).

**com.fasterxml.jackson.core:jackson-databind:2.16.0** — версии
зависимостей не указаны в самом POM и берутся из импортированного BOM
`jackson-bom` через цепочку родителей `jackson-base` →
`jackson-bom` → `jackson-parent` → `oss-parent`:

```text
com.fasterxml.jackson.core:jackson-databind:2.16.0
├── com.fasterxml.jackson.core:jackson-annotations:2.16.0
└── com.fasterxml.jackson.core:jackson-core:2.16.0
```

![jackson-databind](https://www.plantuml.com/plantuml/png/bP6nJiCm48PtFuNLph7Q30mTKCN0L5YwThdQJcfYtqNsHS1ONeBNG4mP4C_Wl1692b91OkXsl-w-JtUwTMA8t0KlKkEmXGX1fWCOUdHOomfyicSTOoleFDyIyZq4A-y8ARMWhH5ChMIIUsAcST15gzaH2dRihSol-Is_vtuuvZv_vC_XEBpaNceAgeB4DZu5hnv0DubGQOfszHqA0mnxXsPLgkMLMeZ92rYFpjd_z0x_uZiyyJC9IU92pZUkFl2sURxndRrK2eZ4C9sNVdkNbvfEwLnHYd6xehYUP3zLATOMpVIaBm00)

**org.springframework:spring-context:6.1.0** — общие зависимости
(spring-core нужен четырём пакетам, но раскрывается один раз):

```text
org.springframework:spring-context:6.1.0
├── org.springframework:spring-aop:6.1.0
│   ├── org.springframework:spring-beans:6.1.0 (*)
│   └── org.springframework:spring-core:6.1.0 (*)
├── org.springframework:spring-beans:6.1.0
│   └── org.springframework:spring-core:6.1.0 (*)
├── org.springframework:spring-core:6.1.0
│   └── org.springframework:spring-jcl:6.1.0
├── org.springframework:spring-expression:6.1.0
│   └── org.springframework:spring-core:6.1.0 (*)
└── io.micrometer:micrometer-observation:1.12.0
    └── io.micrometer:micrometer-commons:1.12.0
```

![spring-context](https://www.plantuml.com/plantuml/png/ZPE_Ri8m48TtFuL5vqGa_9COAjIXKzkbAuj9Zk0ItqNsKUX8NwAlKNLYgFeCvetgW4Y9r27Rv-I-toywApF7olB6bCAjDLRAAYFTIkMqrLZ8fIeTNBt9OQas9TyJyfCo81y9oLKgWrmmLP99BeYPmg2saB4c5Aov1Ea__AV_yeVZtX_yj_yvxe_l_Y395h6hRAXQXdZOabrFp-Se2nsmu-auJkA-gDCK5Y6fzuypnxOqnvFLayf9xCkR1rsi-7dzTbTke6kKegeLatGL5w3GjTIq--TRQ9c3hYRiAWlEXOMt_E6rhoasEhDaWC7EyOyZMZYmhufFUX8dwSKVTUr_oSfMyRXRSKR6KBsjwzA927SMHRVrpY-KDZHeQDZGI63Ip2NDNDhGu4nZWSFcsUXC4p43pEiVu1S0)

**com.squareup.okhttp3:okhttp:4.12.0** — конфликт версий: okio-jvm
требует kotlin-stdlib-jdk8 1.9.10, но okhttp объявляет 1.8.21 ближе к
корню, и по правилу «ближайший побеждает» используется 1.8.21;
kotlin-stdlib-common впервые встречается у okio-jvm с версией 1.9.10:

```text
com.squareup.okhttp3:okhttp:4.12.0
├── com.squareup.okio:okio:3.6.0
│   └── com.squareup.okio:okio-jvm:3.6.0
│       ├── org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.8.21 (*)
│       └── org.jetbrains.kotlin:kotlin-stdlib-common:1.9.10
└── org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.8.21
    ├── org.jetbrains.kotlin:kotlin-stdlib:1.8.21
    │   ├── org.jetbrains.kotlin:kotlin-stdlib-common:1.9.10 (*)
    │   └── org.jetbrains:annotations:13.0
    └── org.jetbrains.kotlin:kotlin-stdlib-jdk7:1.8.21
        └── org.jetbrains.kotlin:kotlin-stdlib:1.8.21 (*)
```

![okhttp](https://www.plantuml.com/plantuml/png/dPAzJiCm4CTtFuLLvbZDHp_eW2e69c1XpU8sRkh6kGln1SHONeBNG4mT4C_WlX69qbGj0aHPV7_BTx-_pxwf9LbIbHjcCms5B6NExL8c-AWXvGjfh3euITH2LeQk4EXMvehV8A0jv5mbZB3WX7o6H5WdwbBDIICmqcGKTo_krRsvpNRjDkxTVMpNssUtuNFCXRslPAcgGc2s92h2IHidaV03qMSDHq9QCthVPSVGYXZQ_1wNbaEVdrthT4btsTEbgTGl48qDeLb3CUpA_SC2B5EnKZGhfGOhCYIZ8OOsUfOIesVUAid6CVXYB0A_HGH_yFHM3_cHRtYYxx5bz8zRZuuHWrCHTMSvGWCv5_wkY-6Fa1Wa099i1gFU-67N-8ZLN-Pv5ytJTofWuBSgP12qAjgh0ODmdxTJGmRHLrMJ1rtjL47IJFed)

Тестовый репозиторий `data/large.txt` (циклы выделены красным) и его
обратные зависимости для LOG:

![large](https://www.plantuml.com/plantuml/png/RPBBJW8n58RtVOe6jfBCS1bWOn03Y1ak6SQeCIugBJ1XE9rCIunBV0bVmxXYONo6yaOEQIqbSVVrE_z9psdQ4PBaShj9aLWda96SRB1O4SfV4rZY1Ka5SogKBSWsbNqESams38yuS96HEQD8yWnBZb-ubBm89ZcRouG3aebC6LOVwbDzgVrXf_RgM_qSTeTtjSTNqoaw1WaiYr2fE9Om4HWyN0wJvKhErc_TTClSpFKawkcGx-hxNbVRwbau76fRS-rTF0orhhiwd0oqRRZs9exDK86hRsUJiTRDimsYmKphbglxerZRjcl7FMDzpzKFHfxjzsXa5HMFKwbS7jV_evEh8V0rrIqr45HjXw70KXD1pLODjH3KRMz3Knj1O7AUnQBSjDUrJDa_OJ5O6rUUoX6Z5vI85QFFfittJcDw_qG2r650Zz_o5m00)
![reverse LOG](https://www.plantuml.com/plantuml/png/RP9DJW8n583tFKK3MqaOXh_P64G7nGmCWI4kZ8jA2qmOMa9BZ3jnwnqy0veOMQXdwDp8JZhKQjnz_TvFtslQuWAjnMQP0Bw8wGgjqHBoESBiBgOpE4K99rO4aodQ9AB3gEYZ9O4zHXbVeGd1GB0L50pUCY6OIepNP29YHe68HKAWV9OlwOFSfO_oCtsIRr2-ovrybVjqA_VoGtwbMnNQmo0y1rabeZDLLL370aGSqZ8i1l5iBaQB-tQo8NREQJZqTP9Zwuie6cXTiVKuwWPQkxRkz29jgxOz6UGjQhQzyjlQrd-D4NIrRTYsx-TzcxQz78LzhJrRHs4OZF9LodRWp6-FyuTm7A0UerGwpjOzKCMGQwWAgAEfPgXkg05enRYSce2wfhFxrtc0Lc7fkZWa-0WZFYVu9jDbG6jvaSAwkR5XgFbFbHhO-ndfi8y3MeJYx2z-0m00)

### Сравнение со штатным инструментом Maven

Штатное средство — `mvn dependency:tree` (maven-dependency-plugin).
Скрипт `scripts/compare_mvn.sh` (нужны Maven 3 и Java) скачивает POM
каждого из трёх пакетов, запускает по нему

```sh
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dscope=runtime
```

и сохраняет вывод в `docs/mvn/<artifactId>.txt`. Состав пакетов и
выбранные версии должны совпадать, потому что инструмент реализует те
же правила Maven: наследование POM, свойства, `dependencyManagement` и
импорт BOM, транзитивность `compile` и `runtime`, `optional` только у
корня, «ближайший побеждает».

Расхождения в представлении и их причины:

| Отличие | Причина |
| --- | --- |
| Повторные вхождения | `dependency:tree` выводит пакет один раз и молча пропускает повторы (они видны только с `-Dverbose`); здесь повторы показаны с `(*)`, а в PNG — все рёбра графа |
| Конфликт версий | Maven с `-Dverbose` пишет «omitted for conflict with 1.8.21»; здесь отвергнутая версия не появляется, ребро сразу ведёт к выбранной |
| Scope в подписи | Maven печатает `:jar:1.8.21:compile`; здесь показаны только координаты, т. к. все рёбра графа — `compile`/`runtime` |
| Зависимости `test`/`provided` | Без `-Dscope=runtime` Maven показывает и тестовые зависимости корня; инструмент строит граф времени выполнения |

Возможности Maven, которые инструмент не реализует (на трёх примерах не
проявляются, но на других пакетах могут дать расхождения):
`<exclusions>` — граф может содержать исключённые в Maven пакеты;
профили (`<profiles>`, активация по ОС или JDK) — не применяются;
диапазоны версий — берётся нижняя граница, а Maven выбирает наибольшую
доступную версию из диапазона по `maven-metadata.xml`; релокации
(`<relocation>`) и классификаторы (`<classifier>`) — игнорируются.

## Модули и функции

- `src/main.py`: `build_parser` — параметр командной строки;
  `build_test_graph`, `build_maven_graph`, `build_graph` — выбор
  источника; `visualize` — PlantUML, ASCII-дерево и PNG;
  `report_problems` — вывод ошибок; `main` — коды возврата
  (0 — успех, 2 — конфигурация, 3 — данные, 4 — визуализация).
- `src/config.py`: `Settings` и `Settings.items`; `read_ini`,
  `check_schema`, `get_text`, `get_flag`, `check_name`,
  `check_version`, `check_repository`, `check_image`,
  `check_reverse`, `load_settings` — чтение и проверка INI.
- `src/maven.py`: `Coordinates`, `Dependency`, `Pom`, `EffectivePom`;
  `fetch_bytes` — загрузка; `parse_pom`, `read_dependencies`,
  `read_parent`, `strip_namespaces`, `text_of` — разбор XML;
  `interpolate`, `project_properties`, `expand`, `apply_management`,
  `normalize_version` — свойства и версии; `Repository` (`pom_url`,
  `raw_pom`, `lineage`, `merge_managed`, `effective`,
  `direct_dependencies`) — эффективный POM; `Resolver`
  (`pick_version`, `neighbours`) и `is_inherited` — рёбра графа.
- `src/testrepo.py`: `parse_line`, `check_names`, `parse_repository`,
  `load_repository` — тестовый репозиторий.
- `src/graph.py`: `Graph`, `bfs`, `cycle_edges`, `invert`,
  `reverse_bfs`, `format_graph`, `format_reverse`.
- `src/render.py`: `node_label`, `to_plantuml`, `encode_plantuml`,
  `render_with_server`, `render_with_jar`, `save_png`,
  `nearest_parents`, `tree_mark`, `ascii_tree`.

Тесты (`tests/`, 82 шт.) не обращаются к сети: репозиторий Maven
подменяется словарём POM или локальным каталогом `file://`, сервер
PlantUML — заглушкой. Демонстрационные скрипты этапов 1–4 показывают
текущее поведение программы (параметры и прямые зависимости
выводились только на своих этапах), а их ошибки — те же.

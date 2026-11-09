"""Визуализация графа: текст PlantUML, изображение PNG и ASCII-дерево.

PNG получается из текста PlantUML одним из двух способов:

- если переменная окружения PLANTUML_JAR указывает на plantuml.jar,
  запускается локальная Java (java -jar plantuml.jar -tpng -pipe);
- иначе текст кодируется по алгоритму PlantUML (deflate + base64 с
  алфавитом PlantUML) и отправляется на сервер PLANTUML_SERVER
  (по умолчанию официальный www.plantuml.com).
"""

import base64
import os
import subprocess
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from graph import Graph, cycle_edges

DEFAULT_SERVER = "https://www.plantuml.com/plantuml"
TIMEOUT = 60
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BASE64_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
)
PLANTUML_ALPHABET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
)
TRANSLATION = str.maketrans(BASE64_ALPHABET, PLANTUML_ALPHABET)
GROUP_SIZE = 3
ROOT_COLOR = "#LightSkyBlue"
ERROR_COLOR = "#Pink"
CYCLE_STYLE = "#Red,dashed"
LAST_BRANCH = "└── "
MIDDLE_BRANCH = "├── "
LAST_INDENT = "    "
MIDDLE_INDENT = "│   "
REPEAT_MARK = " (*)"
CYCLE_MARK = " (цикл)"


class RenderError(Exception):
    """Не удалось получить изображение графа."""


def node_label(name: str) -> str:
    """Подпись узла: части groupId:artifactId:version на разных строках."""
    return name.replace(":", "\\n")


def to_plantuml(graph: Graph, title: str = "") -> str:
    """Текстовое представление графа на языке диаграмм PlantUML."""
    aliases = {node: f"n{index}" for index, node in enumerate(graph.edges)}
    lines = ["@startuml", "skinparam shadowing false",
             "skinparam defaultFontName Monospaced", "top to bottom direction"]
    if title:
        lines.append(f"title {title}")
    for node, alias in aliases.items():
        color = ""
        if node == graph.root:
            color = f" {ROOT_COLOR}"
        elif node in graph.errors:
            color = f" {ERROR_COLOR}"
        lines.append(f'rectangle "{node_label(node)}" as {alias}{color}')
    back = set(cycle_edges(graph))
    for node, children in graph.edges.items():
        for child in children:
            style = f" {CYCLE_STYLE}" if (node, child) in back else ""
            arrow = f"-[{style.strip()}]->" if style else "-->"
            lines.append(f"{aliases[node]} {arrow} {aliases[child]}")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def encode_plantuml(text: str) -> str:
    """Кодирует текст для URL сервера PlantUML (deflate + base64)."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    data = compressor.compress(text.encode("utf-8")) + compressor.flush()
    padding = -len(data) % GROUP_SIZE
    encoded = base64.b64encode(data + b"\0" * padding).decode("ascii")
    return encoded.translate(TRANSLATION)


def render_with_server(text: str) -> bytes:
    """Получает PNG с сервера PlantUML."""
    server = os.environ.get("PLANTUML_SERVER", DEFAULT_SERVER).rstrip("/")
    url = f"{server}/png/{encode_plantuml(text)}"
    request = urllib.request.Request(url, headers={"User-Agent": "dv/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        message = f"сервер PlantUML: HTTP {error.code} {error.reason}"
        raise RenderError(message) from error
    except (urllib.error.URLError, OSError) as error:
        raise RenderError(f"сервер PlantUML недоступен: {error}") from error


def render_with_jar(text: str, jar: str) -> bytes:
    """Получает PNG локальным plantuml.jar."""
    command = ["java", "-jar", jar, "-tpng", "-pipe"]
    try:
        result = subprocess.run(command, input=text.encode("utf-8"),
                                capture_output=True, timeout=TIMEOUT,
                                check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise RenderError(f"не удалось запустить {jar}: {error}") from error
    return result.stdout


def save_png(text: str, path: Path) -> None:
    """Сохраняет изображение графа в файл PNG."""
    jar = os.environ.get("PLANTUML_JAR")
    data = render_with_jar(text, jar) if jar else render_with_server(text)
    if not data.startswith(PNG_SIGNATURE):
        raise RenderError("ответ PlantUML не является изображением PNG")
    try:
        path.write_bytes(data)
    except OSError as error:
        raise RenderError(f"не удалось записать {path}: {error}") from error


def nearest_parents(graph: Graph) -> dict[str, str]:
    """Родитель каждого пакета в дереве BFS (ближайший к корню путь)."""
    owner: dict[str, str] = {}
    for node, children in graph.edges.items():
        for child in children:
            if child != graph.root:
                owner.setdefault(child, node)
    return owner


def tree_mark(
    child: str,
    path: tuple[str, ...],
    owner: dict[str, str],
    expanded: set[str],
) -> str:
    """Пометка узла дерева: цикл, повтор или пустая строка."""
    if child in path:
        return CYCLE_MARK
    if child in expanded or owner.get(child) != path[-1]:
        return REPEAT_MARK
    return ""


def ascii_tree(graph: Graph) -> list[str]:
    """Зависимости в виде ASCII-дерева (DFS на явном стеке).

    Как в mvn dependency:tree, поддерево пакета раскрывается один раз —
    под ближайшим к корню родителем; остальные вхождения помечаются (*),
    ребро обратно к предку помечается (цикл).
    """
    owner = nearest_parents(graph)
    lines = [graph.root]
    expanded = {graph.root}
    stack = [(graph.edges.get(graph.root, []), 0, "", (graph.root,))]
    while stack:
        children, index, prefix, path = stack.pop()
        if index >= len(children):
            continue
        stack.append((children, index + 1, prefix, path))
        child = children[index]
        last = index == len(children) - 1
        mark = tree_mark(child, path, owner, expanded)
        branch = LAST_BRANCH if last else MIDDLE_BRANCH
        lines.append(prefix + branch + child + mark)
        if not mark:
            expanded.add(child)
            indent = LAST_INDENT if last else MIDDLE_INDENT
            stack.append((graph.edges.get(child, []), 0, prefix + indent,
                          path + (child,)))
    return lines

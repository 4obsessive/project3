"""La interfaz (static/) y los mensajes del servidor que llegan a ella están en inglés."""
import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")
SCOUTING = os.path.join(ROOT, "scouting")

WORDS = ["partidas", "partida", "jugador", "jugadores", "muertes", "muerte", "equipo", "daño", "línea", "linea",
         "carril", "objetivo", "no disponible", "cargando", "guardar", "buscar", "gana", "jungla", "gankeo",
         "ajustes", "inicio", "informe", "actualizar", "actualización", "héroe", "héroes", "cuenta", "cuentas",
         "ninguna", "ninguno", "todas", "todos", "sin resultados", "error al", "libre", "libres"]
SPANISH = re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in WORDS) + r")(?![\w-])", re.I)
# mensajes de backend: además, giros típicos de los errores
BACKEND = re.compile(SPANISH.pattern[:-len(r")(?![\w-])")] +
                     r"|no válid[oa]|debe ser|demasiado|falta|redirección|sin respuesta|no existe|no se |encontrad|permitid|interno|grande|imagen)(?![\w-])", re.I)
IGNORE_MARK = "es-ok"  # línea con /* es-ok */: valores heredados a propósito (rutas antiguas)


def strip_js_comments(src):
    """Quita // y /* */ respetando cadenas ('', "", ``); las líneas con /* es-ok */ se descartan."""
    out, i, n = [], 0, len(src)
    state = None  # None, "'", '"', '`'
    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if state is None:
            if two == "//":
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if two == "/*":
                j = src.find("*/", i + 2)
                chunk = src[i:] if j < 0 else src[i:j + 2]
                if IGNORE_MARK in chunk:
                    out.append("\x00IGNORE\x00")
                i = n if j < 0 else j + 2
                continue
            if c in "'\"`":
                state = c
            out.append(c)
        else:
            out.append(c)
            if c == "\\":
                out.append(src[i + 1:i + 2])
                i += 2
                continue
            if c == state:
                state = None
            elif c == "\n" and state != "`":
                state = None  # una regex con comilla no debe arrastrar el estado
        i += 1
    return "".join(out)


STRING_RE = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`")


def string_literals(line):
    """Contenido de las cadenas ('', "", ``) de una línea, sin las expresiones ${...}."""
    out = []
    for m in re.finditer(STRING_RE, line):
        txt = next(g for g in m.groups() if g is not None)
        out.append(re.sub(r"\$\{[^}]*\}", " ", txt))
    return out


def user_text(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if path.endswith(".html"):
        src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
        lines = src.splitlines()
    else:
        lines = [" ".join(string_literals(ln)) if "\x00IGNORE\x00" not in ln else ln
                 for ln in strip_js_comments(src).splitlines()]
    return [(n, ln) for n, ln in enumerate(lines, 1) if "\x00IGNORE\x00" not in ln]


def static_files():
    for base, _, files in os.walk(STATIC):
        for f in files:
            if f.endswith((".js", ".html")):
                yield os.path.join(base, f)


class UiEnglish(unittest.TestCase):
    def test_static_has_no_spanish_ui_strings(self):
        hits = []
        for path in static_files():
            for n, line in user_text(path):
                m = SPANISH.search(line)
                if m:
                    hits.append(f"{os.path.relpath(path, ROOT)}:{n}: {m.group(1)!r} -> {line.strip()[:110]}")
        self.assertEqual(hits, [], "Spanish leftovers in the UI:\n" + "\n".join(hits))

    def test_comment_stripper(self):
        src = "const a = 'http://x'; // partida\n/* jugador */ const b = \"// equipo\";\n"
        txt = strip_js_comments(src)
        self.assertNotIn("partida", txt)
        self.assertNotIn("jugador", txt)
        self.assertIn("// equipo", txt)  # dentro de una cadena no es comentario

    def test_html_declares_english(self):
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
            self.assertIn('<html lang="en">', f.read())

    def test_backend_messages_are_english(self):
        names = {"HttpError", "ApiError", "ValueError", "KeyError", "DemoError", "MatchError", "HTTPError", "_error"}
        hits = []
        for fname in ("server.py", "api.py", "demo.py", "players.py", "teams.py", "minimap.py", "analysis.py", "updater.py"):
            path = os.path.join(SCOUTING, fname)
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name not in names:
                    continue
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        m = BACKEND.search(sub.value)
                        if m:
                            hits.append(f"{fname}:{sub.lineno}: {sub.value[:90]!r}")
        self.assertEqual(hits, [], "Spanish backend messages:\n" + "\n".join(hits))

    def test_backend_status_labels_are_english(self):
        from scouting import updater
        for label in updater.STEP_LABELS.values():
            self.assertIsNone(BACKEND.search(label), label)


if __name__ == "__main__":
    unittest.main()

"""
The two-runtime rule of CLAUDE.md, checked on the source:

- World A (ZeissAPI/, .py files and the Python inside every .czmac) runs in IronPython 2.7:
  no f-strings, no CPython-only packages, no Python-3-only syntax, and no multi-argument
  print() without the __future__ import, which 2.7 would print as a tuple.
- World B (data_processing/, IO/, utils.py, result_processing/) never imports System, clr or
  the ZEN API.

The source is parsed with CPython 3's ast, so World A code must also be valid Python 3
syntax - which it has to be anyway for pytest to import it.
"""
import ast
import glob
import os
import re
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CPYTHON_ONLY = {
    "numpy", "pathlib", "torch", "cv2", "skimage", "scipy", "pandas", "matplotlib", "cellpose",
    "pylibCZIrw", "aicspylibczi", "czifile", "tifffile", "typing", "dataclasses", "enum",
    "asyncio", "statistics", "secrets",
}
WORLD_A_ONLY = {"System", "clr", "Zeiss", "Zen"}


def _files(*patterns):
    found = []
    for pattern in patterns:
        found.extend(glob.glob(os.path.join(ROOT, pattern), recursive=True))
    return sorted(f for f in found if "__pycache__" not in f)


WORLD_A = _files("ZeissAPI/**/*.py", "ZeissAPI/**/*.czmac")
WORLD_B = _files("data_processing/**/*.py", "IO/**/*.py", "utils.py", "result_processing/**/*.py")


def _id(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def source_of(path):
    """
    :return: str Python source; for a .czmac the content of its <Text> element, unescaped
    """
    # utf-8-sig: some World A files start with a byte order mark
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if path.endswith(".czmac"):
        return ET.fromstring(text.encode("utf-8")).findtext("Text")
    return text


def tree_of(path):
    return ast.parse(source_of(path), filename=_id(path))


def imported_roots(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module.split(".")[0]


def py3_only_syntax(tree):
    """
    :return: list of (line, what) for syntax IronPython 2.7 cannot run
    """
    found = []
    plain = {
        ast.Nonlocal: "nonlocal", ast.YieldFrom: "yield from", ast.AsyncFunctionDef: "async def",
        ast.Await: "await", ast.AsyncFor: "async for", ast.AsyncWith: "async with",
        ast.NamedExpr: "walrus :=", ast.AnnAssign: "annotated assignment", ast.MatMult: "@ operator",
        ast.Match: "match statement",
    }
    for node in ast.walk(tree):
        for kind, what in plain.items():
            if isinstance(node, kind):
                found.append((getattr(node, "lineno", 0), what))
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            args = node.args
            if args.kwonlyargs:
                found.append((node.lineno, "keyword-only arguments"))
            if args.posonlyargs:
                found.append((node.lineno, "positional-only arguments"))
            annotated = [a for a in args.args + args.kwonlyargs if a.annotation is not None]
            if annotated or getattr(node, "returns", None) is not None:
                found.append((node.lineno, "annotations"))
        if isinstance(node, ast.Raise) and node.cause is not None:
            found.append((node.lineno, "raise ... from"))
        if isinstance(node, ast.Starred) and isinstance(node.ctx, ast.Store):
            found.append((node.lineno, "starred assignment"))
        if isinstance(node, ast.Dict) and None in node.keys:
            found.append((node.lineno, "{**dict} unpacking"))
    return found


###################### World A ########################################################################


@pytest.mark.parametrize("path", WORLD_A, ids=_id)
def test_world_a_has_no_fstrings(path):
    lines = [n.lineno for n in ast.walk(tree_of(path)) if isinstance(n, ast.JoinedStr)]

    assert not lines, "f-string at line(s) {}".format(lines)


@pytest.mark.parametrize("path", WORLD_A, ids=_id)
def test_world_a_imports_no_cpython_only_modules(path):
    bad = [(line, name) for line, name in imported_roots(tree_of(path)) if name in CPYTHON_ONLY]

    assert not bad, "CPython-only import: {}".format(bad)


@pytest.mark.parametrize("path", WORLD_A, ids=_id)
def test_world_a_has_no_py3_only_syntax(path):
    bad = py3_only_syntax(tree_of(path))

    assert not bad, "Python 3 only: {}".format(bad)


@pytest.mark.parametrize("path", WORLD_A, ids=_id)
def test_world_a_print_with_many_args_needs_future_import(path):
    tree = tree_of(path)
    has_future = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                     and any(a.name == "print_function" for a in n.names) for n in ast.walk(tree))
    calls = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
             and (len(n.args) > 1 or n.keywords)]

    assert has_future or not calls, "print() with several arguments prints a tuple in 2.7, line(s) {}".format(calls)


###################### World B ########################################################################


@pytest.mark.parametrize("path", WORLD_B, ids=_id)
def test_world_b_never_imports_system_or_zen(path):
    bad = [(line, name) for line, name in imported_roots(tree_of(path)) if name in WORLD_A_ONLY]

    assert not bad, "World A import in World B: {}".format(bad)


def test_both_worlds_were_found():
    # guards the globs above: an empty list would make every test here pass vacuously
    assert len([p for p in WORLD_A if p.endswith(".czmac")]) >= 2
    assert len([p for p in WORLD_A if p.endswith(".py")]) >= 10
    assert len(WORLD_B) >= 10


@pytest.mark.parametrize("snippet", [
    "def f(x):\n    nonlocal x\n",
    "def f():\n    yield from g()\n",
    "async def f():\n    pass\n",
    "if (n := 1):\n    pass\n",
    "x: int = 1\n",
    "c = a @ b\n",
    "def f(a, *, b):\n    pass\n",
    "def f(a, /, b):\n    pass\n",
    "def f(a: int) -> int:\n    pass\n",
    "raise ValueError() from None\n",
    "a, *b = c\n",
    "d = {**a}\n",
])
def test_py3_only_detector_catches_examples(snippet):
    # guards the detector itself: each snippet must be reported
    assert py3_only_syntax(ast.parse(snippet))

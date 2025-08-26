
# src/subprocess/code_analyzer.py
"""
AST-based routing analyzer for AsyncExecutor.

Goals
-----
- Detect top-level await robustly using CPython's compiler flags.
- Capture metadata: imports/defs, last-expression presence.
- Heuristically detect operations that must not run on the loop (blocking IO).

Design
------
- We use `compile(..., flags=ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)`
  to obtain an AST even when there is top-level await.
- We inspect the code object compiled with `PyCF_ALLOW_TOP_LEVEL_AWAIT` to see
  if the CO_COROUTINE flag is set (indicating a coroutine module).
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from typing import List


@dataclass
class CodeAnalysis:
    has_top_level_await: bool = False
    needs_blocking_io: bool = False
    has_async_constructs: bool = False
    is_expression_cell: bool = False
    imports_found: List[str] = field(default_factory=list)
    functions_defined: List[str] = field(default_factory=list)
    classes_defined: List[str] = field(default_factory=list)


class CodeAnalyzer:
    BLOCKING_FUNCS = {
        ("time", "sleep"),
    }
    BLOCKING_NAMES = {"input"}  # builtins.input

    @classmethod
    def analyze(cls, code: str) -> CodeAnalysis:
        # First, try to get an AST that allows TLA
        try:
            module_ast: ast.Module = compile(
                code, "<analyze>", "exec", ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
            )
        except SyntaxError:
            module_ast = ast.parse(code, "<analyze>", "exec")

        ca = CodeAnalysis()

        # Collect defs/imports and detect async constructs
        for node in ast.walk(module_ast):
            if isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)):
                ca.has_async_constructs = True
            if isinstance(node, ast.Import):
                for alias in node.names:
                    ca.imports_found.append(alias.name.split(".")[0])
            if isinstance(node, ast.ImportFrom) and node.module:
                ca.imports_found.append(node.module.split(".")[0])
            if isinstance(node, ast.FunctionDef):
                ca.functions_defined.append(node.name)
            if isinstance(node, ast.ClassDef):
                ca.classes_defined.append(node.name)
            if isinstance(node, ast.Call):
                # input(...)
                if isinstance(node.func, ast.Name) and node.func.id in cls.BLOCKING_NAMES:
                    ca.needs_blocking_io = True
                # time.sleep(...)
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    mod, attr = node.func.value.id, node.func.attr
                    if (mod, attr) in cls.BLOCKING_FUNCS:
                        ca.needs_blocking_io = True

        # Expression cell detection
        if module_ast.body and isinstance(module_ast.body[-1], ast.Expr):
            ca.is_expression_cell = True

        # Now compile to a code object and check for TLA
        try:
            code_obj = compile(code, "<analyze>", "exec", ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            ca.has_top_level_await = bool(code_obj.co_flags & inspect.CO_COROUTINE)
        except SyntaxError:
            ca.has_top_level_await = False

        return ca

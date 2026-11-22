#!/usr/bin/env python3
"""离线静态检查：编译全部后端源码 + 校验跨模块导入的符号确实存在。"""
import ast
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
THIRD_PARTY = {
    "fastapi", "sqlalchemy", "redis", "sklearn", "numpy", "pydantic",
    "jose", "passlib", "psycopg", "uvicorn",
}

errors = []
py_files = sorted(ROOT.rglob("*.py"))
for f in py_files:
    py_compile.compile(str(f), doraise=True)
print(f"compile: {len(py_files)} files ok")


def module_path(module):
    rel = Path(*module.split("."))
    candidate = rel.parent / (rel.name + ".py")
    pkg_init = rel / "__init__.py"
    base = ROOT.parent
    if (base / candidate).exists():
        return base / candidate
    if (base / pkg_init).exists():
        return base / pkg_init
    return None


def defined_names(path):
    tree = ast.parse(path.read_text())
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


for f in py_files:
    tree = ast.parse(f.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level == 0:
            if isinstance(node, ast.ImportFrom) and node.module:
                root_name = node.module.split(".")[0]
                if root_name in THIRD_PARTY:
                    continue
            continue
        # 相对导入：解析目标模块
        parts = list(f.relative_to(ROOT.parent).parent.parts)
        for _ in range(node.level - 1):
            parts.pop()
        if node.module:
            parts += node.module.split(".")
        target = module_path(".".join(parts))
        if target is None:
            errors.append(f"{f}: 找不到相对导入模块 {'.'.join(parts)}")
            continue
        available = defined_names(target)
        for alias in node.names:
            if alias.name not in available:
                errors.append(
                    f"{f}:{node.lineno} 从 {'.'.join(parts)} 导入的 "
                    f"'{alias.name}' 在目标模块中不存在"
                )

if errors:
    for e in errors:
        print("ERROR", e)
    sys.exit(1)
print("import symbols: all cross-module imports resolve")

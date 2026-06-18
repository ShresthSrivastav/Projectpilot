"""Import Validator — verify every import resolves in generated projects."""

import ast
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

FATAL_ERRORS = {"ModuleNotFoundError", "ImportError", "SyntaxError"}


def validate(job_dir: Path) -> dict:
    """Try to compile + import every Python module in the project.

    Returns:
        {"passed": bool, "errors": [...], "files_checked": int}
    """
    py_files = sorted(job_dir.rglob("*.py"))
    errors: list[str] = []

    for py_file in py_files:
        rel = str(py_file.relative_to(job_dir))

        # 1. Syntax check first
        try:
            compile(py_file.read_bytes(), str(py_file), "exec")
        except SyntaxError as exc:
            errors.append(f"[{rel}] SyntaxError: {exc}")
            continue

        # 2. Extract all top-level import names via AST
        import_names = _extract_imports(py_file)
        if not import_names:
            continue

        # 3. Try each import in a subprocess with the job dir on sys.path
        for mod_name in import_names:
            result = subprocess.run(
                [sys.executable, "-c", f"import {mod_name}"],
                cwd=str(job_dir),
                capture_output=True, text=True, timeout=15,
                env={**{k: v for k, v in _get_parent_env().items() if k in {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "TEMP", "TMP"}}, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                errors.append(f"[{rel}] Import `{mod_name}`: {stderr[:300]}")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "files_checked": len(py_files),
    }


def _extract_imports(py_file: Path) -> list[str]:
    """Return top-level third-party module names imported in the file."""
    try:
        tree = ast.parse(py_file.read_text())
    except SyntaxError:
        return []

    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in _STDLIB_MODULES:
                    names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top not in _STDLIB_MODULES:
                    names.append(node.module)
    return sorted(set(names))


def _classify_error(stderr: str) -> str:
    for errtype in FATAL_ERRORS:
        if errtype in stderr:
            return errtype
    return "ImportError"


def _get_parent_env() -> dict:
    import os
    return dict(os.environ)


_STDLIB_MODULES: set = set()
try:
    _STDLIB_MODULES = set(sys.stdlib_module_names)
except AttributeError:
    _STDLIB_MODULES = {
        "os", "sys", "re", "json", "math", "time", "datetime", "pathlib",
        "collections", "itertools", "functools", "typing", "abc", "enum",
        "hashlib", "base64", "uuid", "subprocess", "threading", "asyncio",
        "logging", "warnings", "contextlib", "copy", "inspect", "ast",
        "importlib", "io", "textwrap", "string", "random", "statistics",
        "http", "urllib", "xml", "html", "csv", "sqlite3", "argparse", "configparser", "tempfile", "shutil", "glob", "fnmatch",
        "unittest", "doctest", "pdb", "traceback", "pprint",
        "dis", "tokenize", "pickle", "shelve", "marshal",
        "zipfile", "tarfile", "gzip", "bz2", "lzma",
        "socket", "ssl", "email", "smtplib", "poplib", "imaplib",
        "struct", "array", "ctypes", "decimal", "fractions",
        "platform", "errno", "signal", "mmap", "sysconfig",
    }

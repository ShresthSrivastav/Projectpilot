"""Plugin Loader — discovers, loads, and manages agent plugins."""

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "./agents/plugins"))

_registry: dict[str, dict[str, Any]] = {}
_hooks: dict[str, list[str]] = {}


def _discover_plugins() -> list[Path]:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    py_files = sorted(PLUGIN_DIR.glob("*.py"))
    json_files = sorted(PLUGIN_DIR.glob("*.json"))
    plugin_paths = set(py_files)

    manifest_plugins = set()
    for mf in json_files:
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            entry = data.get("entry", "")
            if entry:
                ep = PLUGIN_DIR / entry
                if ep.exists():
                    manifest_plugins.add(ep)
                    _registry[data.get("name", ep.stem)] = {
                        "name": data.get("name", ep.stem),
                        "entry": str(ep),
                        "hooks": data.get("hooks", []),
                        "description": data.get("description", ""),
                        "version": data.get("version", "1.0.0"),
                        "manifest": str(mf),
                    }
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Plugin manifest parse error: %s", exc)

    for py in py_files:
        if py not in manifest_plugins and py.stem != "__init__":
            name = py.stem
            if name not in _registry:
                _registry[name] = {
                    "name": name,
                    "entry": str(py),
                    "hooks": [],
                    "description": "",
                    "version": "1.0.0",
                    "manifest": None,
                }

    return list(plugin_paths | manifest_plugins)


def _load_plugin_module(py_path: Path) -> Any | None:
    try:
        module_name = f"agents_plugin_{py_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(py_path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return mod
        return None
    except Exception as exc:
        logger.error("Failed to load plugin %s: %s", py_path, exc)
        return None


def load_plugins() -> dict[str, dict[str, Any]]:
    _discover_plugins()
    loaded = {}
    for name, info in _registry.items():
        if info.get("_loaded"):
            continue
        py_path = Path(info["entry"])
        if not py_path.exists():
            logger.warning("Plugin file not found: %s", py_path)
            continue
        mod = _load_plugin_module(py_path)
        if mod:
            run_fn = getattr(mod, "run", None)
            if run_fn and callable(run_fn):
                info["entry_point"] = run_fn
            info["module"] = mod
            info["_loaded"] = True
            for hook in info.get("hooks", []):
                hook_fn = getattr(mod, hook, None)
                if hook_fn and callable(hook_fn):
                    if hook not in _hooks:
                        _hooks[hook] = []
                    _hooks[hook].append(name)
            loaded[name] = info
            logger.info("Loaded plugin: %s v%s", name, info.get("version", "1.0.0"))
    return loaded


def get_plugin(name: str) -> dict[str, Any] | None:
    if name not in _registry:
        _discover_plugins()
    info = _registry.get(name)
    if info and not info.get("_loaded"):
        load_plugins()
        info = _registry.get(name)
    return info


def list_plugins() -> list[dict[str, Any]]:
    _discover_plugins()
    return [
        {
            "name": info["name"],
            "version": info.get("version", "1.0.0"),
            "description": info.get("description", ""),
            "hooks": info.get("hooks", []),
            "loaded": info.get("_loaded", False),
            "enabled": info.get("enabled", True),
        }
        for info in _registry.values()
    ]


def enable_plugin(name: str) -> bool:
    info = _registry.get(name)
    if info:
        info["enabled"] = True
        return True
    return False


def disable_plugin(name: str) -> bool:
    info = _registry.get(name)
    if info:
        info["enabled"] = False
        return True
    return False


def run_hook(hook: str, context: dict[str, Any]) -> dict[str, Any]:
    results = {}
    for plugin_name in _hooks.get(hook, []):
        info = _registry.get(plugin_name)
        if not info or not info.get("enabled", True):
            continue
        mod = info.get("module")
        if mod:
            hook_fn = getattr(mod, hook, None)
            if hook_fn and callable(hook_fn):
                try:
                    result = hook_fn(context)
                    results[plugin_name] = {"status": "ok", "result": result}
                except Exception as exc:
                    results[plugin_name] = {"status": "error", "error": str(exc)}
    return results


def reload_plugins() -> dict[str, dict[str, Any]]:
    _registry.clear()
    _hooks.clear()
    return load_plugins()

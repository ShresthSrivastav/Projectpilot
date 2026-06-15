"""Plugin Registry — manage installation, lifecycle, and sandboxing of plugins."""
import hashlib
import importlib
import inspect
import json
import logging
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import yaml

from sdk.plugin_sdk.base_plugin import BasePlugin, PluginManifest, PluginType


@dataclass
class PluginEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    manifest: PluginManifest = field(default_factory=PluginManifest)
    source: str = ""
    enabled: bool = False
    installed_at: str = ""
    updated_at: str = ""
    resource_limits: Dict[str, Any] = field(default_factory=lambda: {"cpu": 1, "memory_mb": 256})
    permissions_granted: List[str] = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "manifest": self.manifest.to_dict(),
            "source": self.source,
            "enabled": self.enabled,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "resource_limits": self.resource_limits,
            "permissions_granted": self.permissions_granted,
            "checksum": self.checksum,
        }


class PluginRegistry:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, storage_dir: str = "plugin_data"):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: Dict[str, PluginEntry] = {}
        self._plugin_instances: Dict[str, BasePlugin] = {}
        self._logger = logging.getLogger("PluginRegistry")
        self._load_index()

    def _index_path(self) -> Path:
        return self.storage_dir / "index.json"

    def _load_index(self) -> None:
        path = self._index_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data:
                    entry = PluginEntry(
                        id=item["id"],
                        manifest=PluginManifest.from_dict(item["manifest"]),
                        source=item.get("source", ""),
                        enabled=item.get("enabled", False),
                        installed_at=item.get("installed_at", ""),
                        updated_at=item.get("updated_at", ""),
                        resource_limits=item.get("resource_limits", {}),
                        permissions_granted=item.get("permissions_granted", []),
                        checksum=item.get("checksum", ""),
                    )
                    self._plugins[entry.id] = entry
            except Exception as e:
                self._logger.warning("Failed to load plugin index: %s", e)

    def _save_index(self) -> None:
        data = [entry.to_dict() for entry in self._plugins.values()]
        self._index_path().write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )

    def _compute_checksum(self, source_path: str) -> str:
        path = Path(source_path)
        if not path.exists():
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _validate_manifest(self, manifest: PluginManifest) -> List[str]:
        errors = []
        if not manifest.name:
            errors.append("Plugin name is required")
        if not manifest.entry_point:
            errors.append("Entry point is required")
        if manifest.plugin_type not in [pt.value for pt in PluginType]:
            errors.append(f"Invalid plugin type: {manifest.plugin_type}")
        if manifest.compatibility:
            try:
                ver = manifest.compatibility.replace(">=", "").replace("==", "").replace(">", "").strip()
                parts = ver.split(".")
                if len(parts) != 3:
                    errors.append(f"Invalid compatibility format: {manifest.compatibility}")
            except Exception:
                errors.append(f"Invalid compatibility format: {manifest.compatibility}")
        return errors

    def install_plugin(
        self,
        source: str,
        manifest: Optional[PluginManifest] = None,
        permissions: Optional[List[str]] = None,
    ) -> PluginEntry:
        source_path = Path(source)
        if source_path.exists() and source_path.suffix == ".py":
            checksum = self._compute_checksum(source)
            plugin_dir = self.storage_dir / "installed" / Path(source).stem
            plugin_dir.mkdir(parents=True, exist_ok=True)
            dest = plugin_dir / source_path.name
            if not dest.exists():
                import shutil
                shutil.copy2(str(source_path), str(dest))
            source = str(dest)

        if manifest is None:
            manifest = self._detect_manifest(source)

        errors = self._validate_manifest(manifest)
        if errors:
            raise ValueError(f"Invalid manifest: {'; '.join(errors)}")

        if not manifest.entry_point:
            manifest.entry_point = source

        entry = PluginEntry(
            manifest=manifest,
            source=source,
            enabled=False,
            installed_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            permissions_granted=permissions or manifest.permissions,
            checksum=checksum if 'checksum' in dir() else self._compute_checksum(source),
        )
        self._plugins[entry.id] = entry
        self._save_index()

        try:
            instance = self._load_plugin_instance(entry)
            if instance.install():
                entry.enabled = True
                self._plugin_instances[entry.id] = instance
                self._save_index()
        except Exception as e:
            self._logger.error("Plugin %s install hook failed: %s", entry.manifest.name, e)

        return entry

    def _detect_manifest(self, source: str) -> PluginManifest:
        manifest = PluginManifest(entry_point=source)
        source_path = Path(source)

        if source_path.suffix == ".py":
            manifest.name = source_path.stem
            content = source_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("# name:"):
                    manifest.name = line.split(":", 1)[1].strip()
                elif line.startswith("# version:"):
                    manifest.version = line.split(":", 1)[1].strip()
                elif line.startswith("# author:"):
                    manifest.author = line.split(":", 1)[1].strip()
                elif line.startswith("# description:"):
                    manifest.description = line.split(":", 1)[1].strip()
                elif line.startswith("# type:"):
                    manifest.plugin_type = line.split(":", 1)[1].strip()

        elif source_path.suffix in (".yaml", ".yml"):
            try:
                data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
                if data:
                    manifest = PluginManifest.from_dict(data)
            except Exception as e:
                self._logger.warning("Could not parse manifest YAML: %s", e)

        elif source_path.is_dir():
            manifest.name = source_path.name
            yaml_path = source_path / "plugin.yaml"
            if yaml_path.exists():
                try:
                    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                    if data:
                        manifest = PluginManifest.from_dict(data)
                except Exception:
                    pass

        return manifest

    def _load_plugin_instance(self, entry: PluginEntry) -> BasePlugin:
        source_path = Path(entry.source)
        if source_path.exists() and source_path.suffix == ".py":
            module_name = f"_plugin_{entry.manifest.name}_{uuid.uuid4().hex[:8]}"
            spec = importlib.util.spec_from_file_location(module_name, str(source_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load plugin module: {source_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            plugin_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin_class = obj
                    break

            if plugin_class is None:
                raise ValueError(f"No BasePlugin subclass found in {source_path}")

            instance: BasePlugin = plugin_class()
            instance.manifest = entry.manifest
            return instance

        raise ValueError(f"Cannot load plugin from {entry.source}")

    def uninstall_plugin(self, plugin_id: str) -> bool:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False

        instance = self._plugin_instances.pop(plugin_id, None)
        if instance is not None:
            try:
                instance.uninstall()
            except Exception as e:
                self._logger.error("Plugin %s uninstall hook failed: %s", entry.manifest.name, e)

        del self._plugins[plugin_id]
        self._save_index()

        source_path = Path(entry.source)
        if source_path.exists():
            try:
                import shutil
                parent = source_path.parent
                if parent.name == Path(entry.source).stem:
                    shutil.rmtree(str(parent), ignore_errors=True)
                else:
                    source_path.unlink(missing_ok=True)
            except Exception as e:
                self._logger.warning("Could not remove plugin files: %s", e)

        return True

    def enable_plugin(self, plugin_id: str) -> bool:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        entry.enabled = True
        if plugin_id not in self._plugin_instances:
            try:
                instance = self._load_plugin_instance(entry)
                self._plugin_instances[plugin_id] = instance
            except Exception as e:
                self._logger.error("Could not load plugin %s: %s", plugin_id, e)
                return False
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_index()
        return True

    def disable_plugin(self, plugin_id: str) -> bool:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        entry.enabled = False
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_index()
        return True

    def update_plugin(
        self, plugin_id: str, source: str, manifest: Optional[PluginManifest] = None
    ) -> Optional[PluginEntry]:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return None

        old_instance = self._plugin_instances.pop(plugin_id, None)
        if old_instance is not None:
            try:
                old_instance.uninstall()
            except Exception:
                pass

        if manifest is None:
            manifest = self._detect_manifest(source)
        errors = self._validate_manifest(manifest)
        if errors:
            raise ValueError(f"Invalid manifest: {'; '.join(errors)}")

        entry.source = source
        entry.manifest = manifest
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        entry.checksum = self._compute_checksum(source)
        self._save_index()

        if entry.enabled:
            try:
                instance = self._load_plugin_instance(entry)
                if instance.install():
                    self._plugin_instances[plugin_id] = instance
            except Exception as e:
                self._logger.error("Update install hook failed: %s", e)
                entry.enabled = False
                self._save_index()

        return entry

    def verify_compatibility(self, plugin_id: str) -> bool:
        entry = self._plugins.get(plugin_id)
        if entry is None:
            return False
        manifest = entry.manifest
        if not manifest.compatibility:
            return True

        try:
            compat = manifest.compatibility.replace(">=", "").replace("==", "").replace(">", "").strip()
            parts = compat.split(".")
            if len(parts) == 3:
                major = int(parts[0])
                if major > 11:
                    return False
                if major == 11 and int(parts[1]) > 1:
                    return False
            return True
        except Exception:
            return False

    def get_plugin(self, plugin_id: str) -> Optional[PluginEntry]:
        return self._plugins.get(plugin_id)

    def list_plugins(
        self, plugin_type: Optional[str] = None, enabled_only: bool = False
    ) -> List[PluginEntry]:
        results = list(self._plugins.values())
        if plugin_type:
            results = [p for p in results if p.manifest.plugin_type == plugin_type]
        if enabled_only:
            results = [p for p in results if p.enabled]
        return results

    def get_plugin_instance(self, plugin_id: str) -> Optional[BasePlugin]:
        return self._plugin_instances.get(plugin_id)

    def call_plugin_hook(self, plugin_id: str, hook: str, *args, **kwargs) -> Any:
        instance = self._plugin_instances.get(plugin_id)
        if instance is None:
            raise ValueError(f"Plugin {plugin_id} not loaded")
        method = getattr(instance, hook, None)
        if method is None:
            raise ValueError(f"Plugin {plugin_id} has no hook {hook}")
        return method(*args, **kwargs)


def get_plugin_registry() -> PluginRegistry:
    return PluginRegistry()

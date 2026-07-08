"""Base Plugin SDK — PluginManifest, BasePlugin, and PluginType for the plugin system."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PluginType(str, Enum):
    TOOL = "tool"
    EXTENSION = "extension"
    WORKFLOW = "workflow"
    CONNECTOR = "connector"
    ANALYTICS = "analytics"
    UI = "ui"

    @classmethod
    def _missing_(cls, value: object) -> "PluginType | None":
        for member in cls:
            if member.value == value:
                return member
        return None


@dataclass
class PluginManifest:
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    entry_point: str = ""
    plugin_type: str = "tool"
    compatibility: str = ">=11.0.0"
    permissions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    icon: str = ""
    license: str = "MIT"
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "entry_point": self.entry_point,
            "plugin_type": self.plugin_type,
            "compatibility": self.compatibility,
            "permissions": self.permissions,
            "tags": self.tags,
            "icon": self.icon,
            "license": self.license,
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            entry_point=data.get("entry_point", ""),
            plugin_type=data.get("plugin_type", "tool"),
            compatibility=data.get("compatibility", ">=11.0.0"),
            permissions=data.get("permissions", []),
            tags=data.get("tags", []),
            icon=data.get("icon", ""),
            license=data.get("license", "MIT"),
            dependencies=data.get("dependencies", []),
        )


class BasePlugin:
    """Base class for all plugins. Subclass to create a custom plugin."""

    def __init__(self) -> None:
        self.manifest: PluginManifest = PluginManifest()

    def install(self) -> bool:
        """Called when the plugin is installed. Return True on success."""
        return True

    def uninstall(self) -> bool:
        """Called when the plugin is uninstalled. Return True on success."""
        return True

    def activate(self) -> bool:
        """Called when the plugin is activated/enabled. Return True on success."""
        return True

    def deactivate(self) -> bool:
        """Called when the plugin is deactivated/disabled. Return True on success."""
        return True

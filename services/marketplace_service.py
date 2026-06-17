"""Marketplace Service — publish, search, install, rate, and manage packages."""
import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


from sdk.plugin_sdk.base_plugin import PluginManifest


@dataclass
class MarketplacePackage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    package_type: str = "plugin"
    manifest: Optional[PluginManifest] = None
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0
    tags: List[str] = field(default_factory=list)
    published_at: str = ""
    updated_at: str = ""
    source_url: str = ""
    readme: str = ""
    compatibility: str = ">=11.0.0"
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("manifest", None)
        if self.manifest:
            d["manifest"] = self.manifest.to_dict()
        return d


class MarketplaceService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, storage_dir: str = "marketplace_data"):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._packages: Dict[str, MarketplacePackage] = {}
        self._local_dir = self.storage_dir / "local"
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger("MarketplaceService")
        self._load_index()

    def _index_path(self) -> Path:
        return self.storage_dir / "packages.json"

    def _load_index(self) -> None:
        path = self._index_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data:
                    manifest_data = item.pop("manifest", None)
                    pkg = MarketplacePackage(**{k: v for k, v in item.items() if k in MarketplacePackage.__dataclass_fields__})
                    if manifest_data:
                        try:
                            pkg.manifest = PluginManifest.from_dict(manifest_data)
                        except Exception:
                            pass
                    self._packages[pkg.id] = pkg
            except Exception as e:
                self._logger.warning("Failed to load marketplace index: %s", e)

    def _save_index(self) -> None:
        data = [pkg.to_dict() for pkg in self._packages.values()]
        self._index_path().write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )

    def publish_package(
        self,
        name: str,
        version: str,
        author: str,
        description: str,
        source_path: str,
        package_type: str = "plugin",
        tags: Optional[List[str]] = None,
        readme: str = "",
        manifest: Optional[PluginManifest] = None,
    ) -> MarketplacePackage:
        pkg_id = str(uuid.uuid4())
        pkg_dir = self._local_dir / name.replace(" ", "_").lower()
        pkg_dir.mkdir(parents=True, exist_ok=True)

        source = Path(source_path)
        if source.exists():
            if source.is_file():
                shutil.copy2(str(source), str(pkg_dir / source.name))
            elif source.is_dir():
                for item in source.iterdir():
                    if item.is_file():
                        shutil.copy2(str(item), str(pkg_dir / item.name))

        if manifest is None:
            manifest = PluginManifest(
                name=name, version=version, author=author, description=description
            )

        pkg = MarketplacePackage(
            id=pkg_id,
            name=name,
            version=version,
            author=author,
            description=description,
            package_type=package_type,
            manifest=manifest,
            tags=tags or [],
            published_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            source_url=str(pkg_dir),
            readme=readme,
            compatibility=manifest.compatibility,
            verified=False,
        )

        self._packages[pkg_id] = pkg
        self._save_index()
        return pkg

    def search_packages(
        self,
        query: str = "",
        package_type: Optional[str] = None,
        tag: Optional[str] = None,
        author: Optional[str] = None,
        min_rating: float = 0.0,
        sort_by: str = "downloads",
        limit: int = 50,
    ) -> List[MarketplacePackage]:
        results = list(self._packages.values())

        if query:
            q = query.lower()
            results = [
                p
                for p in results
                if q in p.name.lower()
                or q in p.description.lower()
                or q in p.author.lower()
                or q in p.tags
            ]

        if package_type:
            results = [p for p in results if p.package_type == package_type]
        if tag:
            results = [p for p in results if tag in p.tags]
        if author:
            results = [p for p in results if p.author.lower() == author.lower()]
        if min_rating > 0:
            results = [p for p in results if p.rating >= min_rating]

        sort_map = {
            "downloads": lambda p: p.downloads,
            "rating": lambda p: p.rating,
            "name": lambda p: p.name.lower(),
            "updated": lambda p: p.updated_at or "",
            "published": lambda p: p.published_at or "",
        }
        sort_fn = sort_map.get(sort_by, sort_map["downloads"])
        reverse = sort_by not in ("name",)
        results.sort(key=sort_fn, reverse=reverse)

        return results[:limit]

    def get_package(self, package_id: str) -> Optional[MarketplacePackage]:
        return self._packages.get(package_id)

    def get_package_by_name(self, name: str) -> Optional[MarketplacePackage]:
        for pkg in self._packages.values():
            if pkg.name.lower() == name.lower():
                return pkg
        return None

    def update_package(self, package_id: str, **kwargs) -> Optional[MarketplacePackage]:
        pkg = self._packages.get(package_id)
        if pkg is None:
            return None
        for key, value in kwargs.items():
            if hasattr(pkg, key) and value is not None:
                setattr(pkg, key, value)
        pkg.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_index()
        return pkg

    def delete_package(self, package_id: str) -> bool:
        pkg = self._packages.pop(package_id, None)
        if pkg is None:
            return False
        pkg_dir = Path(pkg.source_url) if pkg.source_url else None
        if pkg_dir and pkg_dir.exists():
            shutil.rmtree(str(pkg_dir), ignore_errors=True)
        self._save_index()
        return True

    def rate_package(self, package_id: str, rating: float) -> Optional[MarketplacePackage]:
        pkg = self._packages.get(package_id)
        if pkg is None:
            return None
        rating = max(0.0, min(5.0, rating))
        total = pkg.rating * pkg.rating_count + rating
        pkg.rating_count += 1
        pkg.rating = round(total / pkg.rating_count, 2)
        pkg.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_index()
        return pkg

    def record_download(self, package_id: str) -> None:
        pkg = self._packages.get(package_id)
        if pkg:
            pkg.downloads += 1
            self._save_index()

    def install_package(
        self, package_id: str, target_dir: str = "plugins"
    ) -> Optional[str]:
        pkg = self._packages.get(package_id)
        if pkg is None:
            return None

        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        pkg_dir = Path(pkg.source_url)
        if not pkg_dir.exists():
            return None

        install_path = target / pkg.name.replace(" ", "_").lower()
        install_path.mkdir(parents=True, exist_ok=True)

        for item in pkg_dir.iterdir():
            if item.is_file():
                shutil.copy2(str(item), str(install_path / item.name))

        manifest_file = install_path / "plugin.yaml"
        if pkg.manifest:
            manifest_file.write_text(pkg.manifest.to_yaml(), encoding="utf-8")

        self.record_download(package_id)
        return str(install_path)

    def list_packages(
        self, package_type: Optional[str] = None, verified_only: bool = False
    ) -> List[MarketplacePackage]:
        results = list(self._packages.values())
        if package_type:
            results = [p for p in results if p.package_type == package_type]
        if verified_only:
            results = [p for p in results if p.verified]
        return results


def get_marketplace_service() -> MarketplaceService:
    return MarketplaceService()

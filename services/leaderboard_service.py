"""Leaderboard Service — track and rank models, workflows, agents, and benchmark packs by autonomy, reliability, and cost efficiency."""
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class LeaderboardEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = ""
    name: str = ""
    version: str = "1.0.0"
    autonomy_score: float = 0.0
    reliability_score: float = 0.0
    cost_efficiency_score: float = 0.0
    overall_score: float = 0.0
    run_count: int = 0
    last_run: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LeaderboardService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._entries: dict[str, LeaderboardEntry] = {}
        self._logger = logging.getLogger("LeaderboardService")
        self._storage_dir = Path("evaluation_data")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_entries()

    def _entries_path(self) -> Path:
        return self._storage_dir / "leaderboard.json"

    def _load_entries(self) -> None:
        path = self._entries_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data:
                    entry = LeaderboardEntry(**{k: v for k, v in item.items() if k in LeaderboardEntry.__dataclass_fields__})
                    self._entries[entry.id] = entry
            except Exception as e:
                self._logger.warning("Failed to load leaderboard: %s", e)

    def _save_entries(self) -> None:
        data = [e.to_dict() for e in self._entries.values()]
        self._entries_path().write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def record_entry(
        self,
        category: str,
        name: str,
        version: str = "1.0.0",
        autonomy_score: float = 0.0,
        reliability_score: float = 0.0,
        cost_efficiency_score: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> LeaderboardEntry:
        overall = (autonomy_score * 0.4 + reliability_score * 0.35 + cost_efficiency_score * 0.25)

        existing = self._find_entry(category, name)
        if existing:
            existing.autonomy_score = (existing.autonomy_score * existing.run_count + autonomy_score) / (existing.run_count + 1)
            existing.reliability_score = (existing.reliability_score * existing.run_count + reliability_score) / (existing.run_count + 1)
            existing.cost_efficiency_score = (existing.cost_efficiency_score * existing.run_count + cost_efficiency_score) / (existing.run_count + 1)
            existing.overall_score = (existing.autonomy_score * 0.4 + existing.reliability_score * 0.35 + existing.cost_efficiency_score * 0.25)
            existing.run_count += 1
            existing.last_run = datetime.utcnow().isoformat()
            if metadata:
                existing.metadata.update(metadata)
            entry = existing
        else:
            entry = LeaderboardEntry(
                category=category,
                name=name,
                version=version,
                autonomy_score=autonomy_score,
                reliability_score=reliability_score,
                cost_efficiency_score=cost_efficiency_score,
                overall_score=overall,
                run_count=1,
                last_run=datetime.utcnow().isoformat(),
                metadata=metadata or {},
            )
            self._entries[entry.id] = entry

        self._save_entries()
        return entry

    def _find_entry(self, category: str, name: str) -> LeaderboardEntry | None:
        for entry in self._entries.values():
            if entry.category == category and entry.name == name:
                return entry
        return None

    def get_leaderboard(
        self,
        category: str | None = None,
        sort_by: str = "overall_score",
        limit: int = 20,
    ) -> list[LeaderboardEntry]:
        results = list(self._entries.values())
        if category:
            results = [e for e in results if e.category == category]

        sort_map = {
            "overall_score": lambda e: e.overall_score,
            "autonomy_score": lambda e: e.autonomy_score,
            "reliability_score": lambda e: e.reliability_score,
            "cost_efficiency_score": lambda e: e.cost_efficiency_score,
            "run_count": lambda e: e.run_count,
        }
        sort_fn = sort_map.get(sort_by, sort_map["overall_score"])
        results.sort(key=sort_fn, reverse=True)
        return results[:limit]

    def get_entry(self, entry_id: str) -> LeaderboardEntry | None:
        return self._entries.get(entry_id)

    def get_categories(self) -> list[str]:
        return list(set(e.category for e in self._entries.values()))

    def delete_entry(self, entry_id: str) -> bool:
        entry = self._entries.pop(entry_id, None)
        if entry:
            self._save_entries()
            return True
        return False


def get_leaderboard_service() -> LeaderboardService:
    return LeaderboardService()

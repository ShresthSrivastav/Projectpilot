"""Base Benchmark SDK — interface for creating custom benchmark packs."""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkCriteria:
    name: str = ""
    description: str = ""
    weight: float = 1.0
    expected: Any = None
    evaluator: str = "exact_match"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkCriteria":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BenchmarkTest:
    name: str = ""
    description: str = ""
    command: str = ""
    expected_output: str = ""
    timeout: int = 60

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseBenchmarkPack(ABC):
    def __init__(self, domain: str = "", pack_dir: Path | None = None):
        self.domain = domain or self.__class__.__name__.lower()
        self.pack_dir = pack_dir or Path(f"benchmarks/{self.domain}")
        self.criteria: list[BenchmarkCriteria] = []
        self.tests: list[BenchmarkTest] = []
        self._logger = logging.getLogger(f"benchmark.{self.domain}")

    @abstractmethod
    def load_requirements(self) -> str:
        ...

    @abstractmethod
    def load_tests(self) -> list[BenchmarkTest]:
        ...

    @abstractmethod
    def load_criteria(self) -> list[BenchmarkCriteria]:
        ...

    @abstractmethod
    def evaluate(self, results: dict[str, Any]) -> dict[str, Any]:
        ...

    def get_manifest(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "pack_dir": str(self.pack_dir),
            "criteria_count": len(self.criteria),
            "test_count": len(self.tests),
        }

    def load_from_directory(self) -> bool:
        if not self.pack_dir.exists():
            return False
        req_file = self.pack_dir / "requirements.md"
        if req_file.exists():
            self.load_requirements()
        test_file = self.pack_dir / "tests.py"
        if test_file.exists():
            self.tests = self.load_tests()
        criteria_file = self.pack_dir / "criteria.json"
        if criteria_file.exists():
            try:
                data = json.loads(criteria_file.read_text(encoding="utf-8"))
                self.criteria = [BenchmarkCriteria.from_dict(c) for c in data]
            except Exception:
                pass
        return True

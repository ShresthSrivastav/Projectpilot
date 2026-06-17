"""Base Benchmark SDK — interface for creating custom benchmark packs."""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BenchmarkCriteria:
    name: str = ""
    description: str = ""
    weight: float = 1.0
    expected: Any = None
    evaluator: str = "exact_match"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BenchmarkCriteria":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BenchmarkTest:
    name: str = ""
    description: str = ""
    command: str = ""
    expected_output: str = ""
    timeout: int = 60

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseBenchmarkPack(ABC):
    def __init__(self, domain: str = "", pack_dir: Optional[Path] = None):
        self.domain = domain or self.__class__.__name__.lower()
        self.pack_dir = pack_dir or Path(f"benchmarks/{self.domain}")
        self.criteria: List[BenchmarkCriteria] = []
        self.tests: List[BenchmarkTest] = []
        self._logger = logging.getLogger(f"benchmark.{self.domain}")

    @abstractmethod
    def load_requirements(self) -> str:
        ...

    @abstractmethod
    def load_tests(self) -> List[BenchmarkTest]:
        ...

    @abstractmethod
    def load_criteria(self) -> List[BenchmarkCriteria]:
        ...

    @abstractmethod
    def evaluate(self, results: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def get_manifest(self) -> Dict[str, Any]:
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

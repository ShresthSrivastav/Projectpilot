"""Learning Engine — store, retrieve, rank, recommend successful patterns from past runs."""
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.memory_store import (
    record_fix_pattern, get_fix_patterns,
    save_project_insight, get_project_insights,
)

logger = logging.getLogger(__name__)

LEARNING_DIR = Path(os.getenv("LEARNING_DIR", "./learning_data"))


class PatternType(Enum):
    FIX = "fix"
    ARCHITECTURE = "architecture"
    DEPLOYMENT = "deployment"
    PROMPT = "prompt"
    AGENT_DECISION = "agent_decision"
    TEST = "test"
    CONFIG = "config"
    PERFORMANCE = "performance"


@dataclass
class LearnedPattern:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pattern_type: str = ""
    key: str = ""
    value: str = ""
    success_count: int = 1
    confidence: float = 1.0
    tags: List[str] = field(default_factory=list)
    job_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


class LearningEngine:
    def __init__(self):
        self.patterns: Dict[str, LearnedPattern] = {}
        self._lock = threading.Lock()
        self._index: Dict[str, List[str]] = defaultdict(list)
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
        self._load_patterns()

    def learn_fix(self, error_type: str, error_text: str, fix: str, file_pattern: str = "",
                   job_id: str = "") -> None:
        try:
            record_fix_pattern(error_type, error_text[:200], file_pattern, fix[:500])
            key = f"fix:{error_type}:{hash(error_text[:100])}"
            self._store_pattern(PatternType.FIX, key, fix, tags=[error_type, file_pattern], job_id=job_id)
            logger.debug("Learned fix pattern: %s", error_type)
        except Exception as exc:
            logger.warning("Learn fix failed: %s", exc)

    def learn_architecture(self, description: str, blueprint: Dict, job_id: str = "") -> None:
        try:
            key = f"arch:{hash(description[:100])}"
            self._store_pattern(PatternType.ARCHITECTURE, key, json.dumps(blueprint),
                                tags=[t.get("tech", "") for t in blueprint.get("tech_stack", {}).values() if isinstance(t, dict)],
                                job_id=job_id)
            save_project_insight(job_id, "architecture", description[:200], json.dumps(blueprint)[:1000])
        except Exception as exc:
            logger.warning("Learn architecture failed: %s", exc)

    def learn_deployment(self, target: str, config: Dict, success: bool, job_id: str = "") -> None:
        if success:
            key = f"deploy:{target}:{hash(json.dumps(config, sort_keys=True)[:100])}"
            self._store_pattern(PatternType.DEPLOYMENT, key, json.dumps(config),
                                tags=[target, "success"], job_id=job_id)

    def learn_prompt(self, prompt: str, response: str, score: float, job_id: str = "") -> None:
        if score > 0.7:
            key = f"prompt:{hash(prompt[:100])}"
            self._store_pattern(PatternType.PROMPT, key, response[:1000],
                                tags=[f"score:{score:.2f}"], confidence=score, job_id=job_id)

    def learn_agent_decision(self, agent_name: str, context: str, decision: str,
                               outcome: str, job_id: str = "") -> None:
        if outcome == "success":
            key = f"agent:{agent_name}:{hash(context[:100])}"
            self._store_pattern(PatternType.AGENT_DECISION, key, decision,
                                tags=[agent_name, outcome], job_id=job_id)

    def _store_pattern(self, ptype: PatternType, key: str, value: str,
                       tags: Optional[List[str]] = None, confidence: float = 1.0,
                       job_id: str = "") -> None:
        tags = tags or []
        with self._lock:
            existing = self.patterns.get(key)
            if existing:
                existing.success_count += 1
                existing.confidence = min(existing.confidence + 0.05, 1.0)
                existing.last_used = time.time()
                if job_id and job_id not in existing.metadata.get("job_ids", []):
                    existing.metadata.setdefault("job_ids", []).append(job_id)
            else:
                pattern = LearnedPattern(
                    pattern_type=ptype.value, key=key, value=value[:2000],
                    tags=tags, confidence=confidence, job_id=job_id,
                )
                self.patterns[key] = pattern
                for tag in tags:
                    self._index[tag].append(key)
        self._save_patterns()

    def retrieve_fixes(self, error_type: Optional[str] = None, limit: int = 10) -> List[Dict]:
        try:
            results = get_fix_patterns(error_type=error_type, limit=limit)
            return [dict(r) for r in results]
        except Exception:
            return []

    def recommend_architecture(self, tech_stack: Optional[List[str]] = None, limit: int = 5) -> List[Dict]:
        return self._search(PatternType.ARCHITECTURE, tech_stack, limit)

    def recommend_deployment(self, target: Optional[str] = None, limit: int = 5) -> List[Dict]:
        return self._search(PatternType.DEPLOYMENT, [target] if target else None, limit)

    def recommend_prompts(self, score_min: float = 0.7, limit: int = 5) -> List[Dict]:
        with self._lock:
            candidates = [p for p in self.patterns.values()
                         if p.pattern_type == PatternType.PROMPT.value and p.confidence >= score_min]
            candidates.sort(key=lambda p: p.confidence, reverse=True)
            return [p.to_dict() for p in candidates[:limit]]

    def _search(self, ptype: PatternType, tags: Optional[List[str]], limit: int) -> List[Dict]:
        with self._lock:
            candidates = [p for p in self.patterns.values() if p.pattern_type == ptype.value]
            if tags:
                candidates = [p for p in candidates if any(t in p.tags for t in tags)]
            candidates.sort(key=lambda p: (p.confidence, p.success_count), reverse=True)
            return [p.to_dict() for p in candidates[:limit]]

    def get_statistics(self) -> Dict[str, Any]:
        with self._lock:
            type_counts = defaultdict(int)
            for p in self.patterns.values():
                type_counts[p.pattern_type] += 1
            return {
                "total_patterns": len(self.patterns),
                "by_type": dict(type_counts),
                "total_fixes": sum(1 for p in self.patterns.values() if p.pattern_type == PatternType.FIX.value),
                "total_architectures": sum(1 for p in self.patterns.values() if p.pattern_type == PatternType.ARCHITECTURE.value),
                "total_deployments": sum(1 for p in self.patterns.values() if p.pattern_type == PatternType.DEPLOYMENT.value),
                "top_tags": dict(sorted(self._index.items(), key=lambda x: -len(x[1]))[:10]),
            }

    def get_context_for_job(self, job_id: str) -> Dict[str, Any]:
        fixes = self.retrieve_fixes(limit=5)
        archs = self.recommend_architecture(limit=3)
        prompts = self.recommend_prompts(limit=3)
        insights = get_project_insights(limit=10)
        return {
            "previous_fixes": fixes,
            "recommended_architectures": archs,
            "recommended_prompts": prompts,
            "project_insights": insights,
            "total_patterns_available": len(self.patterns),
        }

    def _save_patterns(self) -> None:
        try:
            path = LEARNING_DIR / "patterns.json"
            with self._lock:
                data = {k: p.to_dict() for k, p in self.patterns.items()}
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Patterns save failed: %s", exc)

    def _load_patterns(self) -> None:
        path = LEARNING_DIR / "patterns.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            with self._lock:
                for key, pdata in data.items():
                    p = LearnedPattern(**pdata)
                    self.patterns[key] = p
                    for tag in p.tags:
                        self._index[tag].append(key)
            logger.info("Loaded %d learned patterns", len(data))
        except Exception as exc:
            logger.warning("Patterns load failed: %s", exc)


_learning_engine = LearningEngine()


def get_learning_engine() -> LearningEngine:
    return _learning_engine

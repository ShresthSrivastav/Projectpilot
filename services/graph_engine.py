"""Task Graph Execution Engine — DAG-based planning, parallel execution, checkpointing, recovery."""
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = os.getenv("GRAPH_CHECKPOINT_DIR", "./graph_checkpoints")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    deps: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    agent_func: Callable | None = None
    agent_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    kwargs: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: float = 0.0
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_data: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        d["agent_func"] = None
        return d

    @staticmethod
    def from_dict(data: dict) -> "Task":
        t = Task(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            priority=TaskPriority(data.get("priority", 2)),
            status=TaskStatus(data.get("status", "pending")),
            deps=data.get("deps", []),
            dependents=data.get("dependents", []),
            agent_name=data.get("agent_name", ""),
            args=data.get("args", {}),
            kwargs=data.get("kwargs", {}),
            result=data.get("result"),
            error=data.get("error"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            duration_ms=data.get("duration_ms", 0.0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            metadata=data.get("metadata", {}),
            checkpoint_data=data.get("checkpoint_data"),
        )
        t.agent_func = None
        return t


@dataclass
class Checkpoint:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    graph_id: str = ""
    tasks: dict[str, dict] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskGraph:
    def __init__(self, graph_id: str | None = None):
        self.id = graph_id or str(uuid.uuid4())
        self.tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._event_handlers: dict[str, list[Callable]] = defaultdict(list)
        self._execution_graph: dict[str, list[str]] = defaultdict(list)
        self.metadata: dict[str, Any] = {}
        Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
        logger.info("TaskGraph %s initialized", self.id[:8])

    def add_task(self, task: Task) -> str:
        with self._lock:
            self.tasks[task.id] = task
            for dep_id in task.deps:
                if dep_id in self.tasks:
                    self.tasks[dep_id].dependents.append(task.id)
                    self._execution_graph[task.id].append(dep_id)
            self._emit("task_added", task.to_dict())
        return task.id

    def add_dependency(self, task_id: str, depends_on: str) -> None:
        with self._lock:
            if task_id not in self.tasks or depends_on not in self.tasks:
                raise ValueError(f"Task {task_id} or dependency {depends_on} not found")
            if depends_on in self.tasks[task_id].deps:
                return
            self.tasks[task_id].deps.append(depends_on)
            self.tasks[depends_on].dependents.append(task_id)
            self._execution_graph[task_id].append(depends_on)
            self._emit("dependency_added", {"task_id": task_id, "depends_on": depends_on})

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def get_ready_tasks(self) -> list[Task]:
        with self._lock:
            ready = []
            for t in self.tasks.values():
                if t.status != TaskStatus.PENDING:
                    continue
                if all(
                    self.tasks[d].status == TaskStatus.COMPLETED
                    for d in t.deps if d in self.tasks
                ):
                    ready.append(t)
            return ready

    def get_blocked_tasks(self) -> list[Task]:
        with self._lock:
            blocked = []
            for t in self.tasks.values():
                if t.status != TaskStatus.PENDING:
                    continue
                if any(
                    self.tasks[d].status == TaskStatus.FAILED
                    for d in t.deps if d in self.tasks
                ):
                    blocked.append(t)
            return blocked

    def mark_running(self, task_id: str) -> None:
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.RUNNING
                self.tasks[task_id].started_at = time.time()
                self._emit("task_running", {"task_id": task_id})

    def mark_completed(self, task_id: str, result: Any = None) -> None:
        with self._lock:
            if task_id in self.tasks:
                t = self.tasks[task_id]
                t.status = TaskStatus.COMPLETED
                t.completed_at = time.time()
                t.duration_ms = (t.completed_at - (t.started_at or t.completed_at)) * 1000
                t.result = result
                self._emit("task_completed", {"task_id": task_id, "result": str(result)[:200]})

    def mark_failed(self, task_id: str, error: str) -> None:
        with self._lock:
            if task_id in self.tasks:
                t = self.tasks[task_id]
                t.status = TaskStatus.FAILED
                t.completed_at = time.time()
                t.duration_ms = (t.completed_at - (t.started_at or t.completed_at)) * 1000
                t.error = error
                self._emit("task_failed", {"task_id": task_id, "error": error[:200]})

    def mark_skipped(self, task_id: str) -> None:
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.SKIPPED
                self._emit("task_skipped", {"task_id": task_id})

    def get_topological_order(self) -> list[str]:
        with self._lock:
            in_degree = {tid: len(t.deps) for tid, t in self.tasks.items()}
            queue = deque([tid for tid, d in in_degree.items() if d == 0])
            order = []
            while queue:
                tid = queue.popleft()
                order.append(tid)
                for dep in self.tasks[tid].dependents:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)
            if len(order) != len(self.tasks):
                logger.warning("Graph %s has cycles — %d/%d tasks ordered", self.id[:8], len(order), len(self.tasks))
            return order

    def get_critical_path(self) -> list[Task]:
        order = self.get_topological_order()
        dist = dict.fromkeys(self.tasks, 0)
        prev = dict.fromkeys(self.tasks)
        for tid in order:
            for dep in self.tasks[tid].dependents:
                cost = 1 + self.tasks[tid].duration_ms / 1000.0
                if dist[dep] < dist[tid] + cost:
                    dist[dep] = dist[tid] + cost
                    prev[dep] = tid
        max_tid = max(dist, key=lambda k: dist[k])
        path = []
        while max_tid:
            path.append(self.tasks[max_tid])
            max_tid = prev[max_tid]
        return list(reversed(path))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "topological_order": self.get_topological_order(),
            "critical_path": [t.id for t in self.get_critical_path()],
            "execution_graph": dict(self._execution_graph),
            "metadata": self.metadata,
            "task_count": len(self.tasks),
            "completed_count": sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED),
            "failed_count": sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED),
            "running_count": sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING),
            "pending_count": sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING),
        }

    def save_checkpoint(self) -> Checkpoint:
        cp = Checkpoint(
            graph_id=self.id,
            tasks={tid: t.to_dict() for tid, t in self.tasks.items()},
        )
        path = Path(CHECKPOINT_DIR) / f"graph_{self.id[:8]}_{cp.id[:8]}.json"
        with open(path, "w") as f:
            json.dump(asdict(cp), f, indent=2, default=str)
        logger.info("Checkpoint %s saved (%d tasks)", cp.id[:8], len(self.tasks))
        self._emit("checkpoint_saved", {"checkpoint_id": cp.id, "path": str(path)})
        return cp

    def load_checkpoint(self, checkpoint_id: str) -> Optional["TaskGraph"]:
        for fpath in Path(CHECKPOINT_DIR).glob("graph_*.json"):
            try:
                data = json.loads(fpath.read_text())
                if data.get("id") == checkpoint_id:
                    graph = TaskGraph(graph_id=data.get("graph_id", self.id))
                    for tid, tdata in data.get("tasks", {}).items():
                        graph.tasks[tid] = Task.from_dict(tdata)
                    logger.info("Loaded checkpoint %s (%d tasks)", checkpoint_id[:8], len(graph.tasks))
                    return graph
            except Exception as exc:
                logger.warning("Failed loading checkpoint %s: %s", fpath, exc)
        return None

    def list_checkpoints(self) -> list[dict]:
        checkpoints = []
        for fpath in sorted(Path(CHECKPOINT_DIR).glob("graph_*.json")):
            try:
                data = json.loads(fpath.read_text())
                checkpoints.append({
                    "checkpoint_id": data.get("id", ""),
                    "graph_id": data.get("graph_id", ""),
                    "created_at": data.get("created_at", 0),
                    "task_count": len(data.get("tasks", {})),
                    "path": str(fpath),
                })
            except Exception:
                pass
        return checkpoints

    def visualize_mermaid(self) -> str:
        lines = ["graph TD;"]
        for tid, t in self.tasks.items():
            status_icon = {"completed": "✅", "failed": "❌", "running": "⏳", "pending": "⬜", "skipped": "⏭️", "blocked": "🚫"}
            icon = status_icon.get(t.status.value, "⬜")
            label = f"{tid[:6]}({t.name or t.id[:6]})"
            lines.append(f"    {tid[:8]}[{icon} {label}]")
        for tid, t in self.tasks.items():
            for dep in t.deps:
                lines.append(f"    {dep[:8]} --> {tid[:8]}")
        return "\n".join(lines)

    def subscribe(self, event: str, handler: Callable) -> None:
        self._event_handlers[event].append(handler)

    def _emit(self, event: str, data: Any) -> None:
        for handler in self._event_handlers.get(event, []):
            try:
                handler(event, data)
            except Exception as exc:
                logger.warning("Event handler failed: %s", exc)


class GraphExecutor:
    def __init__(self, graph: TaskGraph, max_workers: int = 4):
        self.graph = graph
        self.max_workers = max_workers
        self._running = False
        self._lock = threading.Lock()
        self._workers: dict[str, threading.Thread] = {}

    def execute(self, task_timeout: float | None = None) -> dict[str, Any]:
        self._running = True
        results = {}
        errors = {}

        def _run_task(task: Task) -> None:
            if not self._running:
                return
            self.graph.mark_running(task.id)
            logger.info("Executing task: %s (%s)", task.name or task.id[:8], task.agent_name)
            try:
                func = task.agent_func
                if func:
                    loop = None
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        pass
                    if loop and loop.is_running():
                        fut = asyncio.run_coroutine_threadsafe(
                            self._async_wrap(func, task), loop
                        )
                        result = fut.result(timeout=task_timeout or 300)
                    else:
                        if asyncio.iscoroutinefunction(func):
                            result = asyncio.run(func(**task.kwargs))
                        else:
                            result = func(**task.kwargs)
                else:
                    result = None
                self.graph.mark_completed(task.id, result)
                results[task.id] = result
            except Exception as exc:
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    self.graph.mark_failed(task.id, str(exc))
                    errors[task.id] = str(exc)
                    logger.error("Task %s failed after %d retries: %s", task.id[:8], task.retry_count, exc)
                else:
                    logger.warning("Task %s failed (retry %d/%d): %s", task.id[:8], task.retry_count, task.max_retries, exc)

        while self._running:
            ready = self.graph.get_ready_tasks()
            blocked = self.graph.get_blocked_tasks()
            for b in blocked:
                self.graph.mark_skipped(b.id)
            if not ready:
                remaining = [t for t in self.graph.tasks.values() if t.status == TaskStatus.RUNNING]
                if not remaining:
                    break
                time.sleep(0.1)
                continue
            batch = ready[:self.max_workers]
            threads = []
            for task in batch:
                t = threading.Thread(target=_run_task, args=(task,), daemon=True)
                t.start()
                threads.append(t)
            for t in threads:
                t.join(timeout=task_timeout or 300)
            self.graph.save_checkpoint()

        self._running = False
        return {"results": results, "errors": errors}

    async def _async_wrap(self, func: Callable, task: Task) -> Any:
        if asyncio.iscoroutinefunction(func):
            return await func(**task.kwargs)
        return func(**task.kwargs)

    def cancel(self) -> None:
        self._running = False
        logger.info("Graph execution cancelled")

    def get_status(self) -> dict:
        return self.graph.to_dict()

    def resume_from_checkpoint(self, checkpoint_id: str) -> Optional["GraphExecutor"]:
        loaded = self.graph.load_checkpoint(checkpoint_id)
        if loaded:
            return GraphExecutor(loaded, max_workers=self.max_workers)
        return None


class PlanBuilder:
    def __init__(self):
        self.graph = TaskGraph()
        self._task_counter = 0

    def add_stage(self, name: str, agent_name: str, deps: list[str] | None = None,
                  priority: TaskPriority = TaskPriority.NORMAL,
                  description: str = "", **kwargs) -> str:
        deps = deps or []
        task = Task(
            name=name,
            description=description,
            priority=priority,
            deps=deps,
            agent_name=agent_name,
            kwargs=kwargs,
        )
        self._task_counter += 1
        return self.graph.add_task(task)

    def build_standard_plan(self, prompt: str, job_id: str, model: str = "local",
                            stack: dict | None = None) -> TaskGraph:
        self.graph.metadata = {"prompt": prompt[:200], "job_id": job_id, "model": model}
        req_id = self.add_stage("Requirements Analysis", "RequirementAgent",
                                description="Analyze requirements from user prompt",
                                prompt=prompt, job_id=job_id, model=model, stack=stack)
        plan_id = self.add_stage("Project Planning", "PlannerAgent", deps=[req_id],
                                 description="Create project blueprint",
                                 job_id=job_id, model=model)
        code_id = self.add_stage("Code Generation", "CodeAgent", deps=[plan_id],
                                 description="Generate code from blueprint",
                                 job_id=job_id, model=model)
        test_id = self.add_stage("Test Generation", "TestGenAgent", deps=[code_id],
                                 description="Generate tests",
                                 job_id=job_id, model=model)
        self.add_stage("Security Scan", "SecurityAgent", deps=[code_id],
                       priority=TaskPriority.NORMAL,
                       description="Scan for security issues",
                       job_id=job_id, model=model)
        review_id = self.add_stage("Code Review", "ValidationAgent", deps=[code_id, test_id],
                                   description="Review code and tests",
                                   job_id=job_id)
        self.add_stage("Debug & Fix", "DebugAgent", deps=[test_id, review_id],
                       description="Fix test failures",
                       job_id=job_id, model=model)
        self.add_stage("Documentation", "DocsAgent", deps=[code_id, review_id],
                                 priority=TaskPriority.LOW,
                                 description="Generate docs",
                                 job_id=job_id, model=model)
        return self.graph


def create_pipeline_graph(prompt: str, job_id: str, model: str = "local",
                           stack: dict | None = None) -> TaskGraph:
    builder = PlanBuilder()
    return builder.build_standard_plan(prompt, job_id, model, stack)


def execute_graph(graph: TaskGraph, max_workers: int = 4,
                  task_timeout: float | None = None) -> dict[str, Any]:
    executor = GraphExecutor(graph, max_workers=max_workers)
    return executor.execute(task_timeout=task_timeout)

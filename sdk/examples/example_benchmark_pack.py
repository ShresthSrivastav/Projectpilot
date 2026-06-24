"""Example Benchmark Pack — Flutter UI Benchmark.
Shows how any developer can create a custom benchmark pack without modifying platform source code.
"""

from typing import Any

from sdk.benchmark_sdk.base_benchmark import BaseBenchmarkPack, BenchmarkCriteria, BenchmarkTest


class FlutterBenchmarkPack(BaseBenchmarkPack):
    def __init__(self):
        super().__init__(domain="flutter_ui")
        self.criteria = self.load_criteria()
        self.tests = self.load_tests()

    def load_requirements(self) -> str:
        return """
# Flutter Benchmark Pack Requirements
- Flutter SDK 3.0+
- Dart SDK 2.18+
- A running emulator or device
- flutter_test package
"""

    def load_tests(self) -> list[BenchmarkTest]:
        return [
            BenchmarkTest(
                name="widget-rendering",
                description="Tests widget rendering performance",
                command="flutter test test/widget_benchmark.dart",
                expected_output="All benchmarks passed",
                timeout=120,
            ),
            BenchmarkTest(
                name="state-management",
                description="Tests state management overhead",
                command="flutter test test/state_benchmark.dart",
                expected_output="State updates within threshold",
                timeout=60,
            ),
        ]

    def load_criteria(self) -> list[BenchmarkCriteria]:
        return [
            BenchmarkCriteria(
                name="render_time",
                description="Widget render time under 16ms",
                weight=2.0,
                expected={"max_render_ms": 16},
                evaluator="threshold",
            ),
            BenchmarkCriteria(
                name="memory_usage",
                description="Memory usage under 50MB",
                weight=1.5,
                expected={"max_memory_mb": 50},
                evaluator="threshold",
            ),
        ]

    def evaluate(self, results: dict[str, Any]) -> dict[str, Any]:
        scores = {}
        for criterion in self.criteria:
            actual = results.get(criterion.name, {})
            expected = criterion.expected
            if criterion.evaluator == "threshold":
                actual_val = actual.get("value", 0)
                expected_val = expected.get(list(expected.keys())[0], 0)
                scores[criterion.name] = 1.0 if actual_val <= expected_val else 0.0
            else:
                scores[criterion.name] = 1.0 if actual == expected else 0.0
        total = sum(scores.values()) / len(scores) if scores else 0
        return {"scores": scores, "total_score": round(total, 4)}

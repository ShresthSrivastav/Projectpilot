"""Log Analysis Engine — parse logs, classify errors, detect root causes, suggest fixes."""

import json
import logging
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from services.llm_service import call_model

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    SYNTAX_ERROR = "syntax_error"
    DEPENDENCY_FAILURE = "dependency_failure"
    IMPORT_FAILURE = "import_failure"
    DATABASE_FAILURE = "database_failure"
    NETWORK_FAILURE = "network_failure"
    TEST_FAILURE = "test_failure"
    DEPLOYMENT_FAILURE = "deployment_failure"
    RUNTIME_CRASH = "runtime_crash"
    PORT_CONFLICT = "port_conflict"
    TIMEOUT = "timeout"
    MEMORY_ERROR = "memory_error"
    PERMISSION_ERROR = "permission_error"
    UNKNOWN = "unknown"


@dataclass
class AnalysisResult:
    error_type: str = ""
    confidence: float = 0.0
    root_cause: str = ""
    suggested_fix: str = ""
    category: str = ""
    line_number: int | None = None
    file_path: str | None = None
    raw_match: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# Regex patterns for error classification
ERROR_PATTERNS: dict[ErrorCategory, list[dict]] = {
    ErrorCategory.SYNTAX_ERROR: [
        {"pattern": r"SyntaxError:.*", "confidence": 0.95},
        {"pattern": r"IndentationError:.*", "confidence": 0.95},
        {"pattern": r"invalid syntax", "confidence": 0.9},
        {"pattern": r"unexpected EOF while parsing", "confidence": 0.9},
    ],
    ErrorCategory.DEPENDENCY_FAILURE: [
        {"pattern": r"ModuleNotFoundError: No module named '(\w+)'", "confidence": 0.9, "group": 1},
        {"pattern": r"ImportError: No module named", "confidence": 0.85},
        {"pattern": r"Could not find a version that satisfies the requirement", "confidence": 0.9},
        {"pattern": r"pip.*install.*failed", "confidence": 0.8},
        {"pattern": r"npm ERR!.*not found", "confidence": 0.85},
    ],
    ErrorCategory.IMPORT_FAILURE: [
        {"pattern": r"ImportError: cannot import name '(\w+)' from '(\w+)'", "confidence": 0.9},
        {"pattern": r"ImportError:.*", "confidence": 0.8},
        {"pattern": r"cannot import name", "confidence": 0.8},
    ],
    ErrorCategory.DATABASE_FAILURE: [
        {"pattern": r"Connection refused.*:.*5432", "confidence": 0.9},
        {"pattern": r"Can't connect to MySQL server", "confidence": 0.9},
        {"pattern": r"database.*does not exist", "confidence": 0.85},
        {"pattern": r"psycopg2\.OperationalError", "confidence": 0.85},
        {"pattern": r"sqlalchemy\.exc\..*Error", "confidence": 0.8},
        {"pattern": r"no such table", "confidence": 0.8},
    ],
    ErrorCategory.NETWORK_FAILURE: [
        {"pattern": r"Connection refused", "confidence": 0.85},
        {"pattern": r"Connection timeout", "confidence": 0.85},
        {"pattern": r"ConnectionError:.*", "confidence": 0.8},
        {"pattern": r"requests\.exceptions\.ConnectionError", "confidence": 0.85},
        {"pattern": r"httpx\.ConnectError", "confidence": 0.85},
        {"pattern": r"Name or service not known", "confidence": 0.9},
    ],
    ErrorCategory.TEST_FAILURE: [
        {"pattern": r"FAILED .*::.*", "confidence": 0.9},
        {"pattern": r"AssertionError:", "confidence": 0.85},
        {"pattern": r"AssertionError: assert", "confidence": 0.9},
        {"pattern": r"tests failed", "confidence": 0.85},
        {"pattern": r"FAILURES:", "confidence": 0.8},
    ],
    ErrorCategory.DEPLOYMENT_FAILURE: [
        {"pattern": r"Deployment failed", "confidence": 0.85},
        {"pattern": r"Build failed", "confidence": 0.8},
        {"pattern": r"Error:.*deploy", "confidence": 0.75},
        {"pattern": r"health check.*failed", "confidence": 0.85},
    ],
    ErrorCategory.RUNTIME_CRASH: [
        {"pattern": r"Segmentation fault", "confidence": 0.95},
        {"pattern": r"Killed", "confidence": 0.85},
        {"pattern": r"panic:", "confidence": 0.8},
        {"pattern": r"Fatal Python error", "confidence": 0.95},
    ],
    ErrorCategory.PORT_CONFLICT: [
        {"pattern": r"Address already in use", "confidence": 0.95},
        {"pattern": r"port.*already in use", "confidence": 0.9},
        {"pattern": r"EADDRINUSE", "confidence": 0.95},
        {"pattern": r"OSError:.*address already in use", "confidence": 0.95},
    ],
    ErrorCategory.TIMEOUT: [
        {"pattern": r"timeout", "confidence": 0.7},
        {"pattern": r"timed out", "confidence": 0.8},
        {"pattern": r"TimeoutError:", "confidence": 0.85},
        {"pattern": r"Request timed out", "confidence": 0.85},
    ],
    ErrorCategory.MEMORY_ERROR: [
        {"pattern": r"MemoryError:", "confidence": 0.95},
        {"pattern": r"OutOfMemoryError", "confidence": 0.9},
        {"pattern": r"JavaScript heap out of memory", "confidence": 0.9},
    ],
    ErrorCategory.PERMISSION_ERROR: [
        {"pattern": r"Permission denied", "confidence": 0.9},
        {"pattern": r"EACCES", "confidence": 0.9},
        {"pattern": r"Operation not permitted", "confidence": 0.85},
    ],
}


class LogAnalyzer:
    def __init__(self):
        self.analysis_history: list[AnalysisResult] = []
        self._lock = logging.getLogger(__name__)

    def analyze(self, log_text: str, use_llm: bool = False) -> AnalysisResult:
        result = self._regex_analyze(log_text)
        if use_llm and result.category == "unknown":
            llm_result = self._llm_analyze(log_text)
            if llm_result.confidence > result.confidence:
                result = llm_result
        self.analysis_history.append(result)
        return result

    def _regex_analyze(self, log_text: str) -> AnalysisResult:
        for category, patterns in ERROR_PATTERNS.items():
            for rule in patterns:
                match = re.search(rule["pattern"], log_text, re.IGNORECASE)
                if match:
                    root_cause = self._generate_root_cause(category, match, log_text)
                    suggested_fix = self._generate_fix(category, match)
                    line_number = self._find_line_number(log_text, match.start())
                    file_path = self._find_file_path(log_text, match.start())
                    return AnalysisResult(
                        error_type=category.value,
                        confidence=rule["confidence"],
                        root_cause=root_cause,
                        suggested_fix=suggested_fix,
                        category=category.name,
                        line_number=line_number,
                        file_path=file_path,
                        raw_match=match.group(0),
                    )
        return AnalysisResult(
            error_type=ErrorCategory.UNKNOWN.value,
            confidence=0.3,
            root_cause="Unknown error pattern",
            suggested_fix="Review logs manually to identify the issue",
            category="UNKNOWN",
        )

    def _generate_root_cause(self, category: ErrorCategory, match: re.Match, log_text: str) -> str:
        line_idx = self._find_line_number(log_text, match.start())
        causes = {
            ErrorCategory.SYNTAX_ERROR: f"Syntax error in source code at line ~{line_idx}: {match.group(0)}",
            ErrorCategory.DEPENDENCY_FAILURE: f"Missing or incompatible dependency: {match.group(0)}",
            ErrorCategory.IMPORT_FAILURE: f"Import resolution failure: {match.group(0)}",
            ErrorCategory.DATABASE_FAILURE: f"Database connection or query failure: {match.group(0)}",
            ErrorCategory.NETWORK_FAILURE: f"Network connectivity issue: {match.group(0)}",
            ErrorCategory.TEST_FAILURE: f"Test assertion or runtime failure: {match.group(0)}",
            ErrorCategory.DEPLOYMENT_FAILURE: f"Deployment pipeline failure: {match.group(0)}",
            ErrorCategory.RUNTIME_CRASH: f"Application runtime crash: {match.group(0)}",
            ErrorCategory.PORT_CONFLICT: "Port already in use by another process",
            ErrorCategory.TIMEOUT: "Operation exceeded timeout threshold",
            ErrorCategory.MEMORY_ERROR: "Application exhausted available memory",
            ErrorCategory.PERMISSION_ERROR: "Insufficient permissions for operation",
            ErrorCategory.UNKNOWN: f"Unclassified error: {match.group(0)}",
        }
        return causes.get(category, f"Error detected: {match.group(0)}")

    def _generate_fix(self, category: ErrorCategory, match: re.Match) -> str:
        fixes = {
            ErrorCategory.SYNTAX_ERROR: "Check the syntax at the indicated line. Look for missing colons, brackets, parentheses, or quotes. Run `python -m py_compile <file>` to validate.",
            ErrorCategory.DEPENDENCY_FAILURE: "Install the missing package with `pip install <package>` or add it to requirements.txt. If package name changed, update the import statement.",
            ErrorCategory.IMPORT_FAILURE: "Verify the module/class name is correct. Check the package exports. The import path may need updating after a package restructure.",
            ErrorCategory.DATABASE_FAILURE: "Ensure database server is running. Verify connection string, credentials, and that the database/table exists. Check firewall rules.",
            ErrorCategory.NETWORK_FAILURE: "Verify the target service is running and reachable. Check network connectivity, DNS resolution, and firewall rules. Consider adding retry logic.",
            ErrorCategory.TEST_FAILURE: "Review the test assertion and expected values. The test may need updating if requirements changed, or the code may have a regression.",
            ErrorCategory.DEPLOYMENT_FAILURE: "Check deployment configuration, environment variables, and build logs. Verify all required services are available.",
            ErrorCategory.RUNTIME_CRASH: "Review application logs for crash context. Check for null pointer dereferences, array bounds, or resource exhaustion.",
            ErrorCategory.PORT_CONFLICT: "Stop the process using the port or change the application port. Use `lsof -i :<port>` to find the conflicting process on Linux/macOS.",
            ErrorCategory.TIMEOUT: "Increase timeout configuration, optimize the slow operation, or add asynchronous processing for long-running tasks.",
            ErrorCategory.MEMORY_ERROR: "Reduce memory usage, increase available memory, fix memory leaks, or add pagination for large datasets.",
            ErrorCategory.PERMISSION_ERROR: "Run with appropriate permissions. Check file ownership and access rights. Avoid running as root where possible.",
            ErrorCategory.UNKNOWN: "Review the full log output. Check system resources, application configuration, and recent changes.",
        }
        return fixes.get(category, "Review logs for more details.")

    def _find_line_number(self, log_text: str, char_pos: int) -> int | None:
        lines = log_text.splitlines()
        cumulative = 0
        for i, line in enumerate(lines):
            cumulative += len(line) + 1
            if cumulative > char_pos:
                return i + 1
        return None

    def _find_file_path(self, log_text: str, char_pos: int) -> str | None:
        file_patterns = [
            r'File "([^"]+)"',
            r"in ([a-zA-Z_][\w./]*)\.py",
            r"at ([a-zA-Z_][\w./]*\.[a-z]+)",
        ]
        for pattern in file_patterns:
            for m in re.finditer(pattern, log_text):
                return m.group(1)
        return None

    def _llm_analyze(self, log_text: str) -> AnalysisResult:
        try:
            prompt = f"""Analyze this error log and identify the root cause:

```
{log_text[:3000]}
```

Output JSON:
{{
  "error_type": "category_name",
  "confidence": 0.0-1.0,
  "root_cause": "brief description",
  "suggested_fix": "actionable fix instruction"
}}"""
            result = call_model(prompt, model="cloud", agent="LogAnalyzer")
            result = re.sub(r"```\w*", "", result).strip()
            parsed = json.loads(result)
            return AnalysisResult(
                error_type=parsed.get("error_type", "unknown"),
                confidence=parsed.get("confidence", 0.5),
                root_cause=parsed.get("root_cause", ""),
                suggested_fix=parsed.get("suggested_fix", ""),
                category=parsed.get("error_type", "UNKNOWN").upper(),
            )
        except Exception as exc:
            logger.warning("LLM analysis failed: %s", exc)
            return AnalysisResult(error_type="unknown", confidence=0.0, root_cause="LLM analysis unavailable")

    def get_statistics(self) -> dict[str, Any]:
        if not self.analysis_history:
            return {"total": 0, "categories": {}}
        categories = {}
        for r in self.analysis_history:
            cat = r.category or "unknown"
            categories[cat] = categories.get(cat, 0) + 1
        return {
            "total": len(self.analysis_history),
            "categories": categories,
            "most_common": max(categories, key=categories.get) if categories else "",
        }


_log_analyzer = LogAnalyzer()


def get_log_analyzer() -> LogAnalyzer:
    return _log_analyzer

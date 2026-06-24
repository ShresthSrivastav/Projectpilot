"""Base Validator SDK — interface for creating custom validators."""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ValidationRule:
    name: str = ""
    description: str = ""
    severity: str = "error"
    enabled: bool = True


@dataclass
class ValidationReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    passed: bool = True
    rules_checked: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseValidator(ABC):
    def __init__(self):
        self.rules: list[ValidationRule] = []
        self._logger = logging.getLogger(f"validator.{self.__class__.__name__}")

    @abstractmethod
    def validate(self, target: Any) -> ValidationReport: ...

    def add_rule(self, rule: ValidationRule) -> None:
        self.rules.append(rule)

    def get_rules(self) -> list[ValidationRule]:
        return self.rules

    def create_report(self, errors: list[str], warnings: list[str]) -> ValidationReport:
        return ValidationReport(
            passed=len(errors) == 0,
            rules_checked=len(self.rules),
            errors=[{"message": e} for e in errors],
            warnings=[{"message": w} for w in warnings],
            summary=f"{len(errors)} error(s), {len(warnings)} warning(s)",
        )

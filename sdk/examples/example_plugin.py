"""Example Plugin — Code Quality Validator Plugin.
Shows how any developer can create a plugin without modifying platform source code.
"""
# name: code-quality-validator
# version: 1.0.0
# author: SDK Example
# description: Validates Python code quality with pylint-like checks
# type: validator

import ast
from typing import Any, Dict, Optional

from sdk.plugin_sdk.base_plugin import BasePlugin, PluginManifest, PluginType


class CodeQualityValidator(BasePlugin):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.manifest = PluginManifest(
            name="code-quality-validator",
            version="1.0.0",
            author="SDK Example",
            description="Validates Python code quality with pylint-like checks",
            plugin_type=PluginType.VALIDATOR.value,
            permissions=["read:files"],
            compatibility=">=11.0.0",
            tags=["validator", "code-quality", "python"],
        )

    def install(self) -> bool:
        return True

    def uninstall(self) -> bool:
        return True

    def configure(self, config: Dict[str, Any]) -> bool:
        self.config.update(config)
        return True

    def validate(self) -> bool:
        return True

    def validate_code(self, source_code: str) -> Dict[str, Any]:
        issues = []
        # Check for missing docstrings
        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    if not ast.get_docstring(node):
                        issues.append({
                            "type": "style",
                            "message": f"Missing docstring in {node.name}",
                            "line": node.lineno,
                        })
        except SyntaxError as e:
            issues.append({"type": "error", "message": f"Syntax error: {e}"})

        # Check for long lines
        for i, line in enumerate(source_code.splitlines(), 1):
            if len(line) > 100:
                issues.append({
                    "type": "style",
                    "message": f"Line {i} too long ({len(line)} > 100 chars)",
                    "line": i,
                })

        return {
            "valid": len([i for i in issues if i["type"] == "error"]) == 0,
            "issues": issues,
            "total_issues": len(issues),
        }


# Entry point for plugin registry
plugin = CodeQualityValidator

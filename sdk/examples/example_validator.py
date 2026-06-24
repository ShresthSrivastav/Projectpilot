"""Example Validator — API Schema Validator.
Shows how any developer can create a custom validator without modifying platform source code.
"""

from typing import Any

from sdk.validation_sdk.base_validator import BaseValidator, ValidationReport, ValidationRule


class APISchemaValidator(BaseValidator):
    def __init__(self):
        super().__init__()
        self.rules = [
            ValidationRule(name="openapi-version", description="Must use OpenAPI 3.0+", severity="error"),
            ValidationRule(name="endpoint-naming", description="Endpoints must use kebab-case", severity="warning"),
            ValidationRule(name="response-schema", description="All responses must have a schema", severity="error"),
        ]

    def validate(self, target: Any) -> ValidationReport:
        errors = []
        warnings = []

        if isinstance(target, dict):
            openapi = target.get("openapi", "")
            if openapi and not openapi.startswith("3."):
                errors.append("OpenAPI version must be 3.0+")
            elif not openapi:
                errors.append("Missing openapi version field")

            paths = target.get("paths", {})
            for path in paths.keys():
                if path != path.lower():
                    warnings.append(f"Path '{path}' should be lowercase")

            for path, methods in paths.items():
                for method, details in methods.items():
                    responses = details.get("responses", {})
                    for status_code, response in responses.items():
                        content = response.get("content", {})
                        if not content:
                            warnings.append(f"{method.upper()} {path} [{status_code}] no content defined")
                        else:
                            for media_type, media in content.items():
                                schema = media.get("schema", {})
                                if not schema:
                                    warnings.append(f"{method.upper()} {path} [{status_code}] missing response schema")

        return self.create_report(errors, warnings)

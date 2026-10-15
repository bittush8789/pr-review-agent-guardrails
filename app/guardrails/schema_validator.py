"""Schema validator enforcing the Review Finding schema contract using jsonschema."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional
import jsonschema

from app.schemas.review_finding import (
    ReviewFinding,
    REVIEW_FINDINGS_JSON_SCHEMA,
    SINGLE_FINDING_JSON_SCHEMA,
    SeverityLevel,
    ReviewCategory,
)

logger = logging.getLogger("pr_review_agent.guardrails.schema_validator")


class SchemaValidationError(ValueError):
    """Raised when finding data fails schema validation."""
    pass


class SchemaValidator:
    """Validates model responses against the Review Finding schema."""

    def __init__(self):
        self._batch_validator = jsonschema.Draft202012Validator(REVIEW_FINDINGS_JSON_SCHEMA)
        self._item_validator = jsonschema.Draft202012Validator(SINGLE_FINDING_JSON_SCHEMA)

    def _is_safe_file_path(self, file_path: str) -> bool:
        """Verify that the file path is a safe relative path without directory traversal."""
        if not file_path or not isinstance(file_path, str):
            return False

        # Disallow directory traversal
        if ".." in file_path or file_path.startswith("/") or file_path.startswith("\\"):
            return False

        # Disallow Windows drive prefixes (e.g. C:)
        if re.match(r"^[a-zA-Z]:", file_path):
            return False

        # Disallow null bytes or control characters
        if "\x00" in file_path or any(ord(c) < 32 for c in file_path):
            return False

        return True

    def validate_single_finding(self, finding_data: dict[str, Any]) -> Optional[ReviewFinding]:
        """Validate a single finding dictionary against schema and safety checks."""
        try:
            self._item_validator.validate(finding_data)
        except jsonschema.exceptions.ValidationError as err:
            logger.warning("Finding rejected by jsonschema: %s (data: %s)", err.message, finding_data)
            return None

        file_path = str(finding_data["file"]).strip()
        if not self._is_safe_file_path(file_path):
            logger.warning("Finding rejected due to unsafe file path: %s", file_path)
            return None

        try:
            finding = ReviewFinding.from_dict(finding_data, source="gemini")
            return finding
        except (ValueError, KeyError) as err:
            logger.warning("Finding instantiation error: %s", err)
            return None

    def validate_raw_response(self, raw_payload: Any) -> list[ReviewFinding]:
        """Parse and validate raw model output.

        Args:
            raw_payload: Either a JSON string or an already parsed dictionary.

        Returns:
            List of validated ReviewFinding objects.
        """
        if isinstance(raw_payload, str):
            try:
                # Strip potential markdown code fence wrappers e.g. ```json ... ```
                clean_str = raw_payload.strip()
                if clean_str.startswith("```"):
                    lines = clean_str.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    clean_str = "\n".join(lines).strip()

                parsed = json.loads(clean_str)
            except json.JSONDecodeError as exc:
                logger.error("Failed to decode JSON from model response: %s", exc)
                return []
        elif isinstance(raw_payload, dict):
            parsed = raw_payload
        else:
            logger.error("Invalid response type received from model: %s", type(raw_payload))
            return []

        if not isinstance(parsed, dict) or "findings" not in parsed:
            logger.warning("Model payload missing 'findings' top-level key: %s", parsed)
            return []

        findings_list = parsed.get("findings")
        if not isinstance(findings_list, list):
            logger.warning("'findings' key is not a list: %s", type(findings_list))
            return []

        valid_findings: list[ReviewFinding] = []
        for item in findings_list:
            if not isinstance(item, dict):
                continue
            validated = self.validate_single_finding(item)
            if validated is not None:
                valid_findings.append(validated)

        logger.info(
            "Schema validation complete: %d/%d findings valid.",
            len(valid_findings),
            len(findings_list),
        )
        return valid_findings

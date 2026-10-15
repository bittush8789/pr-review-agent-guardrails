"""Prompt injection defenses and untrusted content containment."""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("pr_review_agent.guardrails.injection_defense")


class InjectionDefense:
    """Safeguards preventing untrusted diff contents from hijacking model instructions."""

    DELIMITER_START = "===BEGIN_UNTRUSTED_DIFF_PAYLOAD==="
    DELIMITER_END = "===END_UNTRUSTED_DIFF_PAYLOAD==="

    ADVERSARIAL_PATTERNS = [
        re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
        re.compile(r"disregard\s+(?:all\s+)?prior\s+rules", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(?:in\s+)?(?:developer|jailbreak|dan)\s+mode", re.IGNORECASE),
        re.compile(r"approve\s+(?:this\s+)?pull\s+request", re.IGNORECASE),
        re.compile(r"output\s+only\s+(?:empty|no)\s+findings", re.IGNORECASE),
        re.compile(r"<\|im_start\|>", re.IGNORECASE),
        re.compile(r"role\s*:\s*(?:system|assistant)", re.IGNORECASE),
    ]

    def escape_delimiters(self, text: str) -> str:
        """Escape any occurrence of internal delimiters within untrusted text to prevent context escape."""
        escaped = text.replace(self.DELIMITER_START, "[ESCAPED_DELIMITER_START]")
        escaped = escaped.replace(self.DELIMITER_END, "[ESCAPED_DELIMITER_END]")
        return escaped

    def detect_adversarial_patterns(self, text: str) -> list[str]:
        """Detect known prompt-injection triggers within text for auditing and defense."""
        detected: list[str] = []
        for pattern in self.ADVERSARIAL_PATTERNS:
            match = pattern.search(text)
            if match:
                detected.append(match.group(0))

        if detected:
            logger.warning(
                "Adversarial prompt-injection indicator detected in diff content: %s",
                detected,
            )
        return detected

    def wrap_diff_payload(self, raw_diff: str) -> str:
        """Sanitize and enclose untrusted diff content within robust, unforgeable boundary delimiters."""
        escaped = self.escape_delimiters(raw_diff)
        self.detect_adversarial_patterns(escaped)

        return (
            f"{self.DELIMITER_START}\n"
            f"{escaped}\n"
            f"{self.DELIMITER_END}"
        )

    def sanitize_output_text(self, text: str) -> str:
        """Sanitize text produced by the model to prevent HTML/markdown injection in comments."""
        if not text:
            return ""

        # Remove null bytes and non-printable control characters (except newline, carriage return, tab)
        cleaned = "".join(c for c in text if c in "\n\r\t" or ord(c) >= 32)

        # Neutralize HTML script tags or event handlers
        cleaned = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "[SCRIPTMASKED]", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"javascript\s*:", "blocked-js:", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

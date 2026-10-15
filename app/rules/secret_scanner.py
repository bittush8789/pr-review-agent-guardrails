"""Deterministic Python-based secret detection module with redaction safeguards."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Optional

from app.schemas.review_finding import ReviewFinding, ReviewCategory, SeverityLevel

logger = logging.getLogger("pr_review_agent.rules.secret_scanner")


@dataclass(frozen=True)
class SecretDetectionRule:
    """Configuration for an individual secret detection pattern."""

    rule_id: str
    name: str
    pattern: re.Pattern
    severity: SeverityLevel
    confidence: float
    description: str
    suggestion: str


# Placeholders that indicate synthetic or test strings rather than real credentials
PLACEHOLDER_SUBSTRINGS = {
    "your_api_key",
    "replace_with",
    "example",
    "sample",
    "dummy",
    "placeholder",
    "changeme",
    "fake",
    "my_secret",
    "xxxx",
    "test_token",
    "mock_key",
    "none",
    "null",
}


def calculate_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string to estimate randomness."""
    if not text:
        return 0.0
    freq: dict[str, int] = {}
    for char in text:
        freq[char] = freq.get(char, 0) + 1
    entropy = 0.0
    text_len = len(text)
    for count in freq.values():
        p = count / text_len
        entropy -= p * math.log2(p)
    return entropy


class SecretScanner:
    """Deterministic scanner detecting hardcoded credentials, tokens, and keys."""

    DEFAULT_RULES: list[SecretDetectionRule] = [
        SecretDetectionRule(
            rule_id="SEC_AWS_ACCESS_KEY",
            name="AWS Access Key ID",
            pattern=re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
            severity=SeverityLevel.CRITICAL,
            confidence=0.98,
            description="Potential AWS Access Key ID detected.",
            suggestion="Remove the hardcoded AWS access key. Use AWS IAM roles, environment variables, or AWS Secrets Manager.",
        ),
        SecretDetectionRule(
            rule_id="SEC_GITHUB_TOKEN",
            name="GitHub Personal Access Token",
            pattern=re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,255})\b"),
            severity=SeverityLevel.CRITICAL,
            confidence=0.99,
            description="Potential GitHub personal access or OAuth token detected.",
            suggestion="Revoke the exposed GitHub token immediately. Inject tokens via GitHub Actions Secrets or an encrypted vault.",
        ),
        SecretDetectionRule(
            rule_id="SEC_PRIVATE_KEY",
            name="Cryptographic Private Key Block",
            pattern=re.compile(
                r"-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH|PGP|ENCRYPTED)?\s*(?:PRIVATE)?\s*KEY-----",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.CRITICAL,
            confidence=0.99,
            description="Cryptographic private key block header detected.",
            suggestion="Do not commit private keys to source control. Store keys in a secure key management system (KMS) or secret store.",
        ),
        SecretDetectionRule(
            rule_id="SEC_GOOGLE_API_KEY",
            name="Google / Gemini API Key",
            pattern=re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"),
            severity=SeverityLevel.CRITICAL,
            confidence=0.95,
            description="Potential Google API key detected.",
            suggestion="Store Google API credentials in environment variables or Google Secret Manager. Restrict key usage in Google Cloud Console.",
        ),
        SecretDetectionRule(
            rule_id="SEC_SLACK_TOKEN",
            name="Slack API Token",
            pattern=re.compile(r"\b(xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*)\b"),
            severity=SeverityLevel.HIGH,
            confidence=0.95,
            description="Potential Slack bot or user token detected.",
            suggestion="Move Slack tokens out of code into encrypted secret storage and rotate the exposed token.",
        ),
        SecretDetectionRule(
            rule_id="SEC_STRIPE_KEY",
            name="Stripe API Key",
            pattern=re.compile(r"\b(sk_(?:test|live)_[0-9a-zA-Z]{24,99})\b"),
            severity=SeverityLevel.CRITICAL,
            confidence=0.98,
            description="Potential Stripe secret API key detected.",
            suggestion="Do not hardcode payment gateway secrets. Inject Stripe keys through environment variables.",
        ),
        SecretDetectionRule(
            rule_id="SEC_HARDCODED_PASSWORD",
            name="Hardcoded Password Assignment",
            pattern=re.compile(
                r"""(?:password|passwd|pwd|secret_key|api_secret)\s*[:=]\s*['"]([^'"]{8,128})['"]""",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.HIGH,
            confidence=0.85,
            description="Potential hardcoded password or secret string assignment.",
            suggestion="Avoid hardcoding passwords and credentials in code. Retrieve sensitive values at runtime from a secure secrets provider.",
        ),
        SecretDetectionRule(
            rule_id="SEC_BEARER_TOKEN",
            name="Hardcoded Bearer Authentication Token",
            pattern=re.compile(r"""['"]Bearer\s+([a-zA-Z0-9_\-\.]{25,})['"]""", re.IGNORECASE),
            severity=SeverityLevel.HIGH,
            confidence=0.90,
            description="Potential hardcoded Bearer token found in authorization header or string.",
            suggestion="Pass dynamic authorization tokens via secure context or environment variables.",
        ),
        SecretDetectionRule(
            rule_id="SEC_LANGSMITH_KEY",
            name="LangSmith API Key",
            pattern=re.compile(r"\b(lsv2_pt_[a-zA-Z0-9_]{30,80})\b"),
            severity=SeverityLevel.CRITICAL,
            confidence=0.99,
            description="Potential LangSmith API key detected.",
            suggestion="Do not commit LangSmith API keys. Use environment variables or GitHub Actions Secrets (LANGCHAIN_API_KEY).",
        ),
    ]

    def __init__(self, rules: Optional[list[SecretDetectionRule]] = None):
        self.rules = rules if rules is not None else self.DEFAULT_RULES

    def is_placeholder(self, matched_value: str) -> bool:
        """Check if the matched text is an obvious placeholder or template variable."""
        lower = matched_value.lower()
        if any(ph in lower for ph in PLACEHOLDER_SUBSTRINGS):
            return True

        # Environment variable expressions like ${MY_TOKEN} or %VAR%
        if (matched_value.startswith("${") and matched_value.endswith("}")) or (
            matched_value.startswith("%") and matched_value.endswith("%")
        ):
            return True

        # Check for repetitive single characters like '00000000' or 'aaaaaaaa'
        if len(set(matched_value)) <= 2:
            return True

        return False

    def redact_text(self, text: str) -> str:
        """Sanitize text by replacing all known secret patterns with redaction markers.

        This function must be applied to any context passed to LLMs, logs, or error reports.
        """
        redacted = text
        for rule in self.rules:
            # Replace matches with safe masked token
            redacted = rule.pattern.sub(f"[REDACTED_{rule.rule_id}]", redacted)
        return redacted

    def scan_line(self, filename: str, line_num: int, line_content: str) -> list[ReviewFinding]:
        """Scan a single line of changed code for secret patterns."""
        findings: list[ReviewFinding] = []

        # Ignore comment-only lines in test fixture datasets if explicitly testing mocks
        for rule in self.rules:
            matches = rule.pattern.findall(line_content)
            if not matches:
                continue

            for match in matches:
                # Handle regex groups vs single match
                matched_str = match if isinstance(match, str) else match[0] if match else ""
                if not matched_str or self.is_placeholder(matched_str):
                    continue

                # Filter generic password rule with entropy check to avoid low-entropy false positives
                if rule.rule_id == "SEC_HARDCODED_PASSWORD":
                    if calculate_entropy(matched_str) < 2.5:
                        continue

                finding = ReviewFinding(
                    file=filename,
                    line=line_num,
                    severity=rule.severity,
                    category=ReviewCategory.SECURITY,
                    title=f"Potential Secret Detected: {rule.name}",
                    suggestion=rule.suggestion,
                    confidence=rule.confidence,
                    source=f"deterministic:secret_scanner:{rule.rule_id}",
                    rule_id=rule.rule_id,
                )
                findings.append(finding)

        return findings

    def scan_diff_lines(self, added_lines: dict[tuple[str, int], str]) -> list[ReviewFinding]:
        """Scan all newly added or modified lines in a parsed diff.

        Args:
            added_lines: Mapping of (filename, line_number) -> text_content.

        Returns:
            List of ReviewFinding objects.
        """
        findings: list[ReviewFinding] = []
        for (filename, line_num), content in added_lines.items():
            line_findings = self.scan_line(filename, line_num, content)
            findings.extend(line_findings)

        logger.debug("SecretScanner found %d potential secrets in diff.", len(findings))
        return findings

"""Application settings and logging configuration with sensitive data protection."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional


class ConfigurationError(ValueError):
    """Raised when configuration values are missing, invalid, or malformed."""
    pass


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts API keys, tokens, and authorization headers."""

    PATTERNS = [
        re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE),
        re.compile(r"(ghp_[a-zA-Z0-9]{36,})", re.IGNORECASE),
        re.compile(r"(AIza[0-9A-Za-z\-_]{35})", re.IGNORECASE),
        re.compile(r"(GEMINI_API_KEY=)[^\s]+", re.IGNORECASE),
        re.compile(r"(GITHUB_TOKEN=)[^\s]+", re.IGNORECASE),
        re.compile(r"(LANGCHAIN_API_KEY=)[^\s]+", re.IGNORECASE),
        re.compile(r"(lsv2_pt_[a-zA-Z0-9_]{30,})", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern in self.PATTERNS:
                msg = pattern.sub(r"\1***REDACTED***", msg)
            record.msg = msg
        return True


@dataclass(frozen=True)
class Settings:
    """Immutable application settings validated at initialization."""

    github_token: str
    gemini_api_key: Optional[str]
    gemini_model: str
    github_repository: str
    pull_request_number: int
    max_comments_per_pr: int = 5
    confidence_threshold: float = 0.70
    log_level: str = "INFO"
    dry_run: bool = False
    github_api_url: str = "https://api.github.com"
    request_timeout_seconds: float = 30.0
    langsmith_tracing: bool = False
    langsmith_api_key: Optional[str] = None
    langsmith_project: str = "github-pr-review-agent"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    post_summary_comment: bool = True

    def __repr__(self) -> str:
        """Mask credentials when printing or logging settings."""
        token_masked = "***REDACTED***" if self.github_token else "NOT_SET"
        gemini_masked = "***REDACTED***" if self.gemini_api_key else "NOT_SET"
        langsmith_masked = "***REDACTED***" if self.langsmith_api_key else "NOT_SET"
        return (
            f"Settings(github_repository='{self.github_repository}', "
            f"pull_request_number={self.pull_request_number}, "
            f"gemini_model='{self.gemini_model}', "
            f"max_comments_per_pr={self.max_comments_per_pr}, "
            f"confidence_threshold={self.confidence_threshold}, "
            f"log_level='{self.log_level}', "
            f"dry_run={self.dry_run}, "
            f"github_token={token_masked}, "
            f"gemini_api_key={gemini_masked}, "
            f"langsmith_tracing={self.langsmith_tracing}, "
            f"langsmith_project='{self.langsmith_project}', "
            f"langsmith_api_key={langsmith_masked})"
        )


def _validate_repository_format(repo: str) -> None:
    """Validate that repository follows owner/repo pattern."""
    repo_pattern = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    if not repo_pattern.match(repo):
        raise ConfigurationError(
            f"Invalid GITHUB_REPOSITORY '{repo}'. Expected format: 'owner/repo'."
        )


def load_settings(env: Optional[dict[str, str]] = None) -> Settings:
    """Load and validate settings from environment variables or a provided dictionary.

    Args:
        env: Optional mapping of environment variable names to values. If None, os.environ is used.

    Returns:
        Validated Settings instance.

    Raises:
        ConfigurationError: If any required setting is missing or out of valid bounds.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    source = os.environ if env is None else {**os.environ, **env}

    github_token = source.get("GITHUB_TOKEN", "").strip()
    if not github_token:
        raise ConfigurationError("Missing required environment variable: GITHUB_TOKEN")

    gemini_api_key = source.get("GEMINI_API_KEY", "").strip() or None

    gemini_model = source.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
    if not gemini_model:
        raise ConfigurationError("GEMINI_MODEL cannot be empty.")

    github_repository = source.get("GITHUB_REPOSITORY", "").strip()
    if not github_repository:
        raise ConfigurationError("Missing required environment variable: GITHUB_REPOSITORY")
    _validate_repository_format(github_repository)

    pr_raw = source.get("PULL_REQUEST_NUMBER", source.get("PR_NUMBER", "")).strip()
    if not pr_raw:
        raise ConfigurationError("Missing required environment variable: PULL_REQUEST_NUMBER")
    try:
        pull_request_number = int(pr_raw)
        if pull_request_number <= 0:
            raise ValueError()
    except ValueError:
        raise ConfigurationError(
            f"Invalid PULL_REQUEST_NUMBER '{pr_raw}'. Must be a positive integer."
        )

    max_comments_raw = source.get("MAX_COMMENTS_PER_PR", "5").strip()
    try:
        max_comments_per_pr = int(max_comments_raw)
        if max_comments_per_pr < 1:
            raise ValueError()
    except ValueError:
        raise ConfigurationError(
            f"Invalid MAX_COMMENTS_PER_PR '{max_comments_raw}'. Must be an integer >= 1."
        )

    confidence_raw = source.get("CONFIDENCE_THRESHOLD", "0.70").strip()
    try:
        confidence_threshold = float(confidence_raw)
        if not (0.0 <= confidence_threshold <= 1.0):
            raise ValueError()
    except ValueError:
        raise ConfigurationError(
            f"Invalid CONFIDENCE_THRESHOLD '{confidence_raw}'. Must be a float between 0.0 and 1.0."
        )

    log_level = source.get("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError(
            f"Invalid LOG_LEVEL '{log_level}'. Allowed values: DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )

    dry_run_raw = source.get("DRY_RUN", "false").strip().lower()
    dry_run = dry_run_raw in {"1", "true", "yes"}

    github_api_url = source.get("GITHUB_API_URL", "https://api.github.com").strip().rstrip("/")
    if not (github_api_url.startswith("http://") or github_api_url.startswith("https://")):
        raise ConfigurationError(f"Invalid GITHUB_API_URL '{github_api_url}'. Must start with http:// or https://")

    timeout_raw = source.get("REQUEST_TIMEOUT_SECONDS", "30.0").strip()
    try:
        request_timeout_seconds = float(timeout_raw)
        if request_timeout_seconds <= 0:
            raise ValueError()
    except ValueError:
        raise ConfigurationError(
            f"Invalid REQUEST_TIMEOUT_SECONDS '{timeout_raw}'. Must be a positive number."
        )

    # LangSmith tracing configuration (optional)
    langsmith_tracing_raw = source.get("LANGCHAIN_TRACING_V2", source.get("LANGSMITH_TRACING", "false")).strip().lower()
    langsmith_tracing = langsmith_tracing_raw in {"1", "true", "yes"}
    langsmith_api_key = source.get("LANGCHAIN_API_KEY", source.get("LANGSMITH_API_KEY", "")).strip() or None
    langsmith_project = source.get("LANGCHAIN_PROJECT", source.get("LANGSMITH_PROJECT", "github-pr-review-agent")).strip()
    langsmith_endpoint = source.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com").strip()

    # Synchronize process environment variables if LangSmith is enabled so SDK picks it up
    if langsmith_tracing and langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = langsmith_project
        os.environ["LANGCHAIN_ENDPOINT"] = langsmith_endpoint

    # PR Executive Summary configuration
    summary_raw = source.get("POST_SUMMARY_COMMENT", "true").strip().lower()
    post_summary_comment = summary_raw not in {"0", "false", "no"}

    return Settings(
        github_token=github_token,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        github_repository=github_repository,
        pull_request_number=pull_request_number,
        max_comments_per_pr=max_comments_per_pr,
        confidence_threshold=confidence_threshold,
        log_level=log_level,
        dry_run=dry_run,
        github_api_url=github_api_url,
        request_timeout_seconds=request_timeout_seconds,
        langsmith_tracing=langsmith_tracing,
        langsmith_api_key=langsmith_api_key,
        langsmith_project=langsmith_project,
        langsmith_endpoint=langsmith_endpoint,
        post_summary_comment=post_summary_comment,
    )


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured and sanitized root logger.

    Args:
        level: Logging level string (e.g. INFO, DEBUG).

    Returns:
        Configured logger instance.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger("pr_review_agent")
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

    logger.propagate = False
    return logger

"""Unit tests for LangSmith tracing configuration and fallback integration."""

import os
import pytest
from app.config.settings import load_settings, SensitiveDataFilter
from app.review.tracing import traceable, LANGSMITH_AVAILABLE


def test_traceable_decorator_preserves_function_behavior():
    """Verify that @traceable wraps functions transparently without altering returns or raising errors."""
    @traceable(name="test_function", run_type="chain")
    def sample_func(a: int, b: int) -> int:
        return a + b

    result = sample_func(10, 25)
    assert result == 35


def test_langsmith_key_redacted_in_logging():
    """Verify that LangSmith API keys are masked by SensitiveDataFilter."""
    filter_instance = SensitiveDataFilter()
    import logging
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=1,
        msg="Connecting with LANGCHAIN_API_KEY=lsv2_pt_111122223333444455556666777788889999",
        args=(),
        exc_info=None,
    )
    filter_instance.filter(record)
    assert "lsv2_pt_111122223333444455556666777788889999" not in record.msg
    assert "***REDACTED***" in record.msg


def test_settings_loads_langsmith_config():
    """Verify that LangSmith configuration options are parsed by load_settings."""
    env = {
        "GITHUB_TOKEN": "ghp_test123456789012345678901234567890",
        "GITHUB_REPOSITORY": "owner/repo",
        "PULL_REQUEST_NUMBER": "1",
        "LANGCHAIN_TRACING_V2": "true",
        "LANGCHAIN_API_KEY": "lsv2_pt_testapikey1234567890",
        "LANGCHAIN_PROJECT": "custom-pr-review-project",
    }
    settings = load_settings(env)
    assert settings.langsmith_tracing is True
    assert settings.langsmith_project == "custom-pr-review-project"
    assert settings.langsmith_api_key == "lsv2_pt_testapikey1234567890"

    # Verify repr masks the key
    repr_str = repr(settings)
    assert "lsv2_pt_testapikey1234567890" not in repr_str
    assert "langsmith_api_key=***REDACTED***" in repr_str

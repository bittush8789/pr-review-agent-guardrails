"""LangSmith observability and tracing integration with graceful no-op fallback."""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("pr_review_agent.tracing")

try:
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False

    def traceable(
        name: Optional[str] = None,
        run_type: str = "chain",
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Callable:
        """No-op fallback decorator when langsmith package is not installed."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args: Any, **func_kwargs: Any) -> Any:
                return func(*args, **func_kwargs)
            return wrapper
        return decorator


__all__ = ["traceable", "LANGSMITH_AVAILABLE"]

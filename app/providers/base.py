"""Abstract base definition for AI review providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class ProviderAPIError(Exception):
    """Exception raised when an AI provider call fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class AIReviewProvider(ABC):
    """Abstract interface for AI code review providers."""

    @abstractmethod
    def generate_review(self, system_instruction: str, user_prompt: str) -> str:
        """Execute a review prompt against the AI model and return the raw text response.

        Args:
            system_instruction: High-level instructions defining behavior and constraints.
            user_prompt: Context and untrusted diff payload.

        Returns:
            Raw response text from the model (expected to contain JSON findings).

        Raises:
            ProviderAPIError: If the API call fails or times out.
        """
        pass

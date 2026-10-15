"""Google Gemini AI review provider implemented with the official google-genai SDK."""

from __future__ import annotations

import logging
import time
from typing import Optional

from google import genai
from google.genai import types

from app.providers.base import AIReviewProvider, ProviderAPIError
from app.tracing import traceable

logger = logging.getLogger("pr_review_agent.providers.gemini_provider")


class GeminiProvider(AIReviewProvider):
    """Integrates with Google Gemini models using the official google-genai SDK."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.8-flash",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ):
        if not api_key or not api_key.strip():
            raise ValueError("A non-empty Gemini API key is required to initialize GeminiProvider.")
        if not model_name or not model_name.strip():
            raise ValueError("A non-empty Gemini model identifier is required.")

        self.api_key = api_key.strip()
        self.model_name = model_name.strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        # Initialize the official GenAI client
        self._client = genai.Client(api_key=self.api_key)

    @traceable(name="gemini_generate_review", run_type="llm")
    def generate_review(self, system_instruction: str, user_prompt: str) -> str:
        """Call Gemini generate_content with structured JSON output configuration.

        Args:
            system_instruction: Behavioral system prompt and instructions.
            user_prompt: Untrusted diff context wrapped with guardrail delimiters.

        Returns:
            JSON text returned by the model.

        Raises:
            ProviderAPIError: If the call fails after exhausting bounded retries.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.1,  # Low temperature for factual, consistent code analysis
        )

        models_to_try = [self.model_name]
        for fallback in ["gemini-2.5-flash", "gemini-2.0-flash"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_exception: Optional[Exception] = None

        for model_candidate in models_to_try:
            attempts = 0
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    logger.info(
                        "Sending diff context to Gemini (model: %s, attempt %d/%d)...",
                        model_candidate,
                        attempts,
                        self.max_retries + 1,
                    )

                    response = self._client.models.generate_content(
                        model=model_candidate,
                        contents=user_prompt,
                        config=config,
                    )

                    if response is None or not response.text:
                        logger.warning("Gemini returned an empty response.")
                        return '{"findings": []}'

                    return response.text

                except Exception as exc:
                    last_exception = exc
                    error_str = str(exc)
                    logger.warning(
                        "Gemini API request failed for model %s on attempt %d/%d: %s",
                        model_candidate,
                        attempts,
                        self.max_retries + 1,
                        error_str[:200],
                    )

                    if attempts <= self.max_retries:
                        backoff = 1.5 ** attempts
                        time.sleep(backoff)
                    else:
                        break
            logger.info("Retrying with next fallback model if available...")

        raise ProviderAPIError(
            f"Failed to generate review from Gemini model '{self.model_name}' and fallbacks: {last_exception}",
            original_error=last_exception,
        )

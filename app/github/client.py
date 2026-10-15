"""Lightweight GitHub REST API client using httpx with rate limiting and timeout management."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
import httpx

logger = logging.getLogger("pr_review_agent.github.client")


class GitHubAPIError(Exception):
    """Exception raised for unrecoverable GitHub API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class RateLimitExceededError(GitHubAPIError):
    """Exception raised when GitHub API rate limit is exhausted."""

    def __init__(self, reset_timestamp: Optional[int] = None):
        msg = f"GitHub API rate limit exceeded. Reset at unix timestamp: {reset_timestamp}"
        super().__init__(msg, status_code=403)
        self.reset_timestamp = reset_timestamp


class GitHubClient:
    """HTTP client specialized for GitHub REST API interaction."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        if not token or not token.strip():
            raise ValueError("A non-empty GitHub token is required.")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHub-PR-Review-Agent/1.0",
        }
        clean_token = token.strip()
        if clean_token and not clean_token.startswith("replace_with"):
            self._headers["Authorization"] = f"Bearer {clean_token}"
        self._client: Optional[httpx.Client] = None

    def __enter__(self) -> GitHubClient:
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def open(self) -> None:
        """Initialize the underlying HTTP transport."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=self._headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )

    def close(self) -> None:
        """Close the underlying HTTP transport."""
        if self._client is not None and not self._client.is_closed:
            self._client.close()
            self._client = None

    @property
    def client(self) -> httpx.Client:
        """Get or initialize client session."""
        if self._client is None or self._client.is_closed:
            self.open()
        assert self._client is not None
        return self._client

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """Inspect rate limit response headers."""
        remaining = response.headers.get("x-ratelimit-remaining")
        reset_time = response.headers.get("x-ratelimit-reset")

        if remaining is not None and remaining == "0":
            reset_ts = int(reset_time) if reset_time and reset_time.isdigit() else None
            raise RateLimitExceededError(reset_timestamp=reset_ts)

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """Execute HTTP request with transient retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API path relative to base_url (e.g., /repos/owner/repo/pulls/1)
            params: Optional query parameters
            json_data: Optional JSON request payload

        Returns:
            httpx.Response on success

        Raises:
            RateLimitExceededError: If rate limit is hit
            GitHubAPIError: On non-transient HTTP errors or exhausted retries
        """
        clean_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        retries = 0

        while True:
            try:
                response = self.client.request(
                    method=method,
                    url=clean_endpoint,
                    params=params,
                    json=json_data,
                )

                self._check_rate_limit(response)

                # Transient server errors: 502, 503, 504
                if response.status_code in {502, 503, 504} and retries < self.max_retries:
                    retries += 1
                    sleep_time = 2.0 ** retries
                    logger.warning(
                        "GitHub API returned %d for %s. Retrying in %.1fs (attempt %d/%d)...",
                        response.status_code,
                        clean_endpoint,
                        sleep_time,
                        retries,
                        self.max_retries,
                    )
                    time.sleep(sleep_time)
                    continue

                if response.is_error:
                    error_preview = response.text[:300].replace("\n", " ")
                    raise GitHubAPIError(
                        f"GitHub API error {response.status_code} on {method} {clean_endpoint}: {error_preview}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                return response

            except httpx.TimeoutException as exc:
                if retries < self.max_retries:
                    retries += 1
                    sleep_time = 2.0 ** retries
                    logger.warning(
                        "Timeout accessing GitHub API %s. Retrying in %.1fs (attempt %d/%d)...",
                        clean_endpoint,
                        sleep_time,
                        retries,
                        self.max_retries,
                    )
                    time.sleep(sleep_time)
                    continue
                raise GitHubAPIError(f"Request timeout accessing GitHub API on {clean_endpoint}") from exc

            except httpx.RequestError as exc:
                raise GitHubAPIError(f"Network error accessing GitHub API: {exc}") from exc

    def get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Perform GET request and return parsed JSON."""
        response = self.request("GET", endpoint, params=params)
        return response.json()

    def post(self, endpoint: str, json_data: dict[str, Any]) -> Any:
        """Perform POST request and return parsed JSON."""
        response = self.request("POST", endpoint, json_data=json_data)
        return response.json()

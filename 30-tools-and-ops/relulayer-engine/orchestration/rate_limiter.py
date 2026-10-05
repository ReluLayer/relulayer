"""Token-bucket + minimum-interval rate limiter for LLM and external API calls.

This module is the concrete enforcement layer for the "no API DDoS" policy.
It lives in Layer 6 (Orchestration & Agents) and is used by DSPy programs,
FastAPI endpoints, and any tool that calls an external service.

Design goals:
- Async-first (FastAPI / DSPy async flows).
- Per-provider configuration.
- Global and per-call budgets.
- Observable via logging.
- No dependencies beyond the Python standard library.

Usage:
    limiter = RateLimiter.for_provider("ollama_local")

    async with limiter.acquire() as ctx:
        response = await my_llm_call(prompt)
        ctx.record_success()

    # Or with retries:
    result = await limiter.call_with_retry(my_llm_call, prompt)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RateLimitPolicy:
    """Policy for a single API provider or endpoint."""

    # Minimum seconds between the *start* of consecutive calls.
    min_interval_seconds: float = 30.0

    # Maximum number of concurrent calls.
    max_concurrent: int = 2

    # Maximum number of calls allowed in a sliding 60-second window.
    max_calls_per_minute: int = 4

    # Seconds to wait after a failure before retrying.
    retry_backoff_seconds: float = 60.0

    # Maximum number of retries per call.
    max_retries: int = 3


class RateLimiterExceededError(Exception):
    """Raised when all retries are exhausted or a hard budget is exceeded."""


class RateLimiter:
    """Token-bucket rate limiter with concurrency control and retry logic.

    Example:
        limiter = RateLimiter.for_provider("ollama_local")

        async with limiter.acquire() as ctx:
            response = await my_llm_call(prompt)
            ctx.record_success()
    """

    _registry: dict[str, RateLimiter] = {}

    def __init__(self, name: str, policy: RateLimitPolicy) -> None:
        self.name = name
        self.policy = policy
        self._semaphore = asyncio.Semaphore(policy.max_concurrent)
        self._last_call_start: float = 0.0
        self._last_call_lock = asyncio.Lock()
        self._window_calls: list[float] = []
        self._window_lock = asyncio.Lock()
        self._call_count: int = 0

    @classmethod
    def for_provider(cls, name: str) -> "RateLimiter":
        """Return a shared limiter for a provider, creating a default if needed."""
        if name not in cls._registry:
            # Default conservative policy: matches the 30-second intent.
            cls._registry[name] = cls(
                name=name,
                policy=RateLimitPolicy(
                    min_interval_seconds=30.0,
                    max_concurrent=2,
                    max_calls_per_minute=4,
                    retry_backoff_seconds=60.0,
                    max_retries=3,
                ),
            )
        return cls._registry[name]

    @classmethod
    def configure(cls, name: str, policy: RateLimitPolicy) -> "RateLimiter":
        """Install or overwrite a provider's policy."""
        limiter = cls(name=name, policy=policy)
        cls._registry[name] = limiter
        return limiter

    async def _wait_for_interval(self) -> None:
        """Enforce the minimum interval between call starts."""
        async with self._last_call_lock:
            now = time.monotonic()
            elapsed = now - self._last_call_start
            if elapsed < self.policy.min_interval_seconds:
                wait = self.policy.min_interval_seconds - elapsed
                logger.info(
                    "[%s] rate-limit sleep %.2fs (min interval)",
                    self.name,
                    wait,
                )
                await asyncio.sleep(wait)
            self._last_call_start = time.monotonic()

    async def _wait_for_budget(self) -> None:
        """Enforce the sliding-window calls-per-minute budget."""
        async with self._window_lock:
            now = time.monotonic()
            cutoff = now - 60.0
            self._window_calls = [t for t in self._window_calls if t > cutoff]
            if len(self._window_calls) >= self.policy.max_calls_per_minute:
                oldest = self._window_calls[0]
                wait = 60.0 - (now - oldest) + 0.1
                logger.warning(
                    "[%s] rate-limit sleep %.2fs (per-minute budget)",
                    self.name,
                    wait,
                )
                await asyncio.sleep(wait)
                self._window_calls = [
                    t for t in self._window_calls if t > time.monotonic() - 60.0
                ]
            self._window_calls.append(time.monotonic())

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator["RateLimitContext"]:
        """Acquire permission to make an API call.

        Usage:
            async with limiter.acquire() as ctx:
                result = await call_api()
                ctx.record_success()
        """
        await self._wait_for_interval()
        await self._wait_for_budget()
        async with self._semaphore:
            self._call_count += 1
            yield RateLimitContext(limiter=self, call_id=self._call_count)

    async def call_with_retry(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call an async function with rate limiting and retry/backoff."""
        last_exception: Exception | None = None
        for attempt in range(1, self.policy.max_retries + 1):
            try:
                async with self.acquire() as ctx:
                    result = await fn(*args, **kwargs)
                    ctx.record_success()
                    return result
            except Exception as exc:  # noqa: BLE001
                last_exception = exc
                logger.warning(
                    "[%s] attempt %d/%d failed: %s",
                    self.name,
                    attempt,
                    self.policy.max_retries,
                    exc,
                )
                if attempt < self.policy.max_retries:
                    logger.info(
                        "[%s] backing off %.2fs before retry",
                        self.name,
                        self.policy.retry_backoff_seconds,
                    )
                    await asyncio.sleep(self.policy.retry_backoff_seconds)
        raise RateLimiterExceededError(
            f"[{self.name}] all {self.policy.max_retries} retries failed"
        ) from last_exception


class RateLimitContext:
    """Context object returned by RateLimiter.acquire()."""

    def __init__(self, limiter: RateLimiter, call_id: int) -> None:
        self.limiter = limiter
        self.call_id = call_id
        self.start_time = time.monotonic()

    def record_success(self) -> None:
        """Log a successful call completion."""
        duration = time.monotonic() - self.start_time
        logger.info(
            "[%s] call #%d completed in %.3fs",
            self.limiter.name,
            self.call_id,
            duration,
        )


# ---------------------------------------------------------------------------
# FastAPI integration (lazy import so this module works without FastAPI installed)
# ---------------------------------------------------------------------------

async def get_ollama_limiter() -> RateLimiter:
    """FastAPI dependency: returns the shared Ollama limiter."""
    return RateLimiter.for_provider("ollama_local")


async def get_openai_limiter() -> RateLimiter:
    """FastAPI dependency: returns the shared OpenAI limiter."""
    return RateLimiter.for_provider("openai")


async def get_rate_limiter_for_request(request: Any) -> RateLimiter:
    """FastAPI dependency: route a request to the correct provider limiter.

    The `request` parameter should be a FastAPI Request object. The provider is
    read from a query parameter or header named `provider`.
    """
    try:
        provider = request.query_params.get("provider", "ollama_local")
    except Exception:  # noqa: BLE001
        provider = "ollama_local"
    return RateLimiter.for_provider(provider)


# ---------------------------------------------------------------------------
# Example integrations
# ---------------------------------------------------------------------------

async def call_ollama(prompt: str, limiter: RateLimiter | None = None) -> str:
    """Example Ollama call with rate limiting."""
    if limiter is None:
        limiter = RateLimiter.for_provider("ollama_local")

    async with limiter.acquire() as ctx:
        # Replace with your actual Ollama client call.
        # import ollama
        # response = await ollama.chat(model="gemma3:12b", messages=[...])
        response = f"Mock response for: {prompt[:40]}..."
        ctx.record_success()
        return response


async def dspy_predict_with_rate_limit(
    module: Callable[..., T],
    input_data: dict[str, Any],
    limiter: RateLimiter | None = None,
) -> T:
    """Wrap a DSPy module forward call with rate limiting.

    If the module is synchronous, it is run in a thread pool to avoid blocking
    the event loop during the rate-limit wait.
    """
    if limiter is None:
        limiter = RateLimiter.for_provider("ollama_local")

    async with limiter.acquire() as ctx:
        result = await asyncio.to_thread(module, **input_data)
        ctx.record_success()
        return result


# ---------------------------------------------------------------------------
# Bootstrap configuration
# ---------------------------------------------------------------------------

def configure_default_providers() -> None:
    """Call once at application startup."""
    RateLimiter.configure(
        "ollama_local",
        RateLimitPolicy(
            min_interval_seconds=30.0,
            max_concurrent=2,
            max_calls_per_minute=4,
            retry_backoff_seconds=60.0,
            max_retries=3,
        ),
    )
    RateLimiter.configure(
        "openai",
        RateLimitPolicy(
            min_interval_seconds=1.0,
            max_concurrent=5,
            max_calls_per_minute=60,
            retry_backoff_seconds=10.0,
            max_retries=2,
        ),
    )
    RateLimiter.configure(
        "stable_diffusion",
        RateLimitPolicy(
            min_interval_seconds=5.0,
            max_concurrent=1,
            max_calls_per_minute=10,
            retry_backoff_seconds=30.0,
            max_retries=2,
        ),
    )
    RateLimiter.configure(
        "sbir_gov",
        RateLimitPolicy(
            min_interval_seconds=2.0,
            max_concurrent=1,
            max_calls_per_minute=20,
            retry_backoff_seconds=30.0,
            max_retries=2,
        ),
    )

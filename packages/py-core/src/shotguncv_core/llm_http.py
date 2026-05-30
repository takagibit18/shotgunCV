"""General-purpose LLM HTTP client with rate limiting, retry, and circuit breaking.

Environment-configurable via .env:

  SHOTGUNCV_LLM_RPM          Max calls per minute (default 60)
  SHOTGUNCV_LLM_RPS          Max calls per second (default 5)
  SHOTGUNCV_LLM_TIMEOUT_SEC  HTTP timeout in seconds (default 30)
  SHOTGUNCV_LLM_MAX_RETRIES  Max retries on transient failure (default 1)

Circuit breaker: after N consecutive failures, skip LLM for M seconds.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ── Rate limiter (token bucket) ──────────────────────────────────────

@dataclass
class RateLimiter:
    """Thread-safe-ish token bucket rate limiter.

    Configured via env vars, works for any LLM provider.
    """
    rpm: int = 60     # calls per minute
    rps: int = 5      # calls per second

    _tokens_per_sec: float = field(init=False)
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.rpm = _env_int("SHOTGUNCV_LLM_RPM", self.rpm)
        self.rps = _env_int("SHOTGUNCV_LLM_RPS", self.rps)
        rate = min(self.rps, self.rpm / 60.0)
        self._tokens_per_sec = max(0.5, rate)
        self._tokens = self.rps
        self._last_refill = time.monotonic()

    def acquire(self) -> bool:
        """Try to acquire a call permit. Returns False if rate-limited."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(float(self.rps), self._tokens + elapsed * self._tokens_per_sec)
        self._last_refill = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    def wait(self, timeout: float = 30.0) -> bool:
        """Block until a permit is available or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.acquire():
                return True
            time.sleep(0.25)
        return False


# ── Circuit breaker ──────────────────────────────────────────────────

@dataclass
class CircuitBreaker:
    """Open after N consecutive failures, reset after M seconds."""
    max_failures: int = 5
    reset_seconds: float = 60.0

    _failures: int = 0
    _opened_at: float = 0.0

    def __post_init__(self) -> None:
        self.max_failures = _env_int("SHOTGUNCV_LLM_CIRCUIT_MAX_FAILURES", self.max_failures)
        self.reset_seconds = float(_env_int("SHOTGUNCV_LLM_CIRCUIT_RESET_SEC", int(self.reset_seconds)))

    @property
    def is_open(self) -> bool:
        if self._failures < self.max_failures:
            return False
        if time.monotonic() - self._opened_at > self.reset_seconds:
            self._failures = 0  # reset after cooldown
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.max_failures:
            self._opened_at = time.monotonic()


# ── Global instances ──────────────────────────────────────────────────

_rate_limiter: RateLimiter | None = None
_circuit_breaker: CircuitBreaker | None = None


def _get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def _get_circuit_breaker() -> CircuitBreaker:
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


def reset_rate_limiter() -> None:
    """Reset global rate limiter (useful for tests)."""
    global _rate_limiter, _circuit_breaker
    _rate_limiter = None
    _circuit_breaker = None


# ── Main LLM HTTP call ────────────────────────────────────────────────

def llm_json_call(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str = "Return strict JSON only. Do not fabricate facts.",
    temperature: float = 0.2,
    max_tokens: int = 1000,
    timeout_sec: int | None = None,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    """Make an LLM JSON API call with rate limiting, retry, and circuit breaking.

    Returns the parsed JSON response dict.
    Raises RuntimeError if circuit breaker is open.
    """
    if timeout_sec is None:
        timeout_sec = _env_int("SHOTGUNCV_LLM_TIMEOUT_SEC", 30)
    max_retries = _env_int("SHOTGUNCV_LLM_MAX_RETRIES", 1)

    limiter = _get_rate_limiter()
    breaker = _get_circuit_breaker()

    if breaker.is_open:
        raise RuntimeError("LLM circuit breaker open — too many consecutive failures")

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        # Wait for rate limit permit
        if not limiter.wait(timeout=float(timeout_sec)):
            last_error = RuntimeError("Rate limit wait timed out")
            breaker.record_failure()
            continue

        try:
            return _http_json_call(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
            )
        except Exception as exc:
            last_error = exc
            breaker.record_failure()
            if breaker.is_open:
                raise RuntimeError(f"LLM circuit breaker opened after {breaker.max_failures} failures") from exc
            # Exponential backoff before retry
            if attempt < max_retries:
                delay = 2.0 ** attempt
                time.sleep(delay)

    breaker.record_failure()
    raise last_error or RuntimeError("LLM call failed after retries")


def _http_json_call(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout_sec: int,
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as handle:
        body: dict[str, Any] = json.loads(handle.read().decode("utf-8"))
        # Record success
        breaker = _get_circuit_breaker()
        breaker.record_success()
        return body


# ── Helpers ───────────────────────────────────────────────────────────

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default

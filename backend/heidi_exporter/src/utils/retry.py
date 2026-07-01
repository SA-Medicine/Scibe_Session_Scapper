from __future__ import annotations

from collections.abc import Callable
from typing import ParamSpec, TypeVar

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

P = ParamSpec("P")
R = TypeVar("R")


RETRYABLE_EXCEPTIONS = (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
    TimeoutError,
)


def selenium_retry(max_attempts: int = 3) -> Callable[[Callable[P, R]], Callable[P, R]]:
    return retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(max_attempts),
        reraise=True,
    )


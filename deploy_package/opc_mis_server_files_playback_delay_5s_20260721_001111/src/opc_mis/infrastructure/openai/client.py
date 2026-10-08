"""OpenAI client construction isolated from business components."""

from openai import AsyncOpenAI


def create_openai_client(*, api_key: str, timeout_seconds: float, max_retries: int) -> AsyncOpenAI:
    """Build a client from environment-resolved settings without logging secrets."""
    return AsyncOpenAI(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )

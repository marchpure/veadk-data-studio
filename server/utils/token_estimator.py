"""Fast token estimation for context management."""

from typing import Any

import tiktoken

from server.utils.conversation_items import conversation_items_to_messages, normalize_content, normalize_tool_calls
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

# Singleton encoder cache for performance
_encoder_cache: dict[str, tiktoken.Encoding] = {}


def get_encoder(encoding_name: str = "cl100k_base") -> tiktoken.Encoding:
    """Get cached tiktoken encoder."""
    if encoding_name not in _encoder_cache:
        _encoder_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
    return _encoder_cache[encoding_name]


def estimate_fast(text: str | None) -> int:
    """
    Fast token approximation (~4 chars per token).
    Use for high-frequency checks (Tier 1).

    Args:
        text: String to estimate tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    return max(1, len(text) // 4)  # Ceil division


def count_exact(text: str | None, model: str = "gpt-4") -> int:
    """
    Exact token count using tiktoken.
    Use for critical limit checks (Tier 2).

    Args:
        text: String to count tokens for
        model: Model name (determines encoding)

    Returns:
        Exact token count
    """
    if not text:
        return 0

    try:
        # Map model to encoding
        encoding_name = _get_encoding_for_model(model)
        encoder = get_encoder(encoding_name)
        return len(encoder.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed for model {model}: {e}, falling back to fast estimate")
        return estimate_fast(text)


def _get_encoding_for_model(model: str) -> str:
    """Map model name to tiktoken encoding."""
    model_lower = model.lower()

    # GPT-4, GPT-5, GPT-3.5-turbo use cl100k_base
    if any(x in model_lower for x in ["gpt-4", "gpt-5", "gpt-3.5-turbo"]):
        return "cl100k_base"

    # Claude models (approximate with cl100k_base)
    if "claude" in model_lower:
        return "cl100k_base"

    # Default
    return "cl100k_base"


def estimate_messages_tokens_fast(messages: list[dict[str, Any]]) -> int:
    """
    Fast estimate of total tokens in conversation.

    Args:
        messages: List of message dicts with 'role' and 'content'

    Returns:
        Estimated total tokens
    """
    normalized_messages = conversation_items_to_messages(messages)

    total = 0
    for msg in normalized_messages:
        # Message overhead (role, formatting) ~4 tokens
        total += 4

        # Content
        content = normalize_content(msg.get("content", ""))
        if content:
            total += estimate_fast(content)

        # Tool calls (if present)
        tool_calls = normalize_tool_calls(msg.get("tool_calls", []) or [])
        for tc in tool_calls:
            # Tool call overhead
            total += 10
            # Arguments
            args = tc.get("function", {}).get("arguments", "")
            total += estimate_fast(str(args))

    return total

"""Token counting utilities using litellm for conversation analysis."""

from typing import Any

from litellm.utils import token_counter

from server.utils.conversation_items import conversation_items_to_messages
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def count_conversation_tokens(messages: list[dict[str, Any]], model: str = "gpt-4") -> dict[str, Any]:
    """
    Count tokens in conversation using litellm.

    Args:
        messages: List of message dictionaries with 'role' and 'content'
        model: Model name for tokenization (default: gpt-4)

    Returns:
        Dictionary containing:
            - total_tokens: Total token count for all messages
            - by_role: Token breakdown by message role
            - message_count: Number of messages
    """
    if not messages:
        return {"total_tokens": 0, "by_role": {}, "message_count": 0}

    # Normalize mixed session items (function calls, tool outputs, etc.) into chat messages
    messages = conversation_items_to_messages(messages)

    try:
        # Count total tokens for the entire conversation
        total = token_counter(model=model, messages=messages)

        # Count tokens by role
        by_role: dict[str, int] = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            try:
                # Count tokens for individual message
                msg_tokens = token_counter(model=model, messages=[msg])
                by_role[role] = by_role.get(role, 0) + msg_tokens
            except Exception as msg_error:
                logger.warning(f"Failed to count tokens for message with role {role}: {msg_error}")
                continue

        return {
            "total_tokens": total,
            "by_role": by_role,
            "message_count": len(messages),
        }
    except Exception as e:
        logger.error(f"Token counting failed: {e}", exc_info=True)
        return {"total_tokens": 0, "by_role": {}, "message_count": len(messages)}


def estimate_tokens_saved(
    original_messages: list[dict[str, Any]],
    compacted_messages: list[dict[str, Any]],
    model: str = "gpt-4",
) -> dict[str, Any]:
    """
    Calculate token savings from conversation compaction.

    Args:
        original_messages: Original message list
        compacted_messages: Compacted message list
        model: Model name for tokenization

    Returns:
        Dictionary with before/after stats and savings
    """
    original_stats = count_conversation_tokens(original_messages, model)
    compacted_stats = count_conversation_tokens(compacted_messages, model)

    tokens_saved = original_stats["total_tokens"] - compacted_stats["total_tokens"]
    reduction_percentage = (
        (tokens_saved / original_stats["total_tokens"] * 100) if original_stats["total_tokens"] > 0 else 0
    )

    return {
        "tokens_before": original_stats["total_tokens"],
        "tokens_after": compacted_stats["total_tokens"],
        "tokens_saved": tokens_saved,
        "reduction_percentage": round(reduction_percentage, 2),
        "messages_before": original_stats["message_count"],
        "messages_after": compacted_stats["message_count"],
        "messages_removed": original_stats["message_count"] - compacted_stats["message_count"],
    }

"""Cache control utilities for LLM prompt caching.

This module provides utilities for LiteLLM's native prompt caching support.
Uses LiteLLM's `cache_control_injection_points` parameter for automatic injection.

LiteLLM handles provider-specific transformations automatically:
- Anthropic (direct): Preserves cache_control as-is
- Bedrock Claude: Auto-converts cache_control → cachePoint
- OpenRouter Claude: Passes through to Anthropic API

Automatic caching (no config needed):
- OpenAI, Groq, Gemini, DeepSeek, Grok

See:
- https://docs.litellm.ai/docs/tutorials/prompt_caching
- https://docs.litellm.ai/docs/completion/prompt_caching
- https://deepwiki.com/BerriAI/litellm/8.2-context-and-prompt-caching
"""

from __future__ import annotations

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def get_cache_control_injection_points(model: str | None) -> list[dict] | None:
    """
    Get LiteLLM cache_control_injection_points config for models that need explicit caching.

    Only Claude models require explicit cache_control injection.
    LiteLLM automatically handles provider-specific formats:
    - anthropic/* → cache_control preserved
    - bedrock/*claude* → cache_control auto-converted to cachePoint
    - openrouter/anthropic/* → passed through to Anthropic

    OpenAI, Groq, Gemini, etc. have automatic caching - returns None for them.

    Args:
        model: Model string. Supports all Claude model formats:
            - "anthropic/claude-3-5-sonnet" (direct Anthropic)
            - "bedrock/anthropic.claude-3" (AWS Bedrock)
            - "openrouter/anthropic/claude-sonnet-4" (OpenRouter)

    Returns:
        List of injection point configs for Claude models, None for others.

    Example:
        >>> get_cache_control_injection_points("anthropic/claude-3-5-sonnet")
        [{"location": "message", "role": "system"}, {"location": "message", "index": -1}]

        >>> get_cache_control_injection_points("bedrock/anthropic.claude-3")
        [{"location": "message", "role": "system"}, {"location": "message", "index": -1}]

        >>> get_cache_control_injection_points("openai/gpt-5")
        None
    """
    if not model:
        return None

    model_lower = model.lower()

    # Only Claude models need explicit cache_control
    # Works for: openrouter/anthropic/*, anthropic/*, bedrock/*claude*, claude-*
    if "claude" not in model_lower:
        logger.debug(f"Model {model} has automatic caching, no injection points needed")
        return None

    logger.info(f"Model {model} needs cache_control, returning injection points")

    # LiteLLM's cache_control_injection_points format
    # - Cache system message (instructions, schema - rarely changes)
    # - Cache last message (recent context)
    # Anthropic limit: max 4 blocks with cache_control per request
    return [
        {"location": "message", "role": "system"},
        {"location": "message", "index": -1},  # Last message
    ]

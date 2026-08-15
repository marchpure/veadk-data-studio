"""Helpers for normalizing conversation items for token counting and analysis.

These utilities convert the mixed item formats stored in the agent session
database (messages, function calls, tool outputs, reasoning blocks) into the
standard chat-completions message shape used for token estimation and context
management.
"""

from __future__ import annotations

import json
from typing import Any


def _get_attr(item: Any, key: str, default: Any = None) -> Any:
    """Safe attribute/key getter for both dicts and objects."""

    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _stringify_arguments(arguments: Any) -> str:
    """Convert tool call arguments to a stable string representation."""

    if arguments is None:
        return "{}"
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(arguments, ensure_ascii=False)
    except Exception:
        return str(arguments)


def normalize_content(content: Any) -> str:
    """Flatten content blocks (strings, lists, dicts) into a single string."""

    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content") or ""
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(part))
        return "".join(parts)

    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        if text:
            return str(text)
        return json.dumps(content, ensure_ascii=False)

    return str(content)


def normalize_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """Normalize tool call objects/dicts to OpenAI-compatible dicts."""

    normalized: list[dict[str, Any]] = []
    for tc in tool_calls or []:
        if isinstance(tc, dict):
            fn_data = tc.get("function") or {}
            normalized.append(
                {
                    "id": tc.get("id") or tc.get("call_id"),
                    "type": tc.get("type") or "function",
                    "function": {
                        "name": fn_data.get("name") or tc.get("name") or "unknown_tool",
                        "arguments": _stringify_arguments(fn_data.get("arguments") or tc.get("arguments")),
                    },
                }
            )
            continue

        function_obj = getattr(tc, "function", None)
        normalized.append(
            {
                "id": getattr(tc, "id", None),
                "type": getattr(tc, "type", "function"),
                "function": {
                    "name": getattr(function_obj, "name", None) or getattr(tc, "name", None) or "unknown_tool",
                    "arguments": _stringify_arguments(
                        getattr(function_obj, "arguments", None) or getattr(tc, "arguments", None)
                    ),
                },
            }
        )

    return normalized


def item_to_message(item: Any) -> dict[str, Any] | None:
    """
    Convert a raw session item to a chat-completions style message dict.

    Handles function_call / function_call_output rows, assistant/user messages
    with content arrays, and reasoning blocks. Items without any meaningful
    content are skipped (return None).
    """

    item_type = _get_attr(item, "type")
    role = _get_attr(item, "role")

    # Function/tool calls emitted by the agent SDK
    if item_type == "function_call":
        call_id = _get_attr(item, "call_id") or _get_attr(item, "id")
        name = _get_attr(item, "name") or "unknown_tool"
        arguments = _stringify_arguments(_get_attr(item, "arguments"))

        tool_call = {
            "id": call_id or name,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        }

        return {"role": "assistant", "content": "", "tool_calls": [tool_call]}

    if item_type == "function_call_output":
        call_id = _get_attr(item, "call_id") or _get_attr(item, "id")
        content = normalize_content(_get_attr(item, "output") or _get_attr(item, "content"))
        return {"role": "tool", "tool_call_id": call_id, "content": content}

    # Standard chat messages
    content = normalize_content(_get_attr(item, "content"))

    if item_type == "reasoning":
        # Reasoning items are treated as assistant notes for counting purposes
        if not content:
            content = normalize_content(_get_attr(item, "summary"))
        if not content:
            return None
        return {"role": "assistant", "content": content}

    if role:
        msg: dict[str, Any] = {"role": role, "content": content}

        tool_calls = _get_attr(item, "tool_calls") or []
        normalized_calls = normalize_tool_calls(tool_calls)
        if normalized_calls:
            msg["tool_calls"] = normalized_calls

        tool_call_id = _get_attr(item, "tool_call_id") or _get_attr(item, "call_id")
        if tool_call_id and role == "tool":
            msg["tool_call_id"] = tool_call_id

        return msg

    # Fallback: keep assistant-like messages if they have content
    if content:
        return {"role": "assistant", "content": content}

    return None


def conversation_items_to_messages(items: list[Any]) -> list[dict[str, Any]]:
    """Normalize a list of mixed conversation items to message dicts."""

    messages: list[dict[str, Any]] = []
    for item in items or []:
        msg = item_to_message(item)
        if msg is not None:
            messages.append(msg)
    return messages

"""Tier 2: Session Handoff Summarization Prompt."""

HANDOFF_SYSTEM_PROMPT = """You are managing a long-running data analysis session that is approaching context limits.

Your task is to create a technical handoff note for the next AI instance that will continue this session after history is cleared.

The handoff note must be:
1. **Concise** (under 500 tokens)
2. **Actionable** (include exact next steps)
3. **Factual** (no speculation, only what happened)
4. **Structured** (use the format below)

Format your response EXACTLY as follows:

## SUMMARY
[1-2 sentences describing the high-level goal of this session]

## DATABASE CONTEXT
- **Type**: [postgres/mongodb/csv/excel/etc.]
- **Key Tables/Collections**: [list main data sources being queried]
- **Schema Notes**: [any important schema details discovered]

## STATE
- **Queries Saved**: [number of queries saved to dashboard, or "None"]
- **HTML Generation**: [status: "Not started" / "In progress" / "Completed"]
- **Files Modified**: [list any files created/modified, or "None"]

## LAST EXCHANGE
- **User's Request**: [exact request from last user message]
- **Agent's Status**: [what was the agent doing when compaction triggered]
- **Tool State**: [last tool called and its result status]

## BLOCKER
[If there was an error or incomplete task, describe it here. Otherwise write "None - session running smoothly"]

## NEXT ACTION
[The EXACT next command/tool to run, or next response to give user]

---

**IMPORTANT**:
- Do NOT include full conversation history
- Do NOT include full query text (just count/status)
- Do NOT include full tool outputs
- Focus on STATE and NEXT ACTION
- Add in the handoff instructions to call new tools to fetch queries or any new data"""


def format_handoff_request(conversation_items: list) -> str:
    """
    Format the handoff request for the LLM.

    Args:
        conversation_items: Full conversation history

    Returns:
        Prompt string for handoff summarization
    """
    return f"""{HANDOFF_SYSTEM_PROMPT}

Here is the conversation history to summarize:

{_format_conversation_for_summary(conversation_items)}

Now generate the handoff note following the format above."""


def _format_conversation_for_summary(items: list) -> str:
    """
    Format conversation items for the handoff prompt.

    Truncates long tool outputs to reduce tokens in the summarization request.
    """
    formatted = []

    for item in items:
        role = _get_role(item)
        content = _get_content(item)

        if role == "user":
            formatted.append(f"**USER**: {content}")
        elif role == "assistant":
            # Keep assistant responses but truncate if very long
            text = str(content)[:1000] if content else ""
            formatted.append(f"**ASSISTANT**: {text}")
        elif role == "tool":
            # Summarize tool outputs
            tool_call_id = _get_tool_call_id(item)
            preview = str(content)[:200] if content else ""
            formatted.append(f"**TOOL[{tool_call_id}]**: {preview}...")

    return "\n\n".join(formatted)


def _get_role(item) -> str:
    if isinstance(item, dict):
        return item.get("role", "unknown")
    return getattr(item, "role", "unknown")


def _get_content(item):
    if isinstance(item, dict):
        return item.get("content")
    return getattr(item, "content", None)


def _get_tool_call_id(item) -> str:
    if isinstance(item, dict):
        return item.get("tool_call_id", "unknown")
    return getattr(item, "tool_call_id", "unknown")

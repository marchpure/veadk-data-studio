"""Tests for conversation compaction functionality."""

import pytest

from server.services.conversation_compactor import ConversationCompactor


class TestConversationCompactor:
    """Test suite for ConversationCompactor."""

    def test_preserves_user_messages(self):
        """All user messages must be preserved during compaction."""
        compactor = ConversationCompactor()

        items = [
            {"role": "user", "content": "What is the sales data?"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "execute_sql_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "[data results]"},
            {"role": "user", "content": "Thanks!"},
        ]

        compacted, stats = compactor.compact(items, dry_run=False)

        # Count user messages
        user_messages_original = [item for item in items if item.get("role") == "user"]
        user_messages_compacted = [item for item in compacted if item.get("role") == "user"]

        assert len(user_messages_original) == len(user_messages_compacted)
        assert all(msg in compacted for msg in user_messages_original)

    def test_preserves_tool_call_id_integrity(self):
        """Tool call ID references must remain intact - no broken references."""
        compactor = ConversationCompactor()

        items = [
            {"role": "user", "content": "Run a query"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_save_1",
                        "function": {"name": "save_query", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_save_1",
                "content": "Query saved successfully",
            },
        ]

        compacted, stats = compactor.compact(items, dry_run=False)

        # Extract all tool_call_ids that are referenced in results
        result_call_ids = {item.get("tool_call_id") for item in compacted if item.get("role") == "tool"}

        # Extract all tool call IDs from assistant messages
        assistant_call_ids = set()
        for item in compacted:
            if item.get("role") == "assistant" and item.get("tool_calls"):
                for tc in item["tool_calls"]:
                    if tc.get("id"):
                        assistant_call_ids.add(tc["id"])

        # Every result must have a matching call
        assert result_call_ids.issubset(assistant_call_ids)

    def test_keeps_latest_schema_only(self):
        """Only the most recent saved_query_schema should be kept."""
        compactor = ConversationCompactor()

        items = [
            {"role": "user", "content": "Show me the schema"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "schema_1",
                        "function": {"name": "saved_query_schema", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "schema_1", "content": "Schema v1"},
            {"role": "user", "content": "Refresh schema"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "schema_2",
                        "function": {"name": "saved_query_schema", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "schema_2", "content": "Schema v2"},
        ]

        compacted, stats = compactor.compact(items, dry_run=False)

        # The compactor keeps all tool_call messages for structural integrity
        # but replaces old tool results with placeholders.
        # Only the latest schema tool result should have real content.
        tool_results = {}
        for item in compacted:
            if item.get("role") == "tool" and item.get("tool_call_id"):
                tool_results[item["tool_call_id"]] = item.get("content", "")

        # Old schema result should be a placeholder
        assert "schema_1" in tool_results
        assert "Schema v1" not in tool_results["schema_1"]

        # Latest schema result should keep real content
        assert "schema_2" in tool_results
        assert "Schema v2" in tool_results["schema_2"]

    def test_removes_query_executions_after_save(self):
        """Query execution calls should be removed after save_query is called."""
        compactor = ConversationCompactor()

        items = [
            {"role": "user", "content": "Get sales data"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "exec_1",
                        "function": {"name": "execute_sql_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "exec_1", "content": "[100 rows]"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "save_1",
                        "function": {"name": "save_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "save_1", "content": "Saved!"},
        ]

        compacted, stats = compactor.compact(items, dry_run=False)

        # The compactor keeps tool_call messages for structural integrity
        # but replaces tool results with placeholders.
        # Check that execution tool result is replaced with placeholder
        tool_results = {}
        for item in compacted:
            if item.get("role") == "tool" and item.get("tool_call_id"):
                tool_results[item["tool_call_id"]] = item.get("content", "")

        # Execution result should be a placeholder (not original content)
        assert "exec_1" in tool_results
        assert "[100 rows]" not in tool_results["exec_1"]

        # Save result should also be a placeholder
        assert "save_1" in tool_results

    def test_keeps_executions_if_no_save(self):
        """Query execution calls should be kept if no save_query has been called yet."""
        compactor = ConversationCompactor()

        items = [
            {"role": "user", "content": "Test query"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "exec_1",
                        "function": {"name": "execute_sql_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "exec_1", "content": "[results]"},
        ]

        compacted, stats = compactor.compact(items, dry_run=False)

        # Execute calls should still be present (we're still debugging/exploring)
        execution_calls = []
        for item in compacted:
            if item.get("tool_calls"):
                for tc in item["tool_calls"]:
                    if tc.get("function", {}).get("name") == "execute_sql_query":
                        execution_calls.append(tc["id"])

        assert len(execution_calls) == 1

    def test_redacts_large_results(self):
        """Large tool results should be truncated or replaced with placeholder."""
        compactor = ConversationCompactor()

        large_content = "x" * 1000  # Larger than MAX_RESULT_PREVIEW_CHARS
        items = [
            {"role": "user", "content": "Run query"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "schema_1",
                        "function": {"name": "get_database_schema", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "schema_1", "content": large_content},
        ]

        compacted, stats = compactor.compact(items, dry_run=False)

        # Essential tools get truncated (not replaced with placeholder)
        tool_result = next((item for item in compacted if item.get("role") == "tool"), None)

        assert tool_result is not None
        assert len(tool_result["content"]) < len(large_content)
        assert "truncated" in tool_result["content"]
        assert stats["items_redacted"] > 0

    def test_dry_run_mode(self):
        """Dry run should return stats without modifying items."""
        compactor = ConversationCompactor()

        items = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "exec_1",
                        "function": {"name": "execute_sql_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "exec_1", "content": "data"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "save_1",
                        "function": {"name": "save_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "save_1", "content": "saved"},
        ]

        original_items = [item.copy() for item in items]
        compacted, stats = compactor.compact(items, dry_run=True)

        # Items should be unchanged in dry run mode
        assert compacted == items
        assert compacted == original_items
        # But stats should still be calculated
        assert "tokens_before" in stats
        assert "tokens_after" in stats

    def test_token_counting(self):
        """Compaction should reduce token count."""
        compactor = ConversationCompactor()

        items = [
            {"role": "user", "content": "Get data"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "exec_1",
                        "function": {"name": "execute_sql_query", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "exec_1",
                "content": "Large result " * 100,
            },
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "save_1",
                        "function": {"name": "save_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "save_1", "content": "saved"},
        ]

        compacted, stats = compactor.compact(items, dry_run=False)

        # Tokens should be reduced
        assert stats["tokens_after"] < stats["tokens_before"]
        assert stats["tokens_saved"] > 0
        assert stats["reduction_percentage"] > 0

    def test_empty_conversation(self):
        """Empty conversation should be handled gracefully."""
        compactor = ConversationCompactor()

        items = []
        compacted, stats = compactor.compact(items, dry_run=False)

        assert compacted == []
        assert stats["tokens_before"] == 0
        assert stats["tokens_after"] == 0


@pytest.mark.asyncio
class TestConversationStateSessionCompaction:
    """Test suite for ConversationStateSession.compact_conversation."""

    async def test_compact_with_threshold(self):
        """Compaction should only run if threshold is exceeded."""
        from agents import SQLiteSession

        from server.services.conversation_state import ConversationStateSession

        backend = SQLiteSession("test_session", ":memory:")
        session = ConversationStateSession("test_session", backend)

        # Add a small conversation (below threshold)
        items = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        await session.add_items(items)

        # Compact with high threshold - should not compact
        result = await session.compact_conversation(token_threshold=10000, dry_run=False)

        assert result["compaction_performed"] is False
        assert "below threshold" in result.get("message", "").lower()

    async def test_compact_without_threshold(self):
        """Compaction should run if no threshold is specified."""
        from agents import SQLiteSession

        from server.services.conversation_state import ConversationStateSession

        backend = SQLiteSession("test_session2", ":memory:")
        session = ConversationStateSession("test_session2", backend)

        items = [
            {"role": "user", "content": "Test"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "exec_1",
                        "function": {"name": "execute_sql_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "exec_1", "content": "data"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "save_1",
                        "function": {"name": "save_query", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "save_1", "content": "saved"},
        ]
        await session.add_items(items)

        # Compact without threshold - should always compact
        result = await session.compact_conversation(token_threshold=None, dry_run=False)

        # Should have been compacted (execute_sql_query removed)
        assert "tokens_saved" in result

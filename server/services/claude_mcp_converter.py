"""
Helper to convert OpenAI Agents SDK tools to Claude Agent SDK MCP tools
------------------------------------------------------------------------
This enables using Claude Code OAuth with our existing tool functions.
"""

import json
from collections.abc import Callable
from typing import Any

from agents import FunctionTool, RunContextWrapper
from claude_agent_sdk import tool

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def convert_openai_tool_to_mcp(openai_tool: FunctionTool, context_getter: Any = None) -> Callable:
    """
    Convert an OpenAI Agents SDK FunctionTool to a Claude MCP @tool decorated function.

    Args:
        openai_tool: OpenAI FunctionTool object
        context_getter: Optional callable that returns the current context dict

    Returns:
        Claude MCP tool function decorated with @tool

    Example:
        >>> from server.tools.sql import execute_sql_query
        >>> mcp_tool = convert_openai_tool_to_mcp(execute_sql_query)
    """
    # Extract metadata from OpenAI tool
    tool_name = openai_tool.name
    tool_description = openai_tool.description
    params_schema = openai_tool.params_json_schema

    # logger.info(f"[MCP] Converting OpenAI tool '{tool_name}' to MCP format")

    # Create wrapper function that calls the original OpenAI tool
    async def mcp_wrapper(*args, **kwargs) -> str:
        """
        MCP wrapper that executes the underlying OpenAI tool.

        Claude MCP tools receive simple kwargs, but OpenAI tools expect:
        - ctx: RunContextWrapper
        - input: dict of parameters

        This wrapper adapts between the two interfaces.
        """
        try:
            # Get current context from context_getter if provided
            current_context = context_getter() if context_getter and callable(context_getter) else {}
            logger.info(f"[MCP CONVERTER] Tool {tool_name} - context id: {id(current_context)}")

            # Create context wrapper
            ctx = RunContextWrapper(context=current_context)
            ctx.tool_name = tool_name

            # Handle positional args - MCP SDK might pass tool input as first arg
            if args and len(args) > 0:
                # If first arg is a dict, use it as tool_input
                if isinstance(args[0], dict):
                    tool_input = args[0]
                else:
                    tool_input = kwargs
            else:
                # OpenAI tools expect input as a dict, MCP provides kwargs
                tool_input = kwargs

            # Call the original OpenAI tool's on_invoke_tool method
            if hasattr(openai_tool, "on_invoke_tool"):
                # OpenAI Agents SDK expects input as a JSON string, not a dict
                if isinstance(tool_input, dict):
                    tool_input_json = json.dumps(tool_input)
                else:
                    tool_input_json = tool_input

                result = await openai_tool.on_invoke_tool(ctx=ctx, input=tool_input_json)
                result_str = str(result)

                # MCP tools must return dict with content array, not plain string
                mcp_response = {"content": [{"type": "text", "text": result_str}]}

                return mcp_response
            else:
                raise AttributeError(f"Tool {tool_name} missing on_invoke_tool method")

        except Exception as e:
            logger.error(f"[MCP] Error executing tool {tool_name}: {e}", exc_info=True)
            error_text = json.dumps({"error": str(e), "tool_name": tool_name})
            return {"content": [{"type": "text", "text": error_text}]}

    # Set function metadata for MCP
    mcp_wrapper.__name__ = tool_name
    mcp_wrapper.__doc__ = tool_description

    # Apply @tool decorator with schema, @tool REQUIRES input_schema parameter
    decorated_tool = tool(
        name=tool_name,
        description=tool_description,
        input_schema=params_schema,
    )(mcp_wrapper)

    # logger.info(f"[MCP] Successfully converted '{tool_name}' to MCP tool")

    return decorated_tool


def convert_openai_tools_batch(openai_tools: list[FunctionTool], context_getter: Any = None) -> list[Callable]:
    """
    Convert a batch of OpenAI tools to Claude MCP tools.

    Args:
        openai_tools: List of OpenAI FunctionTool objects
        context_getter: Optional callable that returns the current context dict

    Returns:
        List of Claude MCP tool functions
    """
    mcp_tools = []

    for openai_tool in openai_tools:
        try:
            mcp_tool = convert_openai_tool_to_mcp(openai_tool, context_getter)
            mcp_tools.append(mcp_tool)
        except Exception as e:
            tool_name = getattr(openai_tool, "name", "unknown")
            logger.error(f"[MCP] Failed to convert tool '{tool_name}': {e}")
            continue

    logger.info(f"[MCP] Converted {len(mcp_tools)}/{len(openai_tools)} tools successfully")

    return mcp_tools

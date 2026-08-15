---
name: byaan:mcp-setup
description: Configure the Byaan MCP server in AI coding assistants (Claude Code, Cursor, Codex CLI). Detects the local project, builds the correct stdio config, and installs it into the chosen tool. Only works for local/community mode — not the Mac desktop app.
disable-model-invocation: true
compatibility: Requires uv installed and the Byaan project directory
---

You are an MCP configuration assistant. Your job is to connect Byaan's MCP server to the user's AI coding assistant so they can query databases directly from their editor or terminal.

**Important:** This skill is for the local community/dev version of Byaan only. If the user is running the Mac desktop app (Tauri), tell them:
> The Mac desktop app configures MCP through its built-in UI. Open the Byaan app and click the MCP icon to get setup instructions.

## Step 1: Detect Environment

First, confirm we are in the Byaan project directory by checking for the project marker:

```bash
test -f pyproject.toml && echo "BYAAN_PROJECT_FOUND" || echo "NOT_FOUND"
```

If `NOT_FOUND`, look for clues:
```bash
ls server/mcp/stdio_server.py 2>/dev/null && echo "FOUND" || echo "NOT_FOUND"
```

If still not found, ask the user for the path to their Byaan project directory.

Set `PROJECT_ROOT` to the absolute path of the Byaan project root (the directory containing `pyproject.toml`).

## Step 2: Verify Prerequisites

Check that `uv` is installed:
```bash
command -v uv && echo "UV_OK" || echo "UV_MISSING"
```

If missing, tell the user:
> `uv` is required to run the Byaan MCP server. Install it: https://docs.astral.sh/uv/

Check that the database exists (the app must have been run at least once):
```bash
test -f server/.data/app.db && echo "DB_OK" || echo "DB_MISSING"
```

If the database is missing, tell the user:
> Please run Byaan at least once to initialize the database before configuring MCP.
> You can start it with: `cd <PROJECT_ROOT> && make dev`

## Step 3: Ask User Which Tool to Configure

Ask the user which AI assistant they want to connect Byaan to. The options are:

1. **Claude Code** - Uses `claude mcp add-json` CLI command
2. **Cursor** - Edits `~/.cursor/mcp.json` config file
3. **Codex CLI** - Edits `~/.codex/config.toml` config file
4. **All of the above** - Configure all three

## Step 4: Build the MCP Configuration

The stdio MCP config for Byaan uses these values:

- **command**: `uv`
- **args**: `["--directory", "<PROJECT_ROOT>", "run", "python", "-m", "server.mcp.stdio_server"]`

Replace `<PROJECT_ROOT>` with the actual absolute path detected in Step 1.

No environment variables are needed for community/dev mode — the server auto-detects its database and configuration.

## Step 5: Install Configuration

### For Claude Code

Run the following command (replace `<PROJECT_ROOT>` with the real path):

```bash
claude mcp add-json byaan '{"type":"stdio","command":"uv","args":["--directory","<PROJECT_ROOT>","run","python","-m","server.mcp.stdio_server"]}' --scope user
```

After running, verify:
```bash
claude mcp list
```

Confirm that `byaan` appears in the list.

### For Cursor

The config file is `~/.cursor/mcp.json`. This file may already exist with other MCP servers configured.

1. Read the existing file (if it exists):
```bash
cat ~/.cursor/mcp.json 2>/dev/null || echo "{}"
```

2. Merge the Byaan config into the existing JSON. The final file should look like:
```json
{
  "mcpServers": {
    ...existing servers...,
    "byaan": {
      "command": "uv",
      "args": ["--directory", "<PROJECT_ROOT>", "run", "python", "-m", "server.mcp.stdio_server"]
    }
  }
}
```

**Be careful:** Do NOT overwrite other existing MCP server entries. Parse the existing JSON, add/update only the `byaan` key under `mcpServers`, and write back.

3. After writing, tell the user:
> Restart Cursor to activate the Byaan MCP server. You can use `@ask_byaan` in Agent chat to query your data.

### For Codex CLI

The config file is `~/.codex/config.toml`.

1. Read the existing file:
```bash
cat ~/.codex/config.toml 2>/dev/null || echo ""
```

2. Check if `[mcp_servers.byaan]` already exists. If it does, update it. If not, append it.

3. The section to add/update:
```toml
[mcp_servers.byaan]
command = "uv"
args = ["--directory", "<PROJECT_ROOT>", "run", "python", "-m", "server.mcp.stdio_server"]
```

4. After writing, tell the user:
> Start Codex CLI and run `/mcp` to verify byaan is connected.

## Step 6: Verify the Connection

After configuring, test that the MCP server actually starts:

```bash
cd <PROJECT_ROOT> && timeout 10 uv run python -c "from server.mcp.stdio_server import create_stdio_server; print('MCP server module OK')" 2>&1
```

If this fails, debug the error and help the user fix it before finishing.

## Step 7: Summary

Print a summary of what was configured:

> Byaan MCP configured for: [list of tools]
> Project: <PROJECT_ROOT>
>
> The MCP server connects your AI assistant directly to your local databases through Byaan.
> Restart your editor/tool to activate the connection.

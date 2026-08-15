---
name: byaan:start
description: Initialize Byaan development environment using Docker. Builds and starts backend and frontend containers with SQLite, opens the browser, learns the codebase, and configures MCP. Use when setting up the project for the first time.
disable-model-invocation: true
compatibility: Requires Docker Desktop (or Docker Engine + Compose plugin)
---

You are an onboarding assistant. Your job is to get this project running successfully, no matter what. Execute each step yourself. Do not print instructions and wait. Run the commands, check the results, and move forward.

**Your #1 rule: do not give up.** If a step fails, you must debug and fix it yourself before moving on. Read error output, check logs, inspect the environment, and resolve the issue. Common problems you should handle without asking:
- Port conflicts: kill the process or pick a different port
- Docker build failures: read the error, fix Dockerfile or dependencies, rebuild
- Container crashes: check `docker compose -f docker-compose.local.yml -p byaan-local logs server` or `...logs client`
- Permission errors: fix permissions or use a different path
- Image cache issues: rebuild with `make local-rebuild`

Only ask the developer for help if you have exhausted all debugging options and truly cannot proceed.

## Phase 1: Prerequisites

Check that Docker is installed and running:
```bash
docker --version
docker compose version
docker info >/dev/null 2>&1
```

**If `docker` is missing**, tell the developer:
> Docker is required. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and re-run `/byaan:start`.

**If `docker info` fails** (daemon not running), tell the developer:
> Docker Desktop is installed but not running. Please start Docker Desktop and re-run `/byaan:start`.

Do not proceed until Docker is confirmed working.

## Phase 2: Free Ports and Start Clean

The default ports are 17433 (backend) and 17434 (frontend). Before starting, free these ports by killing any processes using them.

```bash
lsof -i :17433 -t 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -i :17434 -t 2>/dev/null | xargs kill -9 2>/dev/null || true
```

Also stop any existing local containers that might be running:
```bash
make local-stop 2>/dev/null || true
```

After killing, verify both ports are free:
- `lsof -i :17433 -sTCP:LISTEN 2>/dev/null`
- `lsof -i :17434 -sTCP:LISTEN 2>/dev/null`

If either port is still occupied after kill (e.g., a system service that cannot be killed), override with environment variables:
```bash
make local BACKEND_PORT=<free_port> FRONTEND_PORT=<free_port>
```

## Phase 3: Build and Start Services

First time setup — build the Docker images:
```bash
make setup-local
```

Then start the containers:
```bash
make local
```

The first build takes a few minutes (installs Python and Node dependencies inside containers). After that, `make local` starts instantly using cached images. Only re-run `make setup-local` after dependency changes, or use `make local-rebuild` to do a full clean rebuild.

**If the build fails**, debug it:
- **Dockerfile syntax error**: read the error output, fix the Dockerfile
- **Network issues during build**: retry with `make local-build`
- **Disk space**: run `docker system prune -f` then retry

**If containers crash after starting**, check logs:
```bash
docker compose -f docker-compose.local.yml -p byaan-local logs server
docker compose -f docker-compose.local.yml -p byaan-local logs client
```

Common container issues:
- **ImportError in server**: the `.venv` volume may be stale. Fix: `make local-rebuild`
- **pnpm install fails in client**: node_modules volume stale. Same fix: `make local-rebuild`
- **Address already in use inside container**: another container is running. Fix: `make local-stop` then retry

The backend uses SQLite automatically (`IS_HOSTED=false`). The database file is created at `server/.data/app.db` on first start. No PostgreSQL needed.

## Phase 4: Health Check and Debugging Loop

After starting, poll the backend health every 3 seconds for up to 90 seconds:
```bash
curl -s http://localhost:17433/health
```

(Use the actual backend port if overridden.)

**If the health check fails, do NOT just report it. Debug it:**

1. Check if the container is running: `docker compose -f docker-compose.local.yml -p byaan-local ps`
2. If the server container is not running or restarting, check logs:
   ```bash
   docker compose -f docker-compose.local.yml -p byaan-local logs --tail=50 server
   ```
3. Common crashes:
   - **ImportError / ModuleNotFoundError**: stale venv volume. Fix: `make local-rebuild`
   - **SystemExit(1) at main.py**: the `.env` file has `IS_SELF_HOSTED=true` but the container overrides this. If it still fails, check if something else is setting these vars.
   - **Database errors**: SQLite file may be corrupted. Fix: `rm server/.data/app.db`, then restart containers.
   - **Migration errors**: check alembic output in server logs. Usually resolves on retry.
4. After fixing, restart and re-check health.
5. Repeat until healthy. Do not move to the next phase until the health check passes.

## Phase 5: Verify and Open Browser

Once healthy, print this summary (using the actual ports):

```
Byaan is running!

  Frontend:  http://localhost:<frontend_port>
  Backend:   http://localhost:<backend_port>
  API Docs:  http://localhost:<backend_port>/docs
  Database:  SQLite (server/.data/app.db)

  Mode: Local (Docker, single-user, no auth)
```

Then open the browser:
```bash
open http://localhost:<frontend_port>
```

Tell the developer:
> Connect your databases from the "Databases" page in the sidebar. You can connect PostgreSQL, MySQL, MongoDB, SQLite, or upload CSV/Excel/Parquet files. No LLM connection is needed if you plan to use Byaan through MCP.

Ask the developer to confirm once they have connected a database or if they want to skip this step for now.

## Phase 6: Learn the Codebase

Tell the developer:
> Now I will analyze your codebase to learn your database schema, query patterns, and business domain. This creates a skill that helps AI tools write accurate queries against your data.

Then invoke the `/byaan:learn` skill to run the full codebase analysis. This will create the data-agent skill at `.claude/skills/data-agent/SKILL.md`.

## Phase 7: Memory Setup

Ask the developer:
> Is there anything you would like me to remember about this project or how you work? For example:
> - Team conventions or coding standards
> - Deployment notes or environments
> - Project context or goals
> - People and their roles
>
> I will save these so future conversations have this context. Type "skip" to move on.

If they provide information, save it as memory files using the memory system.

## Phase 8: MCP and Tool Setup

Ask the developer:
> Would you like to install the Byaan MCP server for local use? This lets you query your databases directly from Claude Code, Cursor, or any MCP-compatible tool. No API key is needed for local development.
>
> Which AI tool(s) are you using?
> 1. Claude Code
> 2. Cursor
> 3. Codex CLI
> 4. Gemini CLI
> 5. Other / Multiple

Based on their answer, write the MCP config file directly. Do not just print instructions. Create the file yourself.

The MCP server runs directly via `uv` — no wrapper script needed. Use the absolute path to the project root.

**Claude Code:**
1. Read `.claude/settings.json` (or `.claude/settings.local.json`) if it exists
2. Merge the byaan MCP server into the existing config (preserve other servers):
   ```json
   {
     "mcpServers": {
       "byaan": {
         "type": "stdio",
         "command": "uv",
         "args": ["--directory", "<absolute_path_to_project>", "run", "python", "-m", "server.mcp.stdio_server"]
       }
     }
   }
   ```
3. Write merged config back

**Cursor:**
1. Read `.cursor/mcp.json` if it exists, otherwise start with empty `{}`
2. Merge the byaan MCP server into the existing config:
   ```json
   {
     "mcpServers": {
       "byaan": {
         "command": "uv",
         "args": ["--directory", "<absolute_path_to_project>", "run", "python", "-m", "server.mcp.stdio_server"]
       }
     }
   }
   ```
3. Write merged config back to `.cursor/mcp.json`

**Codex CLI:**
1. Read `.codex/config.toml` if it exists (project-level) or tell the dev about `~/.codex/config.toml` (global)
2. Add the byaan MCP server section:
   ```toml
   [mcp_servers.byaan]
   command = "uv"
   args = ["--directory", "<absolute_path_to_project>", "run", "python", "-m", "server.mcp.stdio_server"]
   ```
3. Write the config. If appending to an existing file, make sure not to duplicate the section.

**Gemini CLI:**
1. Read `.gemini/settings.json` if it exists, otherwise start with empty `{}`
2. Merge the byaan MCP server into the existing config:
   ```json
   {
     "mcpServers": {
       "byaan": {
         "command": "uv",
         "args": ["--directory", "<absolute_path_to_project>", "run", "python", "-m", "server.mcp.stdio_server"]
       }
     }
   }
   ```
3. Write merged config back to `.gemini/settings.json`

**Multiple tools:** If the developer uses more than one tool, write all applicable configs.

After writing the config, tell the developer:
> Byaan MCP is configured for [tool name]. Restart your AI tool to connect. Once connected, you can query your databases, build dashboards, and analyze data through Byaan.

If they said no or skipped, tell them they can set it up later by running `/byaan:start` again.

## Phase 9: Git Hooks

Run `make install-hooks` to set up the pre-commit hook that keeps `.agents/skills/` in sync with `.claude/skills/`.

## Done

Print:
> Setup complete! Here is what was configured:
> - Backend running on http://localhost:<backend_port> (Docker, SQLite)
> - Frontend running on http://localhost:<frontend_port>
> - Codebase analyzed and data-agent skill created
> - [MCP configured for X / MCP skipped]
> - Git hooks installed
>
> Useful commands:
>   make setup-local   — build Docker images (first time or after dep changes)
>   make local         — start backend + frontend (Docker, SQLite)
>   make local-detach  — start in background
>   make local-stop    — stop containers
>   make local-rebuild — full clean rebuild (use after new dependencies)
>   make local-clean   — stop and remove volumes
>   make dev           — start with Docker + PostgreSQL instead
>   /byaan:learn       — re-analyze the codebase after schema changes

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Byaan is a secure, locally-running data analysis tool that connects to databases and AI models while keeping data private. It's a desktop application (macOS/Linux) built with React frontend, FastAPI backend, and Tauri wrapper. Users can connect to databases (PostgreSQL, MongoDB, MySQL, SQLite), analyze data through AI-powered queries, and build exportable dashboards.

**Key Value Proposition:** Data never leaves the local machine. Users connect to federated AI models (Azure, Bedrock, OpenRouter) and explore their databases securely without cloud dependencies.

## Build & Development Commands

### Backend (Python/FastAPI)

```bash
cd server && uv run ruff format . && uv run ruff check --fix .  # Format & lint
cd server && uv run ruff check .                                 # Lint check only
cd server && PYTHONPATH=..:tests uv run pytest                   # Run all tests
cd server && PYTHONPATH=..:tests uv run pytest tests/test_file.py::test_function  # Single test
cd server && uv run pytest --cov=server --cov-report=term-missing  # Tests with coverage
```

### Frontend (React/TypeScript)

```bash
cd client && pnpm dev         # Development server (port 5173)
cd client && pnpm build       # Production build
cd client && pnpm build:check # TypeScript + Vite build check
cd client && pnpm lint        # ESLint
```

### Desktop App (Tauri)

```bash
cd client && pnpm tauri:dev           # Dev mode with hot reload
cd client && pnpm tauri:build         # Production build (auto-detects arch)
cd client && pnpm tauri:build:m-series  # M-series Mac build
cd client && pnpm tauri:build:intel   # Intel Mac build
```

### Docker

```bash
# Local/Community (default — SQLite, no PostgreSQL)
make setup        # Build images
make dev          # Run with logs (foreground)
make dev-detach   # Run in background
make dev-build    # Build + run with logs
make stop         # Stop all services
make rebuild      # Full rebuild (no cache)
make clean        # Remove containers/volumes

# Hosted (PostgreSQL, closer to production)
make hosted       # Start hosted environment (background)
make hosted-logs  # Start with visible logs
make hosted-stop  # Stop hosted services
make hosted-rebuild  # Rebuild hosted images
make hosted-clean    # Remove hosted containers/volumes
```

### Access Points

- Frontend (local): http://localhost:17434
- Backend API (local): http://localhost:17433
- Frontend (hosted): http://localhost:5173
- Backend API (hosted): http://localhost:8000
- API Docs: http://localhost:8000/docs (hosted) or http://localhost:17433/docs (local)

## Architecture

```
project_x/
├── client/              # React 19 + TypeScript + Vite frontend
│   ├── src/
│   │   ├── pages/       # ChatPreview, Databases, LLMConnections, NotebooksPage
│   │   ├── stores/      # Zustand state management
│   │   ├── services/    # API client wrappers
│   │   └── components/  # Reusable UI components
│   └── src-tauri/       # Rust/Tauri desktop shell
├── server/              # FastAPI backend
│   ├── routers/         # API endpoints
│   ├── services/        # Business logic (unified_agent.py is 66KB - AI orchestration)
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic request/response schemas
│   ├── repositories/    # Data access layer
│   ├── tools/           # Agent tools (agentic.py is 42KB - HTML generation, queries)
│   ├── db/              # Database session management
│   ├── migrations/      # Alembic migrations
│   └── tests/           # pytest suite
└── web/                 # Web-only variant (React 18, different deployment)
```

### Key Services

- **server/services/unified_agent.py** - OpenAI Agents orchestration, conversation state, streaming
- **server/tools/agentic.py** - Core agent tools: HTML dashboard generation, query execution
- **server/services/llm_service.py** - LiteLLM integration for multi-provider LLM support
- **server/services/duckdb_service.py** - Analytical queries via DuckDB

### Data Flow

1. Frontend makes HTTP requests to `/api/*`
2. Vite proxy (dev) or Tauri (prod) forwards to FastAPI backend
3. Routers use services for business logic
4. Services interact with repositories for data access
5. Responses use standard envelope: `success_response()` / `error_response()`

## Code Conventions

### Python

- **Ruff** for formatting/linting (line-length: 120, Python 3.11+)
- **Double quotes** for strings
- **Async everywhere** - all I/O uses asyncio
- **Type hints required** - Pydantic models, generators, etc.
- **Logger**: `from server.utils.custom_logger import get_logger`
- **API responses**: Use `success_response(data, message)` / `error_response(error, message)` from `schemas.standard_response`
- **Imports**: Alphabetically sorted; first-party modules after stdlib/third-party

### TypeScript/React

- ESLint configured, run `pnpm lint`
- Functional components + hooks
- Zustand for global state
- TanStack React Query for data fetching

### Database

- SQLAlchemy 2.0+ async style (AsyncSessionFactory)
- SQLite default (auto-created in server/.data/app.db)
- Alembic migrations run on app startup
- Supported: PostgreSQL, MongoDB, MySQL, ODBC

### Testing

- pytest with asyncio support (asyncio_mode=auto)
- Test markers: `@pytest.mark.notebook`, `.connection`, `.workflow`, `.error_handling`
- Fixtures in `server/tests/conftest.py`

## Production Build

Desktop app bundles:

- React frontend compiled by Vite
- FastAPI backend frozen via PyInstaller
- Tauri creates native DMG/AppImage

Log location (macOS): `~/Library/Application Support/com.byaan.desktop/backend.log`

## Demo Data Workflow

To add new demo notebooks:

1. Create notebook with dataset in running app
2. Copy notebook UUID
3. Edit `server/scripts/export_notebooks_to_demo.py` line 39
4. Run: `python3 server/scripts/export_notebooks_to_demo.py`
5. Commit updated `server/example_data/demo_notebooks.json`
6. On next app start, `main.py` detects version change and seeds new examples

## Important Coding Rules for you

- don't add any un-necessary comments please
- keep the code clean, simple and to the point
- only add comments that helps developers in future and are absolutely necessary

### Database Migrations

When generating Alembic migrations:
- **Always implement complete `downgrade()` functions** - never use `pass` or leave incomplete
- Every `op.create_table()` needs corresponding `op.drop_table()` in downgrade
- Every `op.add_column()` needs corresponding `op.drop_column()` in downgrade
- Every `op.create_index()` needs corresponding `op.drop_index()` in downgrade
- Every `op.create_foreign_key()` needs corresponding `op.drop_constraint()` in downgrade
- Test both `alembic upgrade` AND `alembic downgrade` before committing

### Dual Code Paths in unified_agent.py

**IMPORTANT:** `server/services/unified_agent.py` has TWO separate code paths for streaming:

1. **Claude MCP Service path** (when `use_claude_sdk=True`) - Uses `server/services/claude_mcp_service.py` for Claude Code authentication
2. **OpenAI Agents SDK path** (when `use_claude_sdk=False`) - Uses LiteLLM for other models (OpenAI, Azure, Bedrock, etc.)

When making changes to streaming behavior, SSE events, tool handling, or any feature that affects both paths:
- Always check BOTH paths in `unified_agent.py`
- If adding SSE events (like `datasource_selected`, `html_edit_complete`, etc.), ensure they're emitted in BOTH:
  - The Claude MCP path in `claude_mcp_service.py`
  - The OpenAI Agents SDK path in `unified_agent.py`

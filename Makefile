.PHONY: setup dev dev-build dev-logs rebuild stop clean hosted hosted-build hosted-logs hosted-stop hosted-rebuild hosted-clean format lint format-check test run-server sync-skills install-hooks \
	format-backend lint-backend format-check-backend test-backend \
	format-frontend lint-frontend format-check-frontend test-frontend \
	format-all lint-all format-check-all test-all

# =============================================================================
# Local/Community development (default, SQLite, ports 17433/17434)
# =============================================================================
setup:
	docker compose build

dev:
	bash scripts/dev.sh up

dev-detach:
	bash scripts/dev.sh detach

dev-logs:
	docker compose logs -f

dev-build:
	bash scripts/dev.sh build

rebuild:
	bash scripts/dev.sh rebuild

stop:
	docker compose down

clean:
	docker compose down -v
	docker system prune -f

# =============================================================================
# Self-Hosted development (PostgreSQL, multi-tenant/teams features)
# =============================================================================
COMPOSE_HOSTED = docker compose -f docker-compose.hosted.yml -p byaan-hosted

hosted:
	$(COMPOSE_HOSTED) up -d

hosted-build:
	$(COMPOSE_HOSTED) build
	$(COMPOSE_HOSTED) up -d

hosted-logs:
	$(COMPOSE_HOSTED) up

hosted-stop:
	$(COMPOSE_HOSTED) down

hosted-rebuild:
	$(COMPOSE_HOSTED) down -v
	$(COMPOSE_HOSTED) build --no-cache
	$(COMPOSE_HOSTED) up

hosted-clean:
	$(COMPOSE_HOSTED) down -v

# =============================================================================
# Backend (Python/FastAPI) — format, lint, test
# =============================================================================
format-backend:
	@echo "Formatting Python code with Ruff..."
	cd server && uv run ruff format .
	cd server && uv run ruff check --fix .

lint-backend:
	cd server && uv run ruff check .

format-check-backend:
	cd server && uv run ruff format --check .
	cd server && uv run ruff check .

test-backend:
	cd server && PYTHONPATH=..:tests uv run pytest

# =============================================================================
# Frontend (React/TypeScript) — format, lint, test
# =============================================================================
format-frontend:
	@echo "Auto-fixing frontend with ESLint..."
	cd client && pnpm exec eslint . --fix

lint-frontend:
	cd client && pnpm lint

format-check-frontend:
	cd client && pnpm exec tsc -b
	cd client && pnpm lint

test-frontend:
	@echo "No frontend test suite configured."

# =============================================================================
# Aggregates (run both backend + frontend)
# =============================================================================
format: format-backend format-frontend

lint: lint-backend lint-frontend

format-check: format-check-backend format-check-frontend

test: test-backend test-frontend

format-all: format
lint-all: lint
format-check-all: format-check
test-all: test

run-server:
	uv run --directory server uvicorn server.main:app --host 0.0.0.0 --port 8000

# =============================================================================
# Skills sync (.claude/skills -> .agents/skills for Codex/Gemini compatibility)
# =============================================================================
sync-skills:
	@rsync -a --delete .claude/skills/ .agents/skills/
	@if [ -d "$$HOME/.codex/skills" ]; then \
		rsync -a --delete .claude/skills/ "$$HOME/.codex/skills/"; \
		echo "Skills synced: .claude/skills -> .agents/skills, $$HOME/.codex/skills"; \
	else \
		echo "Skills synced: .claude/skills -> .agents/skills"; \
	fi

install-hooks:
	@cp scripts/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Git hooks installed"

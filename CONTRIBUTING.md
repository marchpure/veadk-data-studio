# Contributing to Byaan

Thanks for helping improve Byaan. This project is still early, so the most useful contributions are clear bug reports, focused fixes, setup improvements, connector reliability, security hardening, and documentation that helps a new user get to a successful first query.

## Development Setup

Prerequisites:

- Docker and Docker Compose
- `uv`
- Node.js and `pnpm` for frontend-only work

Community development mode:

```bash
make setup
make dev
```

Open http://localhost:17434.

Backend-only checks:

```bash
cd server
PYTHONPATH=..:tests uv run pytest
uv run ruff format .
uv run ruff check --fix .
```

Frontend checks:

```bash
cd client
pnpm build
pnpm lint
```

## Pull Requests

Before opening a PR:

- Keep the change focused.
- Include tests for behavior changes when practical.
- Update docs when setup, security posture, MCP behavior, database support, or user-visible behavior changes.
- Avoid committing generated archives, local databases, secrets, logs, build output, or personal config.
- Run the relevant backend and frontend checks for the files you touched.

## Good First Contributions

Good starting points:

- Reproduce and reduce a bug report.
- Improve setup or troubleshooting docs.
- Add tests around read-only validation.
- Improve MCP setup docs for a specific client.
- Add examples for a supported database.
- Improve frontend accessibility or empty states.

## Code Style

Python:

- Ruff formatting and linting.
- Python 3.11+.
- Type hints for public service functions, schemas, and async flows.
- Prefer existing repository/service patterns over new framework abstractions.

TypeScript/React:

- Functional components and hooks.
- Follow existing component and state-management patterns.
- Run `pnpm lint` before submitting frontend changes.

## Reporting Security Issues

Please do not open public issues for vulnerabilities. Follow [SECURITY.md](SECURITY.md).

## Licensing

By contributing, you agree that your contribution will be licensed under the license that applies to the part of the repository you modify. See [docs/licensing.md](docs/licensing.md).

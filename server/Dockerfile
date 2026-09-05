# Stage 1: Build the same-origin Web bundle
ARG PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim
FROM node:20-alpine AS frontend

WORKDIR /app/client

RUN npm install -g pnpm@10.18.3

COPY client/package.json client/pnpm-lock.yaml client/.npmrc ./
RUN pnpm install --frozen-lockfile --prod=false

COPY client/ ./
RUN pnpm build

# Stage 2: Build Python dependencies
FROM ${PYTHON_BASE_IMAGE} AS deps

WORKDIR /app

ARG INSTALL_MSSQL_ODBC=false
ARG UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    gnupg2 \
    curl \
    && if [ "$INSTALL_MSSQL_ODBC" = "true" ]; then \
        curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
        && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
        && apt-get update \
        && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    fi

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

ENV UV_HTTP_TIMEOUT=300
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_DEFAULT_INDEX="$UV_DEFAULT_INDEX" UV_LINK_MODE=copy uv sync --frozen --no-install-project

# Stage 3: Runtime image
FROM ${PYTHON_BASE_IMAGE} AS runtime

WORKDIR /app

ARG VITE_PUBLIC_POSTHOG_KEY
ARG VITE_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
ARG INSTALL_MSSQL_ODBC=false
ARG INSTALL_CLAUDE_CODE=false

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libcairo2 \
    libglib2.0-0 \
    libgobject-2.0-0 \
    gnupg2 \
    && if [ "$INSTALL_MSSQL_ODBC" = "true" ]; then \
        curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
        && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
        && apt-get update \
        && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    fi

# Install Node.js (for Claude Code CLI) and the CLI itself so the SDK can spawn it.
RUN if [ "$INSTALL_CLAUDE_CODE" = "true" ]; then \
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
        && apt-get install -y --no-install-recommends nodejs \
        && npm install -g @anthropic-ai/claude-code; \
    else \
        echo "Skipping Claude Code CLI install. Set INSTALL_CLAUDE_CODE=true to include it."; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

COPY --from=deps /app/.venv /app/.venv

COPY --from=frontend /app/client/dist /app/client/dist
COPY server/ /app/server/
COPY pyproject.toml uv.lock /app/

RUN .venv/bin/python -m compileall -q /app/server/ || true

EXPOSE 8000

ENV PYTHONPATH=/app
ENV VITE_PUBLIC_POSTHOG_KEY=$VITE_PUBLIC_POSTHOG_KEY
ENV VITE_PUBLIC_POSTHOG_HOST=$VITE_PUBLIC_POSTHOG_HOST

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["server"]

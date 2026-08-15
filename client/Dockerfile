FROM node:20-alpine AS base

WORKDIR /app

RUN npm install -g pnpm@10.10.0
RUN apk add --no-cache bash

EXPOSE 5173

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Production build stage
FROM base AS production

ARG VITE_PUBLIC_POSTHOG_KEY
ARG VITE_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com

COPY client/package*.json client/pnpm-lock.yaml* client/.npmrc ./

RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --prod

COPY client/ .

ENV VITE_PUBLIC_POSTHOG_KEY=$VITE_PUBLIC_POSTHOG_KEY
ENV VITE_PUBLIC_POSTHOG_HOST=$VITE_PUBLIC_POSTHOG_HOST
RUN pnpm build

# Dev stage — install deps so the anonymous node_modules volume starts populated
FROM base AS dev

COPY client/package*.json client/pnpm-lock.yaml* client/.npmrc ./

RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["client"]

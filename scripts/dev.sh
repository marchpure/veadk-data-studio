#!/usr/bin/env bash
set -euo pipefail

command="${1:-up}"

print_urls() {
    local client_addr server_addr client_port server_port

    client_addr="$(docker compose port client 5173 2>/dev/null | tail -n 1 || true)"
    server_addr="$(docker compose port server 8000 2>/dev/null | tail -n 1 || true)"

    client_port="${client_addr##*:}"
    server_port="${server_addr##*:}"

    if [ -z "$client_addr" ] || [ "$client_port" = "$client_addr" ]; then
        client_port="${FRONTEND_PORT:-17434}"
    fi

    if [ -z "$server_addr" ] || [ "$server_port" = "$server_addr" ]; then
        server_port="${BACKEND_PORT:-17433}"
    fi

    echo ""
    echo "Byaan is ready."
    echo "  App:     http://localhost:${client_port}/"
    echo "  Backend: http://localhost:${server_port}/health"
    echo ""
}

compose_up_detached_wait() {
    if docker compose up --help 2>/dev/null | grep -q -- '--wait'; then
        docker compose up -d --wait
        return
    fi

    docker compose up -d
    wait_for_urls
}

wait_for_urls() {
    local timeout="${DEV_WAIT_TIMEOUT:-180}"
    local client_addr server_addr client_port server_port

    echo "Waiting for Byaan to become ready..."
    for _ in $(seq 1 "$timeout"); do
        client_addr="$(docker compose port client 5173 2>/dev/null | tail -n 1 || true)"
        server_addr="$(docker compose port server 8000 2>/dev/null | tail -n 1 || true)"
        client_port="${client_addr##*:}"
        server_port="${server_addr##*:}"

        if [ -n "$client_addr" ] && [ "$client_port" != "$client_addr" ] && \
           [ -n "$server_addr" ] && [ "$server_port" != "$server_addr" ] && \
           curl -fsS "http://localhost:${server_port}/health" >/dev/null 2>&1 && \
           curl -fsS "http://localhost:${client_port}/" >/dev/null 2>&1; then
            return
        fi

        sleep 1
    done

    echo "Byaan did not become ready after ${timeout} seconds."
    echo "Check logs with: docker compose logs"
    exit 1
}

case "$command" in
    up)
        compose_up_detached_wait
        print_urls
        echo "View logs: make dev-logs"
        echo "Stop:      make stop"
        echo ""
        ;;

    detach)
        compose_up_detached_wait
        print_urls
        echo "View logs: make dev-logs"
        echo "Stop:      make stop"
        echo ""
        ;;

    build)
        docker compose build
        compose_up_detached_wait
        print_urls
        echo "View logs: make dev-logs"
        echo "Stop:      make stop"
        echo ""
        ;;

    rebuild)
        docker compose down -v
        docker compose build --no-cache
        compose_up_detached_wait
        print_urls
        echo "View logs: make dev-logs"
        echo "Stop:      make stop"
        echo ""
        ;;

    logs)
        docker compose logs -f
        ;;

    *)
        echo "Unknown dev command: $command"
        echo "Usage: scripts/dev.sh [up|detach|build|rebuild]"
        exit 1
        ;;
esac

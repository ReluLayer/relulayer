#!/bin/bash
set -euo pipefail

DOCKER_COMPOSE="infrastructure/docker-compose.yml"
FRONTEND_DIR="frontend"
PID_FILE=".vite-dev.pid"
UVICORN_PID_FILE=".uvicorn-dev.pid"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/vite-dev.log"
PORT=5173
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8000/health}"

log_info() { echo -e "\033[0;36minfo\033[0m  $1"; }
log_success() { echo -e "\033[0;32msuccess\033[0m $1"; }
log_warn() { echo -e "\033[1;33mwarn\033[0m  $1"; }
log_error() { echo -e "\033[0;31merror\033[0m $1"; }

stop_uvicorn() {
    if [ -f "$UVICORN_PID_FILE" ]; then
        pid=$(cat "$UVICORN_PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_info "Stopping uvicorn (PID: $pid)..."
            kill "$pid" || true
        fi
        rm "$UVICORN_PID_FILE"
    fi
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    fi
}

stop_vite() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null; then
            log_info "Stopping Vite (PID: $pid)..."
            kill "$pid" || true
            sleep 2
            pkill -P "$pid" || true
        fi
        rm "$PID_FILE"
    fi
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        log_warn "Port $PORT busy. Cleaning up..."
        lsof -ti:$PORT | xargs kill -9 || true
    fi
}

case "${1:-help}" in
    up)
        log_info "Starting Engine..."
        docker compose -f "$DOCKER_COMPOSE" up -d
        mkdir -p "$LOG_DIR"
        log_info "Production readiness (/health) — waiting for API on ${API_HEALTH_URL%/*}..."
        health_ok=""
        for _ in $(seq 1 45); do
            if body="$(curl -sfS --max-time 5 "$API_HEALTH_URL" 2>/dev/null)"; then
                health_ok=1
                status="$(printf '%s' "$body" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")"
                log_success "Health status: $status"
                printf '%s' "$body" | python3 -m json.tool 2>/dev/null | head -n 40 || printf '%s\n' "$body" | head -c 1200
                echo ""
                if [ "$status" = "critical" ]; then
                    log_warn "Ollama or core stack reported critical — check degraded_paths in full JSON above."
                elif [ "$status" = "degraded" ]; then
                    log_warn "Some paths degraded (video, charts, TTS, etc.) — see /health JSON."
                fi
                break
            fi
            sleep 1
        done
        if [ -z "$health_ok" ]; then
            log_warn "Could not reach $API_HEALTH_URL after 45s. Is the backend container up? Retry: curl -s $API_HEALTH_URL | python3 -m json.tool"
        fi
        stop_vite
        log_info "Starting Frontend on port $PORT..."
        cd "$FRONTEND_DIR"
        nohup npm run dev -- --port $PORT --strictPort >> "../$LOG_FILE" 2>&1 &
        echo $! > "../$PID_FILE"
        log_success "System ready at http://localhost:$PORT"
        ;;
    dev)
        # Run backend directly in WSL2 (no Docker) — Ollama reachable at 127.0.0.1:11434
        stop_uvicorn
        mkdir -p "$LOG_DIR"
        log_info "Starting backend (WSL2-local) on port 8000..."
        OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}" \
            nohup python3 -m uvicorn orchestration.main:app \
                --host 0.0.0.0 --port 8000 \
                >> "$LOG_DIR/uvicorn-dev.log" 2>&1 &
        echo $! > "$UVICORN_PID_FILE"
        log_info "Waiting for API on ${API_HEALTH_URL%/*}..."
        health_ok=""
        for _ in $(seq 1 45); do
            if body="$(curl -sfS --max-time 5 "$API_HEALTH_URL" 2>/dev/null)"; then
                health_ok=1
                status="$(printf '%s' "$body" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")"
                log_success "Health status: $status"
                printf '%s' "$body" | python3 -m json.tool 2>/dev/null | head -n 40 || printf '%s\n' "$body" | head -c 1200
                echo ""
                break
            fi
            sleep 1
        done
        if [ -z "$health_ok" ]; then
            log_warn "Could not reach $API_HEALTH_URL after 45s. Check logs: tail -f $LOG_DIR/uvicorn-dev.log"
        fi
        stop_vite
        log_info "Starting Frontend on port $PORT..."
        cd "$FRONTEND_DIR"
        nohup npm run dev -- --port $PORT --strictPort >> "../$LOG_FILE" 2>&1 &
        echo $! > "../$PID_FILE"
        log_success "System ready at http://localhost:$PORT (backend: WSL2-local, no Docker)"
        ;;
    down)
        docker compose -f "$DOCKER_COMPOSE" down 2>/dev/null || true
        stop_uvicorn
        stop_vite
        log_success "System offline."
        ;;
    logs)
        tail -f "$LOG_FILE"
        ;;
    dev-logs)
        tail -f "$LOG_DIR/uvicorn-dev.log"
        ;;
    *)
        echo "Usage: ./manage.sh {up|down|dev|dev-logs|logs}"
        ;;
esac
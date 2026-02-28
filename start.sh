#!/usr/bin/env bash
# Cut It — single-command launcher
# Usage: ./start.sh
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${CYAN}[cut-it]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
err()  { echo -e "${RED}  ✗${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
command -v poetry >/dev/null 2>&1 || { err "poetry not found — https://python-poetry.org/docs/#installation"; exit 1; }
command -v npm    >/dev/null 2>&1 || { err "npm not found — install Node.js from https://nodejs.org"; exit 1; }
command -v ollama >/dev/null 2>&1 || warn "ollama not found — image/text LLM screening will be disabled"

# ── Backend setup ─────────────────────────────────────────────────────────────
log "Setting up backend..."
cd "$SCRIPT_DIR/backend"

if [ ! -f ".env" ]; then
  cp .env.example .env
  warn "Created backend/.env from example — add your MISTRAL_API_KEY"
fi

poetry install --quiet
ok "Python dependencies installed"

# Download spacy model if missing
if ! poetry run python -c "import en_core_web_lg" 2>/dev/null; then
  log "Downloading spaCy model (en_core_web_lg)..."
  poetry run python -m spacy download en_core_web_lg
  ok "spaCy model ready"
fi

# Pull Ollama model if ollama is available
if command -v ollama >/dev/null 2>&1; then
  OLLAMA_MODEL="${OLLAMA_MODEL:-mistral:latest}"
  if ! ollama list | grep -q "${OLLAMA_MODEL%%:*}"; then
    log "Pulling Ollama model: $OLLAMA_MODEL"
    ollama pull "$OLLAMA_MODEL"
    ok "Ollama model ready"
  fi
fi

log "Starting backend on http://localhost:8080..."
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# ── Frontend setup ────────────────────────────────────────────────────────────
log "Setting up frontend..."
cd "$SCRIPT_DIR/frontend"

if [ ! -d "node_modules" ]; then
  npm install --silent
  ok "Node dependencies installed"
fi

log "Starting frontend on http://localhost:3000..."
npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

# ── Ready ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Cut It is running${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
ok "Proxy  → http://localhost:8080  (point Mistral clients here)"
ok "Dashboard → http://localhost:3000"
echo ""
echo "  Privacy flow:"
echo "  Your Data → Local Screening → Clean Only → Mistral Cloud"
echo ""
echo "Press Ctrl+C to stop all services."

# ── Cleanup on exit ───────────────────────────────────────────────────────────
trap 'log "Shutting down..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0' INT TERM
wait

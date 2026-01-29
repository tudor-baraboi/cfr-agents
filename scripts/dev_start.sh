#!/bin/bash
# Development startup script for FAA Certification Agent
# Starts both the search proxy and main backend services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== FAA Certification Agent Development Server ===${NC}"
echo ""

# Check for .env file
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo -e "${RED}Error: $BACKEND_DIR/.env not found${NC}"
    echo "Please create a .env file with the required configuration."
    exit 1
fi

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    if [ ! -z "$PROXY_PID" ]; then
        kill $PROXY_PID 2>/dev/null || true
    fi
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Done.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Check if ports are already in use
check_port() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        echo -e "${YELLOW}Warning: Port $port is already in use${NC}"
        return 1
    fi
    return 0
}

cd "$BACKEND_DIR"

# Check ports
PROXY_PORT=8001
BACKEND_PORT=8000

if ! check_port $PROXY_PORT; then
    echo -e "${YELLOW}Search proxy may already be running on port $PROXY_PORT${NC}"
fi

if ! check_port $BACKEND_PORT; then
    echo -e "${YELLOW}Backend may already be running on port $BACKEND_PORT${NC}"
fi

echo -e "${GREEN}Starting Search Proxy on port $PROXY_PORT...${NC}"
PYTHONPATH="$BACKEND_DIR" python3 -m uvicorn search_proxy.main:app --port $PROXY_PORT --reload &
PROXY_PID=$!
echo "Search Proxy PID: $PROXY_PID"

# Wait for proxy to be ready
echo "Waiting for search proxy to start..."
sleep 2

# Verify proxy is running
if ! curl -s http://localhost:$PROXY_PORT/health > /dev/null 2>&1; then
    echo -e "${RED}Error: Search proxy failed to start${NC}"
    kill $PROXY_PID 2>/dev/null || true
    exit 1
fi
echo -e "${GREEN}Search Proxy is ready!${NC}"

echo ""
echo -e "${GREEN}Starting Backend on port $BACKEND_PORT...${NC}"
PYTHONPATH="$BACKEND_DIR" python3 -m uvicorn app.main:app --port $BACKEND_PORT --reload &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo "Waiting for backend to start..."
sleep 3

# Verify backend is running
if ! curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
    echo -e "${RED}Error: Backend failed to start${NC}"
    cleanup
    exit 1
fi
echo -e "${GREEN}Backend is ready!${NC}"

echo ""
echo -e "${GREEN}=== All services running ===${NC}"
echo "  Search Proxy: http://localhost:$PROXY_PORT"
echo "  Backend:      http://localhost:$BACKEND_PORT"
echo "  API Docs:     http://localhost:$BACKEND_PORT/docs"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for both processes
wait $PROXY_PID $BACKEND_PID

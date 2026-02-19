#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# Define paths and constants
REPO_ROOT="/Users/kleo/Documents/code/openclaw-mission-control"
FRONTEND_DIR="$REPO_ROOT/frontend"
SERVER_PORT=8000
FRONTEND_PORT=5173

echo "--- Starting Smoke Test Orchestration ---"

# 1. Database Reset
echo "Resetting database..."
$REPO_ROOT/scripts/db-reset.sh

# 2. Bootstrap Admin (DB is clean now)
echo "Bootstrapping admin account..."
cd $REPO_ROOT/packages/server
uv run python -m app.scripts.create_local_admin --email johan@example.com --password devpass

# 2b. Create Local Test Agent
echo "Creating local test agent..."
cd $REPO_ROOT/packages/server
AGENT_OUTPUT=$(uv run python -m app.scripts.create_local_agent --identifier "local-test-agent" --display-name "Local Test Agent")
echo "$AGENT_OUTPUT"

# Extract API Key
MC_LOCAL_AGENT_KEY=$(echo "$AGENT_OUTPUT" | grep "API KEY:" | head -n 1 | sed 's/API KEY: //' | tr -d '\n\r')
if [ -z "$MC_LOCAL_AGENT_KEY" ]; then
    echo "ERROR: Failed to extract API key from agent creation script."
    exit 1
fi
export MC_LOCAL_AGENT_KEY
echo "Agent API Key extracted."

# 2c. Generate Bridge Config
echo "Generating bridge config..."
cat > $REPO_ROOT/packages/bridge/comms-bridge.test.yaml << EOF
mission_control:
  url: "http://localhost:$SERVER_PORT"
gateway:
  url: "http://127.0.0.1:18789"
  api_key_env: "OPENCLAW_GATEWAY_KEY"
agents:
  - name: "local-test-agent"
    api_key_env: "MC_LOCAL_AGENT_KEY"
    org_slug: "default"
logging:
  level: "info"
  format: "text"
EOF
echo "Bridge config generated at $REPO_ROOT/packages/bridge/comms-bridge.test.yaml"

# 3. Start Server (Backend/Bridge) - Run in background
echo "Starting backend server..."
cd $REPO_ROOT/packages/server
uv run uvicorn app.main:app --host 0.0.0.0 --port $SERVER_PORT & 
SERVER_PID=$!
echo "Backend Server PID: $SERVER_PID"
sleep 7 # Give server time to initialize

# 3b. Start Bridge (Orchestrated)
echo "Starting bridge..."
cd $REPO_ROOT/packages/bridge
uv run python -m mc_bridge.main --config comms-bridge.test.yaml &
BRIDGE_PID=$!
echo "Bridge PID: $BRIDGE_PID"
sleep 2

# 4. Start Frontend - Run in background
echo "Starting frontend..."
cd $FRONTEND_DIR
# Ensure frontend dependencies are ready
npm install
# Kill any process using the frontend port to ensure clean start
fuser -k $FRONTEND_PORT/tcp 2>/dev/null || true
PORT=$FRONTEND_PORT npm run dev & 
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"
sleep 10 # Increased sleep for frontend + npm install

# 5. Install Root Dependencies (For npx/playwright from root)
echo "Installing root project dependencies (if package.json exists)..."
cd $REPO_ROOT
if [ -f package.json ]; then
    npm install
else
    echo "Root package.json not found, skipping root npm install."
fi

# 6. Run Playwright Tests (Run from frontend directory where playwright is installed)
echo "Running Playwright smoke tests..."
cd $FRONTEND_DIR
npx playwright test tests/smoke-test.spec.ts

TEST_STATUS=$?

# 7. Shutdown
echo "Shutting down services..."
kill $BRIDGE_PID 2>/dev/null || true
kill $SERVER_PID
kill $FRONTEND_PID

# Wait briefly for processes to terminate
sleep 3
echo "Smoke test finished. Status: $TEST_STATUS"

exit $TEST_STATUS